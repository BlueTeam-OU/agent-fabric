"""tools/fabric/gzcoord/inbox_parts/relay.py — the relay started, asked, and its errors said.
A part of tools/fabric/gzcoord/inbox.py, whose docstring is the contract."""
from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any
from .. import i18n
from ..gzmsg import en
from .config import default_relay
from .tokens import TokenRefused


# ── the hosted relay ─────────────────────────────────────────────────

def _relay_up(relay_url: str, seconds: int) -> bool:
    try:
        return subprocess.run(["curl", "-sf", "-m", str(seconds), f"{relay_url}/status"], stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=seconds + 5).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def ensure_relay(runtime_dir: str, relay_url: str | None = None, t: i18n.Printer | None = None) -> dict:
    """The hosting workspace (whose runtime dir holds the relay's venv) is
    the coordinator's: its session start brings the relay up — the user
    unit bootstrap installed where a manager runs (supervised, outlives the
    session), else a detached spawn. A workspace without the venv is a
    client and returns at once: nothing in a client session may host."""
    relay_url = default_relay() if relay_url is None else relay_url
    t = t or en()
    binary = os.path.join(runtime_dir, "venv", "bin", "claude-bridge")
    if not os.path.exists(binary):
        return {"hosted": False, "started": False}
    if _relay_up(relay_url, 2):
        return {"hosted": True, "started": False}
    token_file = os.path.join(runtime_dir, "bridge-token")
    db = os.path.join(runtime_dir, "claude-bridge.db")
    log = os.path.join(runtime_dir, "bridge.log")
    if not os.path.exists(token_file):
        return {"hosted": True, "started": False, "note": t("start.relay-no-token-file", {"token_file": token_file})}
    unit = os.environ.get("GZCOORD_RELAY_UNIT", "gzcoord-relay")
    unit_file = os.path.join(os.environ.get("HOME", os.path.expanduser("~")), ".config", "systemd", "user", f"{unit}.service")
    # The user manager's bus: XDG_RUNTIME_DIR where the shell has it, else
    # the account's runtime dir — a `sudo -u` or the host executor gives
    # the shell neither while the lingering manager is up. systemctl needs
    # the dir in ITS environment; a bus that is not a socket is a leftover.
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    bus = os.path.join(runtime, "bus")
    try:
        bus_is_socket = stat.S_ISSOCK(os.stat(bus).st_mode)
    except OSError:
        bus_is_socket = False
    if os.path.exists(unit_file) and (bus_is_socket or os.environ.get("GZCOORD_TEST_BUS_ANY") == "1"):
        try:
            asked = subprocess.run(["systemctl", "--user", "start", unit], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
                                   env={**os.environ, "XDG_RUNTIME_DIR": runtime}).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            asked = False   # systemctl itself failed: the spawn below is the fallback
        if asked:
            for _ in range(16):
                if _relay_up(relay_url, 1):
                    return {"hosted": True, "started": True, "unit": unit}
                time.sleep(0.5)
            return {"hosted": True, "started": False, "note": t("start.relay-unit-silent", {"unit": unit, "log": log})}
    with open(log, "a") as out:
        child = subprocess.Popen([binary, "--host", "127.0.0.1", "--port", "8765", "--db", db,
                                  "--auth-token-file", token_file],
                                 stdin=subprocess.DEVNULL, stdout=out, stderr=out, start_new_session=True)
    for _ in range(16):
        if _relay_up(relay_url, 1):
            return {"hosted": True, "started": True, "pid": child.pid}
        time.sleep(0.5)
    return {"hosted": True, "started": False, "note": t("start.relay-silent", {"log": log})}


# ── the relay's API ──────────────────────────────────────────────────

class RelayError(Exception):
    """A relay call that did not answer 2xx (status set) or could not be
    made at all (status None). `reached` is False when the request provably
    never reached the relay (the connection was refused, the name did not
    resolve), None when that cannot be told (a timeout or a reset may come
    after the relay took it)."""

    def __init__(self, message: str, status: int | None = None, reached: bool | None = None):
        super().__init__(message)
        self.status = status
        self.reached = reached


# Node's fetch gave up on a response with no headers after 300 s (undici's
# headersTimeout); the long poll is at most 55 s. The same bound here.
API_TIMEOUT = 300


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_a, **_k):  # noqa: ANN002 — the stdlib's signature
        return None   # a 3xx is then an HTTPError: an answer that is not 2xx


# The relay is called directly and nowhere else: urllib, unlike the Node's
# fetch, would go through http_proxy/https_proxy from the environment and
# follow a redirect with the Authorization header to whatever host it names.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def api(tok: str, path_and_query: str, relay_url: str | None = None, method: str = "GET", body: str | None = None,
        timeout: float = API_TIMEOUT) -> Any:
    relay_url = default_relay() if relay_url is None else relay_url
    # tok came through checked_token(): http.client's own refusal of a line
    # break would quote the whole header, the token in it, into an error line.
    req = urllib.request.Request(f"{relay_url}{path_and_query}", method=method,
                                 data=None if body is None else body.encode("utf-8"),
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raise RelayError(f"{path_and_query} -> HTTP {e.code}", e.code) from None
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        never = isinstance(reason, (ConnectionRefusedError, socket.gaierror))
        raise RelayError(f"fetch failed ({reason})", reached=False if never else None) from None
    return json.loads(raw.decode("utf-8"))


def explain_relay_error(e: BaseException, relay_url: str, t: i18n.Printer | None = None) -> dict:
    """A 401 is not "unreachable": the relay answered and refused the token
    — after a rotation the fix is a re-sync, so say so, and exit 4 so a
    watch can stop instead of printing the same line for hours."""
    t = t or en()
    status = getattr(e, "status", None)
    if status in (401, 403):
        return {"line": t("relay.refused", {"relay_url": relay_url, "status": status}), "code": 4}
    # The synced token re-read after a 401 that holds a line break: the 401
    # stands, and the watch stops on it, never "relay down" every 30 s.
    if isinstance(e, TokenRefused):
        return {"line": f"gzcoord inbox: {e}", "code": 4}
    return {"line": t("relay.unreachable", {"relay_url": relay_url, "detail": str(e)}), "code": 0}
