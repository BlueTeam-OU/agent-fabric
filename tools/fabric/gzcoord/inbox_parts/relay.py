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

import httpsafe
import process
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


def _stopped_by_operator(unit: str, env: dict[str, str]) -> bool:
    """True only for a unit that ran this boot and was stopped cleanly:
    inactive, Result success, left after it was entered. A failed unit, one
    never started (monotonic stamps 0) or an answer systemctl would not give
    is False — those are started as before. The monotonic stamps are compared
    because they are integers; the wall-clock ones are locale text."""
    try:
        shown = subprocess.run(["systemctl", "--user", "show", unit, "-p", "ActiveState", "-p", "Result",
                                "-p", "ActiveEnterTimestampMonotonic", "-p", "InactiveEnterTimestampMonotonic"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               timeout=15, env=env, text=True)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if shown.returncode != 0:
        return False
    props = dict(line.split("=", 1) for line in shown.stdout.splitlines() if "=" in line)
    try:
        entered = int(props["ActiveEnterTimestampMonotonic"])
        left = int(props["InactiveEnterTimestampMonotonic"])
    except (KeyError, ValueError):
        return False
    return props.get("ActiveState") == "inactive" and props.get("Result") == "success" and 0 < entered < left


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
        env = {**os.environ, "XDG_RUNTIME_DIR": runtime}
        # An operator's `systemctl stop` holds: the unit file says the relay is
        # supervised, so neither a start nor the detached spawn below may undo it.
        if _stopped_by_operator(unit, env):
            return {"hosted": True, "started": False, "note": t("start.relay-stopped", {"unit": unit})}
        try:
            asked = subprocess.run(["systemctl", "--user", "start", unit], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
                                   env=env).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            asked = False   # systemctl itself failed: the spawn below is the fallback
        if asked:
            for _ in range(16):
                if _relay_up(relay_url, 1):
                    return {"hosted": True, "started": True, "unit": unit}
                time.sleep(0.5)
            # The unit logs to the journal (gzcoord-relay.service), never to bridge.log, which
            # only the spawn below writes: the note names where this relay's output is.
            return {"hosted": True, "started": False,
                    "note": t("start.relay-unit-silent", {"unit": unit, "log": f"journalctl --user -u {unit}"})}
    with open(log, "a") as out:
        child = process.spawn_service([binary, "--host", "127.0.0.1", "--port", "8765", "--db", db,
                                       "--auth-token-file", token_file],
                                      stdin=subprocess.DEVNULL, stdout=out, stderr=out)
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


# The relay is called directly and nowhere else: urllib, unlike the Node's
# fetch, would go through http_proxy/https_proxy from the environment and
# follow a redirect with the Authorization header to whatever host it names.
_OPENER = httpsafe.opener(proxies=False, redirects="none")


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
