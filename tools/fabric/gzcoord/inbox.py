"""tools/fabric/gzcoord/inbox.py — GZCoord's inbox: what the relay holds for
THIS session, delivered the way SPEC §17 says a recipient receives — a
body read only when it is addressed to it. Ported from
communication/gzcoord/scripts/inbox.mjs (agent-fabric ADR-040 §7, Wave
7); that path is now a shim that runs this.

CONTRACT, frozen from the Node:
  argv      (none)              drain: one cursor page, return at once
            --follow            the watch: block for the life of the
                                session, print each delivery as it lands,
                                never return on a quiet spell
            --wait [S]          block up to S seconds (Number(S), else
                                1800) and return the moment a message
                                addressed here lands; --keyword K
                                (repeatable, 3+ characters, at most 8)
                                also ends it on a passing message
            --replay <seq|message-id> [--json]
                                re-read ONE message; the cursor does not
                                move; a body not addressed here is not
                                shown. --json: one object (addressed,
                                seq, sender, when, type, metadata, text),
                                or {"addressed": false, "seq": N}
            --history [<seq>]   one line per message addressed here in the
                                relay's recent history; bodies stay with
                                --replay; the cursor does not move
            --held              is this account's inbox held (planning)?
  env       CLAUDE_BRIDGE_URL and GZCOORD_CHANNEL (together, or over a
            project's integration), CLAUDE_BRIDGE_AUTH_TOKEN (after the
            synced file), AGENT_FABRIC_ROOT, AGENT_FABRIC_STATE_DIR,
            AGENT_FABRIC_HOLD_DIR, GZCOORD_JOURNAL=off, GZCOORD_RELAY_UNIT,
            GZCOORD_TEST_BUS_ANY=1, XDG_RUNTIME_DIR, HOME,
            GZCOORD_DEFAULT_LOCALE_ONLY
  stdout    deliveries, the drain's listing, replay/history output, the
            keyword hit, the watch's relay-down/back lines and the
            journal's held-messages line — what the Monitor turns into
            notifications
  stderr    every start-up and refusal line; the hold's held/released
  exit      0 drained, delivered, nothing for you, not configured, no
            token, relay unreachable on a drain or wait; 1 a usage line,
            replay of no such message, the --held "not held"; 2 a control
            channel named, replay not addressed (--json too); 3 a keyword
            hit; 4 a refused token (the watch ends with it). Anything
            unforeseen is `gzcoord inbox: <why>` and exit 0: the whole
            contract of a session start is one line and exit 0.

The rest of the Node's header — the modes, the hold, the addressee rule,
why the watch is one process under a Monitor — is kept below where each
applies. Never blocks a session start: relay down, no token, no
catalogue — each is one line on stderr and exit 0.

THE JOURNAL (ADR-041 rule 4), in this process now: a page's messages
addressed to this session are kept in its own journal before the page is
acknowledged; one the journal cannot take is neither acknowledged nor
shown. The Node ran episodic.py as a process per page, and that crossing
is where the journal's edge cases kept appearing (#78, #84, #88) — the
reason Wave 7 moved this file. The order is the protocol's and is kept.
"""
from __future__ import annotations

import contextlib
import io
import json
import math
import os
import re
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from . import gzmsg, i18n, paths
from . import jsvalues as js
from .gzmsg import en

# The default dictionary's printer for a caller that passes none: a test,
# another tool. main() resolves the login's once and passes it down.

# ── the project's integration ────────────────────────────────────────

def workspace() -> str:
    """The projects/ directory the fabric checkout sits in: where the relay's
    database, token and venv live — host state, never inside a repository."""
    return os.path.dirname(paths.fabric_root())


def relay_runtime_dir(cfg: dict, ws: str | None = None) -> str:
    v = cfg.get("relay_runtime_dir")
    return os.path.abspath(os.path.join(workspace() if ws is None else ws, ".gzcoord" if v is None else v))


def integration_config(project: str | None, env: dict | None = None, t: i18n.Printer | None = None) -> dict:
    """Which relay, which channel, where the token and the hosted relay's
    runtime live: from the PROJECT (projects/<id>/integration/gzcoord/
    config.json) or from the environment (CLAUDE_BRIDGE_URL and
    GZCOORD_CHANNEL together). Nothing else: until 2026-09-16 the defaults
    were one project's, and a working copy of any other silently joined
    that project's channel with its token file."""
    env = os.environ if env is None else env
    t = t or en()
    file = os.path.join(paths.fabric_root(), "projects", project, "integration", "gzcoord", "config.json") if project else None
    if file:
        try:
            with open(file, encoding="utf-8") as fh:
                own = json.load(fh)
            if isinstance(own, dict) and own.get("relay_url") and own.get("channel"):
                return {"configured": True, "source": file, "relay_runtime_dir": ".gzcoord", **own,
                        "relay_url": env.get("CLAUDE_BRIDGE_URL", own["relay_url"]),
                        "channel": env.get("GZCOORD_CHANNEL", own["channel"])}
        except (OSError, ValueError):
            pass   # no file, or not JSON: the environment may still configure it
    if env.get("CLAUDE_BRIDGE_URL") and env.get("GZCOORD_CHANNEL"):
        return {"configured": True, "source": "environment", "relay_url": env["CLAUDE_BRIDGE_URL"],
                "channel": env["GZCOORD_CHANNEL"], "relay_runtime_dir": ".gzcoord"}
    where = f"projects/{project}/integration/gzcoord/config.json" if project else t("config.where-registered")
    what = t("config.for-project", {"project": project}) if project else t("config.for-working-copy")
    return {"configured": False, "source": None, "reason": t("config.not-configured", {"what": what, "where": where})}


def default_relay() -> str:
    """Where a caller that names no relay posts (the Node read it once at
    import; a process reads it once either way)."""
    return os.environ.get("CLAUDE_BRIDGE_URL", "http://127.0.0.1:8765")


class ControlChannel(ValueError):
    pass


def assert_not_control_channel(channel: Any, t: i18n.Printer | None = None) -> None:
    """A channel ending in ":control" carries the fabric's machine records
    (runtime/control/), and no session may drain or send on it — a control
    record printed into a session's context is what the control plane
    exists to avoid, and GZCOORD_CHANNEL could otherwise name one
    (2026-09-17)."""
    t = t or en()
    if isinstance(channel, str) and channel.endswith(":control"):
        raise ControlChannel(t("config.control-channel", {"channel": channel}))


