#!/usr/bin/env python3
"""runtime/claude-code/hooks/watch-nudge.py — a session whose GZCoord inbox
watch is down is told, after a tool call, to arm it again now.

watch-on-stop.py notices a missing watch only when the session would go idle.
On 2026-11-24 python-dev-01 left its watch down after each delivery for the
rest of a turn: a message that landed meanwhile woke nobody. This is the same
question asked mid-turn, as a PostToolUse hook for every tool. It refuses
nothing: its whole output is `hookSpecificOutput.additionalContext`, and it
exits 0 whatever happens.

The predicates are watch-on-stop.py's, loaded by path and never copied: which
process is the session (session_proc), whether a watch descends from it or
holds the login's one-watch lock (has_watch), the relay-down marker, and the
integration check. There is no relay or carrier probe: a per-tool hook cannot
afford a network wait, so a fresh relay-down marker simply keeps it silent
(the Stop hook probes before it asks).

Cost is bounded by a record per session, $STATE/watch-nudge.json:
  checked  when the process table was last read, or the session last re-armed.
           A call less than CHECK_S after it returns before reading /proc or
           loading the predicates: it never reminds, so a reminder can come at
           most every CHECK_S. A read that finds no harness ancestor is recorded
           too, so no path reads /proc on every call.
  down     the watch was seen down at that read
  nudged   this spell of "down" has been reminded, at nudged_at. A spell ends
           when a read sees the watch up, or when the call is the session's own
           re-arm (a Bash run of watch-on-stop.py's COMMAND): the watch it starts
           can end on a delivery while the session is idle, before any read sees
           it up. A spell reminded AGAIN_S ago is reminded again. A spell the
           hook stayed silent in (a fresh relay-down marker, no GZCoord) is not
           nudged, so it is reminded when the reason ends.
  A record that cannot be written costs the bound on reads, never the reminder.

Silent, printing nothing: a subagent's call (agent_id or agent_type: the watch
is the session's, and a subagent's `Bash` is not the place to start it); a
payload that is not a JSON object or has no session_id; no harness ancestor; no
fabric binding or no GZCoord integration (the watch would exit 3 at once and
"arm it" would loop); a fresh relay-down marker; any internal error.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK_S = 30
# A spell reminded this long ago is reminded again: reads happen only during tool calls, and a watch re-armed and then
# ended by a delivery while the session was idle can be down at every read (review of #705, F2).
AGAIN_S = 1800
KEEP_S = 86400
STATE_FILE = "watch-nudge.json"
# The tree this file is in: reading AGENT_FABRIC_ROOT would be a root lookup outside tools/fabric/roots.py (ADR-045 §5 rule 1).
FABRIC_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
_on_stop = None
_identity = None


def on_stop():
    """watch-on-stop.py, loaded by path (its name has a hyphen) and only when a read is due."""
    global _on_stop
    if _on_stop is None:
        spec = importlib.util.spec_from_file_location("fabric_watch_on_stop", os.path.join(HERE, "watch-on-stop.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _on_stop = mod
    return _on_stop


def identity():
    """runtime/identity.py, loaded by path on its own: the cached path must not pay for watch-on-stop.py's
    imports (urllib alone is about 80 ms), and it needs only the state directory and the one writer."""
    global _identity
    if _identity is None:
        spec = importlib.util.spec_from_file_location("fabric_identity", os.path.join(FABRIC_ROOT, "runtime", "identity.py"))
        _identity = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_identity)
    return _identity


def message(command: str) -> str:
    # The Bash(...) shape is watch-on-stop.py's REASON, word for word (a test pins that).
    return ("Your GZCoord inbox watch is not running, so a message that arrives now wakes nobody. Re-arm it now, "
            "before anything else: Bash(command: '" + command + "', run_in_background: true, timeout: 7200000, "
            "description: 'gzcoord inbox wait'). Never a Monitor, never a second watch.")


def read_state(path: str, now: float) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        return {k: v for k, v in raw.items()
                if isinstance(v, dict) and isinstance(v.get("checked"), (int, float)) and now - v["checked"] < KEEP_S}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def write_state(path: str, seen: dict) -> None:
    ident = identity()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    ident.atomic_write(path, json.dumps(seen), 0o600)


def keep(path: str, seen: dict) -> None:
    """write_state, whose failure (an unwritable state directory, a full disk) costs the bound on reads, never the
    reminder this call computed (review of #705, F1)."""
    try:
        write_state(path, seen)
    except Exception:  # noqa: BLE001 - a hook that refuses nothing also breaks nothing
        pass


def rearms(payload: dict) -> bool:
    """The call is the session's own re-arm: a Bash run of watch-on-stop.py's COMMAND. Prefiltered on the flag so an
    ordinary call does not pay for watch-on-stop.py's imports."""
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    return payload.get("tool_name") == "Bash" and isinstance(command, str) and "--until-delivery" in command \
        and on_stop().COMMAND in command


def state_path() -> str:
    return os.path.join(identity().agent_state_dir(), STATE_FILE)


def decide(payload: dict, now: float, path: str, procs=None, is_integrated=None, own_pid: int | None = None,
           run_dir: str | None = None) -> dict | None:
    """The hook's answer for one PostToolUse payload, None for silence. `procs` (a table, or a callable
    returning one), `is_integrated`, `own_pid` and `run_dir` are the tests' seams."""
    if payload.get("agent_id") or payload.get("agent_type"):
        return None
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    # Two parallel tool calls may both read before either writes; the worst case is one reminder twice.
    seen = read_state(path, now)
    mine = seen.get(session_id)
    # The re-arm itself ends the spell, whatever a later read sees: the watch it starts may end on a delivery before
    # any read finds it up (review of #705, F2).
    if rearms(payload):
        seen[session_id] = {"checked": now, "down": False, "nudged": False}
        keep(path, seen)
        return None
    if mine is not None and 0 <= now - mine["checked"] < CHECK_S:
        return None
    ws = on_stop()
    table = (procs() if callable(procs) else procs) if procs is not None else ws.read_procs()
    session = ws.harness_pid(table, own_pid or os.getpid())
    if session is None:
        # The read is recorded on this path too, or a session the walk cannot place reads /proc on every call
        # (review of #705, F1); what the record knew of the spell is kept.
        seen[session_id] = {**(mine or {"down": False, "nudged": False}), "checked": now}
        keep(path, seen)
        return None
    if ws.has_watch(table, session, run_dir):
        seen[session_id] = {"checked": now, "down": False, "nudged": False}
        keep(path, seen)
        return None
    nudged_at = mine.get("nudged_at", mine["checked"]) if mine else now
    nudged = bool(mine and mine.get("down") and mine.get("nudged")) and 0 <= now - nudged_at < AGAIN_S
    say = False
    if not nudged and not ws.relay_down(now, run_dir) \
            and (is_integrated or ws.integrated)(payload.get("cwd"), session_id):
        say = True
    seen[session_id] = {"checked": now, "down": True, "nudged": nudged or say,
                        **({"nudged_at": now} if say else {"nudged_at": nudged_at} if nudged else {})}
    keep(path, seen)
    if not say:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": message(ws.COMMAND)}}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if isinstance(payload, dict):
            out = decide(payload, time.time(), state_path())
            if out:
                print(json.dumps(out))
    except (Exception, SystemExit):  # noqa: BLE001 - a hook that refuses nothing also breaks nothing
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
