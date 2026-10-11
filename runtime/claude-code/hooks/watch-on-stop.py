#!/usr/bin/env python3
"""runtime/claude-code/hooks/watch-on-stop.py — a session that is about to
go idle without a GZCoord inbox watch is sent back once to arm it.

Messages wake a session only through its watch (`gzcoord-inbox
--until-delivery`, a background shell the session runs itself, gzcoord-receive
§1). Two ways it went missing, both seen on 2026-10-11: a restarted session
ended its first turn without starting one, and the harness reaped an idle
session's background shells under memory pressure. session-start.py says
"arm it" only at the start; this is the same decision at the moment the
session would fall silent. Registered at user scope on Stop
(runtime/claude-code/user-settings.py).

A watch is "of this session" when a process whose command line is
gzcoord-inbox with --until-delivery, --follow or --wait (inbox-watch.py) descends from the session's
harness: the nearest ancestor of this hook named `claude` (session-state.py's
rule). The process table is read from /proc and passed in as `procs`, so a
test supplies its own.

It passes, printing nothing, when: stop_hook_active; no harness ancestor; the
session has no fabric binding or its project has no GZCoord integration
(the watch would exit 3 at once, and "start it" would loop); or it blocked
this session less than WINDOW_S ago. The last guard is the loop breaker: a
session that just started the watch, or could not, is not asked again. Any
internal error passes: a guard never stands in a session's way.
"""
from __future__ import annotations

import importlib.util
import json
import os
import pwd
import sys
import time

FABRIC_ROOT = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
WINDOW_S = 300
STATE_FILE = "watch-on-stop.json"
KEEP_S = 86400
COMMAND = "gzcoord-inbox --until-delivery"
REASON = ("No GZCoord inbox watch is running for this session, so no message can wake it. Before you finish, start it "
          "in the background: Bash(command: '" + COMMAND + "', run_in_background: true, timeout: 7200000, "
          "description: 'gzcoord inbox wait'), then end your turn. Never a Monitor, never a second watch.")


def read_procs(proc: str = "/proc") -> dict[int, tuple[int, str, str]]:
    """pid -> (ppid, comm, command line) for every process /proc shows."""
    out: dict[int, tuple[int, str, str]] = {}
    for d in os.listdir(proc):
        if not d.isdigit():
            continue
        try:
            with open(f"{proc}/{d}/stat", encoding="utf-8", errors="replace") as fh:
                raw = fh.read()
            with open(f"{proc}/{d}/cmdline", "rb") as fh:
                cmd = fh.read().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        out[int(d)] = (int(raw[raw.rindex(")") + 2:].split()[1]), raw[raw.index("(") + 1:raw.rindex(")")], cmd)
    return out


def harness_pid(procs: dict, pid: int) -> int | None:
    for _ in range(64):
        entry = procs.get(pid)
        if not entry:
            return None
        if entry[1] == "claude":
            return pid
        if entry[0] <= 1:
            return None
        pid = entry[0]
    return None


def is_watch(cmd: str) -> bool:
    # One predicate with session-start.py, loaded by path (inbox-watch.py).
    spec = importlib.util.spec_from_file_location(
        "fabric_inbox_watch", os.path.join(os.path.dirname(os.path.abspath(__file__)), "inbox-watch.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.is_watch(cmd)


def has_watch(procs: dict, session: int) -> bool:
    for pid, (_, _, cmd) in procs.items():
        if not is_watch(cmd):
            continue
        a = pid
        for _ in range(64):
            a = procs.get(a, (0, "", ""))[0]
            if a == session:
                return True
            if a <= 1:
                break
    return False


def state_path() -> str:
    login = pwd.getpwuid(os.getuid()).pw_name
    root = os.environ.get("AGENT_FABRIC_STATE_DIR")
    root = os.path.abspath(root) if root else os.path.join(
        os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state"), "agent-fabric")
    return os.path.join(root, "agents", login, STATE_FILE)


def recently_blocked(path: str, session: str, now: float) -> bool:
    try:
        with open(path, encoding="utf-8") as fh:
            return now - float(json.load(fh)[session]) < WINDOW_S
    except (OSError, ValueError, KeyError, TypeError):
        return False


def remember(path: str, session: str, now: float) -> None:
    try:
        with open(path, encoding="utf-8") as fh:
            seen = json.load(fh)
        seen = {k: v for k, v in seen.items() if now - float(v) < KEEP_S}
    except (OSError, ValueError, TypeError, AttributeError):
        seen = {}
    seen[session] = now
    tmp = f"{path}.{os.getpid()}"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(seen, fh)
    os.replace(tmp, path)


def integrated(cwd: str | None, session: str | None) -> bool:
    """Whether this session is fabric-launched and its project has GZCoord
    configured, by the inbox's own rule. Unlike session-start.py, an import
    that fails answers False: there the line may stay, here a block must
    be certain."""
    sys.path.insert(0, os.path.join(FABRIC_ROOT, "tools", "fabric"))
    try:
        spec = importlib.util.spec_from_file_location("fabric_identity", os.path.join(FABRIC_ROOT, "runtime", "identity.py"))
        identity = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(identity)
        ctx = identity.resolve_context(cwd=cwd or os.getcwd(), session=session)
        if not ctx.get("agent") or not ctx.get("project"):
            return False
        from gzcoord.inbox_parts.config import integration_config
        return bool(integration_config(ctx["project"])["configured"])
    except (Exception, SystemExit):  # noqa: BLE001 - identity refuses with SystemExit
        return False


def decide(payload: dict, procs: dict, now: float, path: str, is_integrated=integrated,
           own_pid: int | None = None) -> dict | None:
    if payload.get("stop_hook_active"):
        return None
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    session = harness_pid(procs, own_pid or os.getpid())
    if session is None or has_watch(procs, session):
        return None
    if recently_blocked(path, session_id, now) or not is_integrated(payload.get("cwd"), session_id):
        return None
    remember(path, session_id, now)
    return {"decision": "block", "reason": REASON}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if isinstance(payload, dict):
            out = decide(payload, read_procs(), time.time(), state_path())
            if out:
                print(json.dumps(out))
    except (Exception, SystemExit):  # noqa: BLE001 - a guard never stands in a session's way
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