def git_toplevel() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def inbox_root(who: dict) -> str:
    """The working copy the token and integration are read from: the
    checkout this runs in; outside one (a session in the workspace), the
    binding's working copy — found live on architect-cto-01, 2026-09-14,
    when a workspace launch drained nothing; the cwd is the last resort."""
    top = git_toplevel()
    if top:
        return top
    if who.get("working_copy"):
        return who["working_copy"]
    try:
        with open(who.get("binding") or "", encoding="utf-8") as fh:
            b = json.load(fh)
        if b.get("working_copy") and os.path.exists(b["working_copy"]):
            return b["working_copy"]
    except (OSError, ValueError, AttributeError):
        pass
    return os.getcwd()


def synced_var(name: str, home: str | None = None) -> str | None:
    """One `export NAME=value` line of the synced secrets file, unquoted, or
    None. The value is a secret: printed nowhere, used in place."""
    home = os.path.expanduser("~") if home is None else home
    try:
        with open(os.path.join(home, ".config", "agent-fabric", "secrets.env"), encoding="utf-8", errors="replace") as fh:
            lines = fh.read().split("\n")
    except OSError:
        return None
    pattern = re.compile(f"^export {re.escape(name)}=(.*)$")
    for line in lines:
        m = pattern.match(line)
        if not m:
            continue
        v = gzmsg.js_trim(m.group(1))
        if len(v) >= 2 and ((v[0] == "'" and v[-1] == "'") or (v[0] == '"' and v[-1] == '"')):
            v = v[1:-1]
        elif v in ("'", '"'):
            v = ""   # a lone quote: starts and ends with itself, sliced away
        return v or None
    return None


class TokenRefused(Exception):
    """The relay token holds a line break or a NUL. Said in one line that
    names no part of it."""


def checked_token(v: str | None) -> str | None:
    """Every token leaves this module through here: trimmed of HTTP
    whitespace, as fetch's Headers trimmed a header value, and refused with
    a CR, LF or NUL inside. Such a token reached presence.mjs whole, and the
    first line of its fetch error, carrying the token's start, was printed
    as the presence detail (review of #93, round 2)."""
    if v is None:
        return None
    v = v.strip(" \t\r\n")
    if any(c in v for c in "\r\n\0"):
        raise TokenRefused("the relay token holds a line break or a NUL; nothing was sent with it "
                           "(fabric-secrets sync writes it again)")
    return v


def synced_token(home: str | None = None) -> str | None:
    return checked_token(synced_var("CLAUDE_BRIDGE_AUTH_TOKEN", home))


def token(root: str, cfg: dict | None = None) -> str | None:
    """The token, from wherever this working copy keeps it; never printed,
    never logged. The synced file first: the environment is a snapshot of
    it taken when the session's shell started, and after a rotation it
    stays wrong for the life of the session (web-dev-01, 2026-09-14)."""
    return checked_token(_token(root, cfg))


def _token(root: str, cfg: dict | None) -> str | None:
    # Fields only: nothing this default says is printed.
    cfg = integration_config(None, os.environ, en()) if cfg is None else cfg
    synced = synced_var("CLAUDE_BRIDGE_AUTH_TOKEN")
    if synced:
        return synced
    if os.environ.get("CLAUDE_BRIDGE_AUTH_TOKEN"):
        return os.environ["CLAUDE_BRIDGE_AUTH_TOKEN"]
    env_file = os.path.join(root, cfg["token_env_file"]) if cfg.get("token_env_file") else None
    if env_file and os.path.exists(env_file):
        with open(env_file, encoding="utf-8") as fh:
            for line in fh.read().split("\n"):
                if line.startswith("CLAUDE_BRIDGE_AUTH_TOKEN="):
                    return gzmsg.js_trim(line[len("CLAUDE_BRIDGE_AUTH_TOKEN="):])
    try:
        with open(os.path.join(root, ".claude/settings.local.json"), encoding="utf-8") as fh:
            v = (json.load(fh).get("env") or {}).get("CLAUDE_BRIDGE_AUTH_TOKEN")
        if v:
            return v
    except (OSError, ValueError, AttributeError):
        pass
    # The hosting workspace holds the token the relay itself reads
    # (projects/.gzcoord/bridge-token, 0600): a session there is the host.
    try:
        with open(os.path.join(relay_runtime_dir(cfg), "bridge-token"), encoding="utf-8") as fh:
            v = gzmsg.js_trim(fh.read())
        if v:
            return v
    except OSError:
        pass
    return None


def identity(me: dict | None = None, taxonomy: gzmsg.Taxonomy | None = None) -> dict:
    """Who this session is on the channel: <host>/<login> — the AGENT, never
    the working copy — and the role: the binding's, else a slug the login
    carries. A binding naming a role the catalogue lacks falls back to the
    login's, and the error travels with the identity (review of #55)."""
    me = gzmsg.whoami() if me is None else me
    instance = me["agent"]
    host = me.get("host") if me.get("host") is not None else socket.gethostname().split(".")[0]
    recorded = gzmsg.recorded_role(taxonomy, me) if taxonomy is not None else {"role": None}
    slug = recorded["role"] if recorded.get("role") is not None else \
        (gzmsg.slug_of(instance, taxonomy) if taxonomy is not None else None)
    out = {"address": f"{host}/{instance}", "instance": instance, "slug": slug, "project": me.get("project")}
    if recorded.get("error"):
        out["roleError"] = recorded["error"]
    return out


def for_me(msg: dict, me: dict) -> bool:
    """SPEC §7.1 addressing, SPEC §17 reading rule."""
    m = msg["metadata"]
    if m.get("BROADCAST") == "true":
        return True
    if "TO" in m:
        return m["TO"] == me["address"]
    if "TO-ROLE" in m:
        return me.get("slug") is not None and m["TO-ROLE"] == me["slug"]
    return False


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
    made at all (status None)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


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
        raise RelayError(f"fetch failed ({reason})") from None
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


def _records(page: Any) -> Any:
    """page.messages ?? page — the relay's page, or a bare list."""
    if isinstance(page, dict) and not js.nullish(page.get("messages", js.UNDEFINED)):
        return page["messages"]
    return page


def _when(rec: dict) -> Any:
    return js.coalesce(js.get(rec, "timestamp"), js.get(rec, "ts"), "")


def one_line(msg: dict, t: i18n.Printer | None = None) -> str:
    """The addressing half is the WIRE's vocabulary — TO, TO-ROLE,
    broadcast, the type — matched by name across locales and never
    translated; only the missing-id placeholder is."""
    t = t or en()
    m = msg["metadata"]
    to = f"TO {m['TO']}" if m.get("TO") else f"TO-ROLE {m['TO-ROLE']}" if m.get("TO-ROLE") else "broadcast"
    line = f"{m['MESSAGE-ID'] if 'MESSAGE-ID' in m else t('inbox.no-id')}  {msg['type']}  {to}  {m.get('SUBJECT', '')}"
    return re.sub(f"[{js.JS_SPACE}]+$", "", line)


def _parse_quiet(text: Any) -> dict | None:
    try:
        return gzmsg.parse(gzmsg.normalize(text))
    except (gzmsg.NotGzcoord, AttributeError, TypeError):
        return None


def replay(tok: str, relay_url: str, channel: str, which: str, me: dict, t: i18n.Printer | None = None,
           as_json: bool = False) -> int:
    """Re-read one message already past this session's cursor — the case a
    read was piped through something that dropped the body. The recent
    history, no consumer id, so no cursor moves; the body only when it is
    addressed here: SPEC §17 does not stop applying because it is a replay.
    By relay seq, or by the MESSAGE-ID inside the body (the relay's own id
    is a transport detail nobody quotes)."""
    t = t or en()
    page = api(tok, "/api/messages?" + urllib.parse.urlencode({"channel": channel, "limit": "500", "full": "1"}),
               relay_url)
    lst = _records(page)

    def mid_of(r: dict) -> Any:
        m = _parse_quiet(r.get("content"))
        return m["metadata"].get("MESSAGE-ID") if m else None

    rec = next((r for r in lst if js.string(js.get(r, "seq")) == js.string(which) or r.get("id") == which
                or mid_of(r) == which), None)
    if rec is None:
        print(t("replay.no-message", {"which": which, "n": len(lst), "channel": channel}), file=sys.stderr)
        return 1
    text = gzmsg.normalize(rec["content"])
    when = _when(rec)
    try:
        msg = gzmsg.parse(text)
    except gzmsg.NotGzcoord:
        msg = None
    if as_json:
        addressed = bool(msg and for_me(msg, me))
        print(js.stringify({"addressed": addressed, "seq": rec.get("seq"), "sender": rec.get("sender"), "when": when,
                            "type": msg["type"], "metadata": msg["metadata"], "text": text}
                           if addressed else {"addressed": addressed, "seq": rec.get("seq")}))
        return 0 if addressed else 2
    if not msg or not for_me(msg, me):
        print(t("replay.not-addressed", {"seq": js.get(rec, "seq"), "sender": js.get(rec, "sender"), "when": when,
                                         "address": me["address"]}))
        if msg:
            print(f"  {one_line(msg, t)}")
        return 2
    print(t("replay.title", {"seq": js.get(rec, "seq"), "sender": js.get(rec, "sender"), "when": when}))
    print("```text")
    print(text[:-1] if text.endswith("\n") else text)
    print("```")
    return 0


# The relay pages forward from a message it holds (since_id) and never
# backward, so what can be listed is its newest page — the same window
# --replay reads.
HISTORY_WINDOW = 500


def history(tok: str, relay_url: str, channel: str, from_seq: float | None, me: dict,
            t: i18n.Printer | None = None) -> int:
    t = t or en()
    page = api(tok, "/api/messages?" + urllib.parse.urlencode(
        {"channel": channel, "limit": str(HISTORY_WINDOW), "full": "1"}), relay_url)
    lst = _records(page)
    lines = []
    for rec in lst:
        if from_seq is not None and js.number(js.get(rec, "seq")) < from_seq:
            continue
        msg = _parse_quiet(rec.get("content"))
        if msg is None or not for_me(msg, me):
            continue
        lines.append(f"  {js.string(js.get(rec, 'seq'))}  {js.string(_when(rec))}  {js.string(js.get(rec, 'sender'))}"
                     f"  {one_line(msg, t)}")
    first = js.coalesce(js.get(lst[0], "seq") if lst else js.UNDEFINED, "-")
    print(t("history.head", {"n": len(lines), "window": len(lst), "first": first, "channel": channel,
                             "address": me["address"]}))
    for line in lines:
        print(line)
    if lines:
        print(t("history.replay-hint", {"cmd": REPLAY_CMD}))
    return 0


# SPEC §7.2: a retransmission keeps its MESSAGE-ID, and a recipient holding
# both copies discards one. The watch cannot know what this session read,
# so it shows the copy — the first may have been cut or scrolled past —
# marked with the seq of the earlier one (same FROM, same MESSAGE-ID, a
# lower seq in the recent history). Best effort and bounded: the records
# are already acknowledged, and a relay that hangs must not hold back — or,
# if the session ends meanwhile, lose — a delivery the cursor has passed
# (#57 blind review F2).
RETRANSMISSION_LOOKUP_MS = 2000


def mark_retransmissions(classified: list[dict], fetch_recent: Callable[[threading.Event], Any],
                         timeout_ms: int = RETRANSMISSION_LOOKUP_MS) -> None:
    mine = [c for c in classified if c["isMine"] and c.get("msg") and c["msg"]["metadata"].get("MESSAGE-ID")]
    if not mine:
        return
    done = threading.Event()
    box: dict = {}

    def lookup() -> None:
        try:
            box["page"] = fetch_recent(done)
        except BaseException as e:  # noqa: BLE001 — a lookup that fails marks nothing
            box["error"] = e

    worker = threading.Thread(target=lookup, daemon=True)
    worker.start()
    worker.join(timeout_ms / 1000)
    done.set()
    if worker.is_alive() or "page" not in box:
        return
    page = box["page"]
    lst = page["messages"] if isinstance(page, dict) and isinstance(page.get("messages"), list) else \
        page if isinstance(page, list) else []
    first: dict[str, Any] = {}
    for rec in lst:
        m = _parse_quiet(rec.get("content") if isinstance(rec, dict) else None)
        if m is None:
            continue
        key = f"{js.string(js.get(m['metadata'], 'FROM'))}|{js.string(js.get(m['metadata'], 'MESSAGE-ID'))}"
        if key not in first or js.number(js.get(rec, "seq")) < js.number(first[key]):
            first[key] = js.get(rec, "seq")
    for c in mine:
        meta = c["msg"]["metadata"]
        seq = first.get(f"{js.string(js.get(meta, 'FROM'))}|{js.string(js.get(meta, 'MESSAGE-ID'))}", js.UNDEFINED)
        if seq is not js.UNDEFINED and js.number(seq) < js.number(js.get(c["rec"], "seq")):
            c["retransmitOf"] = seq


# Alert keywords: reasons to stop waiting on a message NOT addressed to this
# session. Whole-token, case-insensitive, over the full text (metadata and
# body — PR numbers live in REFERENCES). 3+ characters (shorter fires on
# nearly everything), at most 8 per arm, and a message from this session's
# own address never counts: a session must not wake on its own echo.
KEYWORD_MIN = 3
KEYWORD_MAX = 8


class KeywordError(ValueError):
    pass


def check_keywords(keywords: list | None = None, t: i18n.Printer | None = None) -> list[str]:
    t = t or en()
    seen: list[str] = []
    for k in keywords or []:
        if not isinstance(k, str) or len(k) < KEYWORD_MIN:
            raise KeywordError(t("keyword.too-short", {"keyword": js.stringify(k), "min": KEYWORD_MIN}))
        if k in seen:
            continue
        if len(seen) >= KEYWORD_MAX:
            raise KeywordError(t("keyword.too-many", {"max": KEYWORD_MAX}))
        seen.append(k)
    return seen


_TOKEN_SPLIT = re.compile(r"[^a-z0-9_-]+")


def keyword_hit(text: str, keywords: list[str], own_address: str | None) -> bool:
    if not keywords or not text:
        return False
    tokens = {x for x in _TOKEN_SPLIT.split(text.lower()) if x}
    if own_address:
        # Each TOKEN of the own address goes: the address is never one
        # token, and a keyword naming another session's instance half must
        # still fire on that session's message.
        for x in _TOKEN_SPLIT.split(own_address.lower()):
            tokens.discard(x)
    return any(k.lower() in tokens for k in keywords)


# ── THE HOLD (2026-09-16) ────────────────────────────────────────────
# A plan is written from the context the session had when it entered plan
# mode; a delivery mid-plan is context it was not asked to absorb. The
# harness cannot pause notifications, but a delivery is one only because
# this watch polls and prints — so while the session plans, the watch does
# not poll. The plan-hold hook writes <pid>.json under the login's own
# hold directory; the account is held while ANY marker names a live harness
# of this login: the pid answers a signal as this uid (EPERM is another
# login's process) and, when both sides know it, has the start time the
# marker recorded (a reused pid is not the harness). The directory and each
# file must be this login's — another login must not hold or release this
# inbox. Held is a line on stderr, never stdout.

def hold_dir(home: str | None = None) -> str:
    return os.environ.get("AGENT_FABRIC_HOLD_DIR",
                          os.path.join(os.path.expanduser("~") if home is None else home, ".cache", "agent-fabric", "hold"))


def pid_start(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as fh:
            fields = re.sub(r".*\) ", "", fh.read(), count=1, flags=re.S).split(" ")
    except OSError:
        return ""
    return fields[19] if len(fields) > 19 else ""


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, OverflowError, ValueError):
        return False
    return True


def hold_status(directory: str | None = None, is_alive: Callable[[int], bool] = pid_alive,
                start_of: Callable[[int], str] = pid_start, uid: int | None = None,
                t: i18n.Printer | None = None) -> dict:
    directory = hold_dir() if directory is None else directory
    uid = os.getuid() if uid is None else uid
    t = t or en()
    try:
        st = os.lstat(directory)
    except OSError:
        return {"held": False, "reason": t("held.no-directory"), "sessions": []}
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        return {"held": False, "reason": t("held.not-a-directory"), "sessions": []}
    if st.st_uid != uid:
        return {"held": False, "reason": t("held.not-this-login"), "sessions": []}
    sessions, stale = [], []
    for name in os.listdir(directory):
        if not re.fullmatch(r"\d+\.json", name, re.ASCII):
            continue
        file = os.path.join(directory, name)
        try:
            if os.lstat(file).st_uid != uid:
                stale.append(t("held.stale-not-this-login", {"name": name}))
                continue
            with open(file, encoding="utf-8") as fh:
                m = json.load(fh)
        except (OSError, ValueError):
            stale.append(t("held.stale-unreadable", {"name": name}))
            continue
        m = m if isinstance(m, dict) else {}
        pid = m.get("pid")
        whole = (isinstance(pid, int) and not isinstance(pid, bool)) or (isinstance(pid, float) and pid.is_integer())
        if not whole or pid <= 0:
            stale.append(t("held.stale-no-pid", {"name": name}))
            continue
        pid = int(pid)
        if not is_alive(pid):
            stale.append(t("held.stale-gone", {"name": name, "pid": pid}))
            continue
        now = start_of(pid)
        if m.get("start") and now and js.string(m["start"]) != js.string(now):
            stale.append(t("held.stale-reused", {"name": name, "pid": pid}))
            continue
        sessions.append({"pid": pid, "session_id": m.get("session_id"), "since": m.get("since")})
    if not sessions:
        return {"held": False, "reason": "; ".join(stale) if stale else t("held.no-marker"), "sessions": sessions}
    return {"held": True, "sessions": sessions}


HOLD_POLL_MS = 1000

# THE JOURNAL (ADR-041 rule 4): the messages addressed to this session are
# kept in its journal before the page is acknowledged, so a message is
# never let go by the carrier and then lost between here and the session.
# If the journal cannot take them they are neither acknowledged nor shown:
# the carrier shows them again, after JOURNAL_RETRY_MS so a broken journal
# does not spin. Others' traffic is acknowledged as before, never journaled.
JOURNAL_RETRY_MS = 30000


def _episodic():
    """tools/fabric/episodic.py — its own CLI, run in this process: the
    same exit codes and the same one-line reasons it gave as a process."""
    tools = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import episodic  # noqa: E402 — the sibling module, loaded when a page needs it
    return episodic


def run_episodic(args: list[str], stdin: str) -> dict:
    """{status, stdout, stderr} of `episodic.py <args>` with stdin, in this
    process. An exception that escapes it is a journal that did not answer;
    an interrupt or an exit is not."""
    out, err = io.StringIO(), io.StringIO()
    saved = sys.stdin
    try:
        sys.stdin = io.StringIO(stdin)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = _episodic().main(args)
    except (KeyboardInterrupt, SystemExit):
        # Read as "journal failed", a forwarded SIGINT left the watch running.
        raise
    except BaseException as e:  # noqa: BLE001 — anything the journal raised is its non-answer
        status, err = 1, io.StringIO(err.getvalue() + f"episodic: {type(e).__name__}: {e}\n")
    finally:
        sys.stdin = saved
    return {"status": status if isinstance(status, int) else 1, "stdout": out.getvalue(), "stderr": err.getvalue()}


def journal_inbound(records: list[dict], who: dict | None, run: Callable[[list[str], str], dict] = run_episodic) -> dict:
    where = [*(["--project", who["project"]] if who and who.get("project") else []),
             *(["--working-copy", who["working_copy"]] if who and who.get("working_copy") else [])]
    lines = [js.stringify({"content": r.get("content"),
                           "seq": js.coalesce(js.get(r, "seq"), None),
                           "ts": js.coalesce(js.get(r, "ts_full"), js.get(r, "timestamp"), js.get(r, "ts"), None)})
             for r in records]
    r = run(["gzcoord-in", *where], "\n".join(lines) + "\n")
    said = [x for x in str(r.get("stderr") or "").strip().split("\n") if x]
    if r.get("status") != 0:
        return {"ok": False, "reason": said[-1] if said else f"episodic: the journal did not answer (exit {r.get('status')})"}
    return {"ok": True, "said": said}


# ── the wait ─────────────────────────────────────────────────────────

def wait_loop(fetch_page: Callable[[int, threading.Event], Any], ack: Callable[[Any], Any], wait_total: float,
              for_me_fn: Callable[[dict], bool] | None = None, keywords: list[str] | None = None,
              own_address: str | None = None, held: Callable[[], bool] = lambda: False,
              on_hold: Callable[[bool], None] = lambda h: None, hold_poll_ms: int = HOLD_POLL_MS,
              sleep: Callable[[float], None] = lambda ms: time.sleep(ms / 1000),
              journal: Callable[[list[dict]], dict] | None = None,
              on_journal_fail: Callable[[str, int], None] = lambda reason, n: None,
              journal_retry_ms: int = JOURNAL_RETRY_MS) -> dict:
    """One arm of the waiter. `delivered` iff some slice carried a message
    for this session. Every slice's messages are acknowledged before the
    loop continues or returns — an acknowledgement means "shown this
    position", not "read the body". `held` is consulted before every slice,
    once a poll interval during one, and once more when it returns: a hold
    that begins mid-slice abandons the fetch, a page that landed with the
    hold is dropped unread (nothing acknowledged, the relay re-shows it),
    and the loop polls nothing until the hold clears. A retired HELLO or
    GOODBYE (SPEC §8) an old session still sends is acknowledged and never
    delivered, not even listed: presence is the control plane's to answer
    (ADR-030), and on a busy day the announcements were most of what every
    watch printed (the owner, 2026-09-25)."""
    for_me_fn = for_me_fn or (lambda msg: False)
    keywords = keywords or []
    waited = 0.0
    hit = None
    was_held = False
    while True:
        if held():
            if not was_held:
                on_hold(True)
                was_held = True
            sleep(hold_poll_ms)
            continue
        if was_held:
            on_hold(False)
            was_held = False
        slice_ = 1 if wait_total == 0 else min(55, max(1, wait_total - waited))
        abort = threading.Event()
        box: dict = {}

        def fetch() -> None:
            try:
                box["page"] = fetch_page(slice_, abort)
            except BaseException as e:  # noqa: BLE001 — carried to the waiting side
                box["error"] = e

        worker = threading.Thread(target=fetch, daemon=True)
        worker.start()
        while True:
            worker.join(hold_poll_ms / 1000)
            if not worker.is_alive():
                break
            if held():
                abort.set()   # the slice is abandoned: nothing read is acknowledged
                break
        if abort.is_set():
            page = {"messages": []}
        elif "error" in box:
            abort.set()
            raise box["error"]
        else:
            page = box["page"]
        abort.set()
        if held():
            page = {"messages": []}   # landed as the hold began: unread, unacknowledged, re-shown later
        waited += slice_
        classified, retired = [], []
        delivered = False
        for rec in (page.get("messages") if isinstance(page, dict) else None) or []:
            try:
                msg = gzmsg.parse(rec["content"])
            except (gzmsg.NotGzcoord, AttributeError, TypeError, KeyError):
                msg = None   # not GZCOORD/1: never addressed
            if msg and msg["type"] in gzmsg.RETIRED_TYPES:
                retired.append(rec)
                continue
            is_mine = bool(for_me_fn(msg)) if msg else False
            classified.append({"rec": rec, "msg": msg, "isMine": is_mine})
            delivered = delivered or is_mine
        mine = [c for c in classified if c["isMine"]]
        if journal and mine:
            kept = journal([c["rec"] for c in mine])
            if not kept.get("ok"):
                # Held: not shown, not acknowledged — only if nothing after
                # them is acknowledged either. The relay keeps one cursor per
                # consumer and an acknowledgement moves it to that record's
                # seq, so acknowledging a later record would pass the held
                # one for good (review of #78). What precedes the first held
                # record is acknowledged; a seq that cannot be compared
                # acknowledges none.
                on_journal_fail(kept.get("reason"), len(mine))
                seqs = [js.number(js.get(c["rec"], "seq")) for c in mine]
                first_held = math.nan if any(math.isnan(s) for s in seqs) else min(seqs)

                def before(rec: dict) -> bool:
                    return math.isfinite(first_held) and js.number(js.get(rec, "seq")) < first_held

                passed = [c for c in classified if not c["isMine"] and before(c["rec"])]
                for rec in [*[r for r in retired if before(r)], *[c["rec"] for c in passed]]:
                    try:
                        ack(rec.get("id"))
                    except Exception:  # noqa: BLE001 — re-read on the next arm
                        pass
                # Acknowledged now, so never read again: a keyword among them
                # is the exit reason here or nowhere (review of #78).
                passed_hit = next((c["rec"] for c in passed
                                   if c["msg"] and keyword_hit(c["rec"].get("content"), keywords, own_address)), None)
                def held_result(hit: Any = None) -> dict:
                    # Built at each return: `waited` is the count when it returns.
                    return {"classified": passed, "waited": waited, "delivered": False, "keywordHit": hit,
                            "othersPassed": len(passed), "journalFailed": kept.get("reason")}
                if passed_hit:
                    return held_result(passed_hit)
                # A bounded wait ends within its budget, the hold said; the
                # watch retries until the journal takes them.
                if wait_total == 0 or waited >= wait_total:
                    return held_result()
                pause = min(journal_retry_ms, (wait_total - waited) * 1000)
                sleep(pause)
                waited += math.ceil(pause / 1000)
                if waited >= wait_total:
                    return held_result()
                continue
        for rec in retired:
            try:
                ack(rec.get("id"))
            except Exception:  # noqa: BLE001 — re-read on the next arm
                pass
        for c in classified:
            try:
                ack(c["rec"].get("id"))
            except Exception:  # noqa: BLE001 — the next arm re-shows it
                pass
        # A keyword hit stops the wait on a message NOT addressed here; a
        # delivered message wins the exit; a message from this session's own
        # address never hits.
        if not delivered and not hit:
            for c in classified:
                if not c["isMine"] and c["msg"] and keyword_hit(c["rec"].get("content"), keywords, own_address):
                    hit = c["rec"]
                    break
        if delivered or hit or wait_total == 0 or waited >= wait_total:
            return {"classified": classified, "waited": waited, "delivered": delivered, "keywordHit": hit,
                    "othersPassed": len([c for c in classified if not c["isMine"]])}
        # Nothing for this session, no keyword hit: the cursor is past the
        # slice, and the remaining budget keeps waiting.


# ── one delivery, as the session reads it ────────────────────────────
# THE NOTIFICATION CAP. What the watch prints reaches the session as a
# Monitor notification, and the harness shows about 3,000 characters of one
# event, then "...(truncated)"; the rest lives only in the task's output
# file, which the session does not know to open (architect-cto, 2026-09-16,
# four deliveries cut inside REQUEST or VERIFIED; measured at 3,017
# characters shown). So --follow renders under a cap of its own: a delivery
# that fits is printed whole; one that does not keeps every metadata line,
# cuts the body at a line boundary, and says where it cut and how to read
# the whole message. The drain is not a notification and is rendered whole.
# Lengths are JavaScript's (UTF-16 units), as the cap was measured.
NOTIFICATION_CAP = 2800
# The name on PATH, never a path through an expansion: a session told to
# run it is not asked for approval (runtime/claude-code/commands.json).
REPLAY_CMD = "gzcoord-inbox --replay"
MAX_FLAG_LINES = 4
_SECTION = re.compile(r"[A-Z][A-Z0-9-]*:")


def cut_at_line(text: str, max_units: int) -> str:
    """Always at a line boundary: a body whose first line alone is longer
    than the budget keeps nothing of it (the notice says where to read)."""
    if js.length(text) <= max_units:
        return text
    nl = js.last_newline_at_or_before(text, max_units)
    return "" if nl < 0 else text[:nl]


def _drop_final_newline(s: str) -> str:
    return s[:-1] if s.endswith("\n") else s


def split_message(text: str) -> dict:
    """The metadata block ends at the first section marker (SPEC §6: the
    blank line before it MAY be absent), not at a blank line."""
    lines = _drop_final_newline(text.replace("\r\n", "\n")).split("\n")
    at = next((k for k, line in enumerate(lines) if k > 0 and _SECTION.fullmatch(line)), -1)
    if at < 0:
        return {"meta": re.sub(r"\n+$", "", "\n".join(lines)), "body": ""}
    meta_end = at
    while meta_end > 0 and lines[meta_end - 1] == "":
        meta_end -= 1
    return {"meta": "\n".join(lines[:meta_end]), "body": "\n".join(lines[at:])}


def render(res: dict, me: dict, channel: str, taxonomy: gzmsg.Taxonomy | None, cap: float = math.inf,
           t: i18n.Printer | None = None, reminder: str = "") -> str:
    t = t or en()
    mine, others = [], []
    for c in res["classified"]:
        rec, msg = c["rec"], c.get("msg")
        if not msg:
            others.append({"rec": rec, "line": t("inbox.not-a-message", {"id": js.get(rec, "id"),
                                                                       "sender": js.get(rec, "sender")})})
            continue
        (mine if c["isMine"] else others).append({"rec": rec, "msg": msg,
                                                   "retransmitOf": c.get("retransmitOf", js.UNDEFINED)})
    # The reminder rides the head line and nothing else: the one line read
    # on every drain and every delivery; the cap measures the head as it
    # prints.
    who = f"{me['address']}{' (' + me['slug'] + ')' if me.get('slug') else ''}"
    head = t("inbox.head", {"who": who, "mine": len(mine), "others": len(others), "channel": channel}) + reminder
    parts = []
    for p in mine:
        rec = p["rec"]
        # The message has arrived: the terminal-copy width warning does not apply.
        v = gzmsg.validate(rec["content"], taxonomy=taxonomy, max_columns=0, t=t)
        flags = [*(t("delivery.invalid", {"detail": e}) for e in v["errors"]),
                 *(t("delivery.warning", {"detail": w}) for w in v["warnings"])]
        # Only under a cap: the drain shows every validator line.
        if math.isfinite(cap) and len(flags) > MAX_FLAG_LINES:
            flags = [*flags[:MAX_FLAG_LINES], t("delivery.flags-more", {"n": len(flags) - MAX_FLAG_LINES})]
        if p["retransmitOf"] is not js.UNDEFINED:
            flags = [t("delivery.retransmission", {"seq": p["retransmitOf"]}), *flags]
        title = t("delivery.title", {"seq": js.get(rec, "seq"), "sender": js.get(rec, "sender"),
                                     "when": js.get(rec, "timestamp")})
        if flags:
            title += "\n    " + "\n    ".join(flags)
        text = _drop_final_newline(rec["content"])
        parts.append({"rec": rec, "title": title, "text": text, **split_message(text)})
    other_lines = [f"  {o['line'] if 'line' in o else one_line(o['msg'], t)}" for o in others]
    others_block = ["", t("inbox.others-header"), *other_lines] if others else []
    whole = "\n".join([head, *[x for p in parts for x in ("", p["title"], "```text", p["text"], "```")], *others_block])
    if js.length(whole) <= cap:
        return whole

    # Over the cap. Metadata whole and others listed if that fits; the
    # bodies share what is left, each cut at a line and ending with the
    # replay command for its seq. Nothing is claimed to be elsewhere.
    def seqs(lst: list) -> str:
        return t("cap.seq-range", {"first": js.get(lst[0]["rec"], "seq"), "last": js.get(lst[-1]["rec"], "seq")}) \
            if lst else ""

    def notice(p: dict) -> str:
        return t("cap.notice", {"replay_cmd": REPLAY_CMD, "seq": js.get(p["rec"], "seq")})

    others_count = ["", t("cap.others-count", {"count": len(others), "range": seqs(others)})] if others else []

    def layout(tail: list[str]) -> int:
        return js.length("\n".join([head, *[x for p in parts for x in ("", p["title"], "```text", p["meta"], "",
                                                                         notice(p), "```")], *tail]))

    others_tail = others_block
    if layout(others_tail) > cap:
        others_tail = others_count
    fixed = layout(others_tail)
    if fixed > cap:
        # Too many messages for one notification: one line each, read by
        # seq, and the tail says how many lines this listing dropped.
        lines = [head, t("cap.by-seq", {"replay_cmd": REPLAY_CMD})]
        rows = [t("cap.row", {"seq": js.get(p["rec"], "seq"), "line": one_line(gzmsg.parse(p["rec"]["content"]), t)})
                for p in parts]

        def tail_for(n: int) -> str:
            return t("cap.more-for-you", {"n": len(parts) - n, "range": seqs(parts[n:])}) if n < len(parts) else ""

        others_line = t("cap.and-others", {"count": len(others), "range": seqs(others)}) if others else ""
        n = 0
        while n < len(rows) and js.length("\n".join(x for x in [*lines, *rows[:n + 1], tail_for(n + 1), others_line]
                                                    if x)) <= cap:
            n += 1
        return "\n".join(x for x in [*lines, *rows[:n], tail_for(n), others_line] if x)
    budget = int(cap - fixed)
    shares = [0] * len(parts)
    # shortest bodies first: what they do not need goes to the longer ones
    order = sorted(range(len(parts)), key=lambda i: js.length(parts[i]["body"]))
    for k, i in enumerate(order):
        share = budget // (len(order) - k)
        take = min(share, js.length(parts[i]["body"]) + 2)
        shares[i] = take
        budget -= take
    out = [head]
    for i, p in enumerate(parts):
        cut = cut_at_line(p["body"], max(0, shares[i] - 2))
        fits = js.length(cut) >= js.length(p["body"])
        out.extend(["", p["title"], "```text", p["text"] if fits else p["meta"] + ("\n\n" + cut if cut else ""),
                    *([] if fits else ["", notice(p)]), "```"])
    return "\n".join([*out, *others_tail])


# ── the command ──────────────────────────────────────────────────────

class _Exit(Exception):
    def __init__(self, code: int):
        super().__init__(code)
        self.code = code


def _arg_after(argv: list[str], flag: str) -> Any:
    i = argv.index(flag) if flag in argv else -1
    return (argv[i + 1] if i + 1 < len(argv) else js.UNDEFINED) if i >= 0 else None


def main(argv: list[str]) -> int:
    wait_given = "--wait" in argv
    follow = "--follow" in argv
    replay_given = "--replay" in argv
    replay_which = _arg_after(argv, "--replay")
    history_given = "--history" in argv
    history_arg = _arg_after(argv, "--history")
    history_from = js.number(history_arg) if history_given and history_arg is not js.UNDEFINED \
        and not history_arg.startswith("--") else None
    wait_total = 0.0
    if wait_given:
        n = js.number(_arg_after(argv, "--wait"))
        wait_total = n if js.truthy_number(n) else 1800.0
    # Who this session is (the login) and which project it works in — the
    # second selects the integration: relay, channel, where the token and
    # runtime live, in the project's WORKING COPY.
    who = gzmsg.whoami()
    # From here every line is this login's: English, or the locale its name
    # ends in when that locale has an active dictionary (i18n).
    t = i18n.t_for(who)
    reminder = i18n.locale_reminder(who)
    # --keyword K, validated BEFORE the arm starts (a bad one refused at arm
    # time costs nothing), after `t` so the refusal reads in the login's
    # language (blind review F3 on PR #28).
    keywords = check_keywords([argv[i + 1] if i + 1 < len(argv) else js.UNDEFINED
                               for i, a in enumerate(argv) if a == "--keyword"], t)
    if replay_given and not replay_which:
        print(t("replay.usage"), file=sys.stderr)
        return 1
    if history_given and history_from is not None and not js.is_integer(history_from):
        print(t("history.usage"), file=sys.stderr)
        return 1
    if "--held" in argv:
        h = hold_status(t=t)
        unknown = t("held.unknown")
        if h["held"]:
            sessions = ", ".join(t("held.session", {"session": x["session_id"] if x["session_id"] is not None else unknown,
                                                    "pid": x["pid"],
                                                    "since": x["since"] if x["since"] is not None else unknown})
                                 for x in h["sessions"])
            print(t("held.held", {"agent": who["agent"], "sessions": sessions}))
        else:
            print(t("held.not-held", {"reason": h["reason"]}))
        return 0 if h["held"] else 1
    root = inbox_root(who)
    cfg = integration_config(who.get("project"), os.environ, t)
    # Not configured is not an error at a session start, and not a guess.
    if not cfg["configured"]:
        print(t("start.skipping", {"reason": cfg["reason"]}), file=sys.stderr)
        return 0
    try:
        assert_not_control_channel(cfg["channel"], t)
    except ControlChannel as e:
        print(t("start.error", {"detail": str(e)}), file=sys.stderr)
        return 2
    relay_url, channel = cfg["relay_url"], cfg["channel"]
    # What this session owns first: the hosting working copy starts its
    # relay here, so a session restart is also the relay's.
    up = ensure_relay(relay_runtime_dir(cfg), relay_url, t)
    if up.get("started"):
        print(t("start.relay-started-unit", {"unit": up["unit"]}) if up.get("unit")
              else t("start.relay-started-pid", {"pid": up.get("pid")}), file=sys.stderr)
    elif up.get("note"):
        print(t("start.error", {"detail": up["note"]}), file=sys.stderr)
    tok = token(root, cfg)
    if not tok:
        print(t("start.no-token", {"token_file": cfg["token_env_file"] if cfg.get("token_env_file") is not None
                                   else t("config.no-token-file")}), file=sys.stderr)
        return 0
    tax_path = gzmsg.find_taxonomy(root)
    taxonomy = gzmsg.load_taxonomy(tax_path) if tax_path else None
    me = identity(who, taxonomy)
    if me.get("roleError"):
        print(t("start.error", {"detail": me["roleError"]}), file=sys.stderr)
    state = {"tok": tok}

    def with_fresh_token(fn: Callable[[str], Any]) -> Any:
        """Once: a refused token is retried with the synced file's value
        when that differs from what the environment carried."""
        try:
            return fn(state["tok"])
        except RelayError as e:
            fresh = synced_token() if e.status in (401, 403) else None
            if fresh and fresh != state["tok"]:
                state["tok"] = fresh
                print(t("start.token-retry"), file=sys.stderr)
                return fn(state["tok"])
            raise

    if history_given:
        try:
            return with_fresh_token(lambda tk: history(tk, relay_url, channel, history_from, me, t))
        except Exception as e:  # noqa: BLE001 — any failure of the read is the relay's line
            x = explain_relay_error(e, relay_url, t)
            print(x["line"], file=sys.stderr)
            return x["code"] or 1
    if replay_which:
        try:
            return with_fresh_token(lambda tk: replay(tk, relay_url, channel, replay_which, me, t, "--json" in argv))
        except Exception as e:  # noqa: BLE001
            x = explain_relay_error(e, relay_url, t)
            print(x["line"], file=sys.stderr)
            return x["code"] or 1

    # Drain mode spends 1 s on the cursor page and lists everything; wait
    # mode chains slices until a message ADDRESSED TO THIS SESSION lands,
    # passing others' traffic through acknowledged and unprinted.
    def ack(message_id: Any) -> Any:
        return api(state["tok"], "/api/ack", relay_url, method="POST",
                   body=js.stringify({"consumer_id": me["address"], "channel": channel, "message_id": message_id}))

    def fetch_page(slice_: float, abort: threading.Event) -> Any:
        q = urllib.parse.urlencode({"channel": channel, "consumer_id": me["address"],
                                    "timeout_seconds": js.string(slice_), "limit": "50"})
        return api(state["tok"], f"/api/wait?{q}", relay_url, timeout=slice_ + API_TIMEOUT)

    def held() -> bool:
        return hold_status(t=t)["held"]

    # Each key literally beside its t(: the i18n suite reads the source for
    # them, and a key built in an expression is one its guard cannot see.
    def on_hold(h: bool) -> None:
        print(t("watch.held") if h else t("watch.hold-released"), file=sys.stderr, flush=True)

    journal = None if os.environ.get("GZCOORD_JOURNAL") == "off" else (lambda recs: journal_inbound(recs, who))
    cause = {"reason": None}

    def on_journal_fail(reason: str, n: int) -> None:
        # The journal speaks for itself, untranslated, on stdout in the
        # watch, so the held messages reach the session.
        if reason == cause["reason"]:
            return
        cause["reason"] = reason
        print(f"gzcoord: {n} message(s) addressed to you are held, not shown: your journal could not keep them"
              f" ({reason}); they are shown once it can (ADR-041), or with GZCOORD_JOURNAL=off", flush=True)

    def fetch_recent(_done: threading.Event) -> Any:
        return api(state["tok"], "/api/messages?" + urllib.parse.urlencode(
            {"channel": channel, "limit": str(HISTORY_WINDOW), "full": "1"}), relay_url,
            timeout=RETRANSMISSION_LOOKUP_MS / 1000)

    def mine_fn(msg: dict) -> bool:
        return for_me(msg, me)

    if follow:
        # The watch. Each arm waits an hour of slices; a delivery is printed
        # and the next arm starts at once; a quiet hour starts the next arm
        # silently. Transport trouble is one line each way; a refused token
        # ends the watch with exit 4 so the harness reports it once.
        down = False
        while True:
            try:
                r = with_fresh_token(lambda _tk: wait_loop(fetch_page, ack, 3600, mine_fn, [], me["address"], held,
                                                           on_hold, journal=journal, on_journal_fail=on_journal_fail))
            except Exception as e:  # noqa: BLE001 — every failure of an arm is the relay's, said once
                x = explain_relay_error(e, relay_url, t)
                if x["code"] == 4:
                    print(x["line"], file=sys.stderr)
                    return 4
                if not down:
                    print(t("watch.relay-down", {"relay_url": relay_url}), flush=True)
                    down = True
                time.sleep(30)
                continue
            if down:
                print(t("watch.relay-back"), flush=True)
                down = False
            if r["delivered"]:
                cause["reason"] = None
                mark_retransmissions(r["classified"], fetch_recent)
                print(render(r, me, channel, taxonomy, cap=NOTIFICATION_CAP, t=t, reminder=reminder), flush=True)

    try:
        res = with_fresh_token(lambda _tk: wait_loop(fetch_page, ack, wait_total, mine_fn, keywords, me["address"],
                                                     journal=journal, on_journal_fail=on_journal_fail))
    except Exception as e:  # noqa: BLE001
        x = explain_relay_error(e, relay_url, t)
        print(x["line"], file=sys.stderr)
        return x["code"]
    if res.get("keywordHit") and wait_given:
        hit = res["keywordHit"]
        m = next((c for c in res["classified"] if c["rec"].get("id") == hit.get("id")), None)
        print(t("keyword.hit", {"channel": channel, "keywords": ", ".join(keywords)}))
        print(f"  {one_line(m['msg'], t) if m and m.get('msg') else t('keyword.unparsable', {'id': js.get(hit, 'id'), 'sender': js.get(hit, 'sender')})}")
        raise _Exit(3)
    if not res["delivered"] and wait_given:
        print(t("wait.nothing", {"channel": channel, "waited": res["waited"], "others_passed": res["othersPassed"]}))
    if not res["delivered"]:
        return 0
    mark_retransmissions(res["classified"], fetch_recent)
    print(render(res, me, channel, taxonomy, t=t, reminder=reminder))
    # The cursor is already past everything shown: wait_loop acknowledges
    # every slice it sees, delivered or passed.
    return 0


def run(argv: list[str]) -> int:
    """The command: main(), with the Node's last resort — NOT through the
    dictionary, since what failed may BE the dictionary — one line and exit
    0, on a path whose whole contract is one line and exit 0 (blind review
    F1 on PR #28)."""
    try:
        return main(argv)
    except _Exit as e:
        return e.code
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # noqa: BLE001 — the contract's last resort
        print(f"gzcoord inbox: {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
