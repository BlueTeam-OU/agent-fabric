#!/usr/bin/env python3
"""tools/fabric/plan_hold.py — the Claude Code hook (PreToolUse on every tool, UserPromptSubmit, SessionEnd) that
holds this account's GZCoord inbox while a session is planning, behind runtime/claude-code/hooks/plan-hold.sh
(Wave 9 batch 7, ADR-040 §7).

Contract, frozen from the shell script and pinned by tests/test_plan_hold_cli.py:
  stdin   the hook payload: hook_event_name, permission_mode, agent_id (null for the session itself) and
          session_id are read; anything else is ignored. Empty, malformed or event-less input does nothing
  env     CLAUDE_PID (the harness; the hook's parent when unset or empty), CLAUDE_CODE_SESSION_ID (before the
          payload's session_id), AGENT_FABRIC_HOLD_DIR (else $HOME/.cache/agent-fabric/hold)
  stdout  nothing, ever; nothing on stderr
  exit    0 always: a hook that cannot run must not turn a planning session into a broken one
  writes  <hold dir>/<pid>.json, mode 0600, {"session_id", "pid", "start", "since"}; removes this session's
          own marker, and the markers of harnesses that are gone

A plan is written from the context the session has when it enters plan mode; a delivery landing in the middle
of it is new context the plan was not asked to absorb. The harness gives no way to pause notifications, but the
whole delivery path is ours: a message becomes a notification only because the watch (gzcoord-inbox
--until-delivery, in tools/fabric/gzcoord/inbox.py) polls the relay and prints it. So the session says
"planning" through a marker, and the watch does not poll while a marker is live: nothing is consumed, the relay
keeps the cursor, and the first poll after the plan is approved delivers everything at once.

One marker per SESSION, naming the harness pid (CLAUDE_PID, exported to hooks; the hook's parent IS that
process, verified on 2.1.273), its start time from /proc, and the session id. The account is held while ANY
marker names a live harness of this login — two sessions planning under one login hold together and release
separately (the first review found a single file per login released the sibling's hold). Under $HOME, not /tmp:
another login could pre-create a per-uid name under /tmp and own the directory, and then hold or release this
login's inbox (the same review, P1); the home is the login's. The directory must be ours, mode 700 and not a
symlink, or the hook writes nothing.

Every hook event carries permission_mode (verified live 2.1.273: UserPromptSubmit and PreToolUse; SessionStart
does not), so the marker follows the mode rather than the EnterPlanMode/ExitPlanMode calls — a rejected plan
stays in plan mode, and a plan entered by launch flag never calls EnterPlanMode. A subagent's event (agent_id
present) is not the session's mode and is ignored. SessionEnd clears the session's own marker; every event
sweeps markers whose harness is gone (dead pid, or a pid reused by a process with another start time).
"""
import glob
import json
import os
import re
import stat
import sys
import time

POSITIVE = re.compile(r"[1-9][0-9]*")


def value(payload: object, key: str) -> str:
    """The field as jq's `.key // ""` read it; a value that is not a string is not an event name, mode or id."""
    found = payload.get(key) if isinstance(payload, dict) else None
    return found if isinstance(found, str) else ""


def is_subagent(payload: object) -> bool:
    """A null agent_id is the session itself; the harness sent that, and a missing one, for the session."""
    found = payload.get("agent_id") if isinstance(payload, dict) else None
    return found not in (None, False, "")


def start_of(pid: str) -> str:
    """The start time of a pid (clock ticks since boot): /proc/<pid>/stat field 22, read after the ')' that ends
    the command name. Empty off Linux."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as fh:
            return fh.read().rsplit(") ", 1)[1].split()[19]
    except (OSError, IndexError):
        return ""


def alive(pid: str, start: str) -> bool:
    """A positive pid (0 would signal the hook's own process group and succeed) that answers kill -0 as THIS
    login (EPERM is another login's process, never our harness) and, when both sides know it, was started when
    the marker says."""
    if not POSITIVE.fullmatch(pid):
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, OverflowError):
        return False
    now = start_of(pid)
    return not start or not now or start == now


def text_of(found: object, empty: str) -> str:
    """jq's `(.k // empty) | tostring` of a marker's field."""
    if found in (None, False):
        return empty
    return json.dumps(found) if not isinstance(found, str) else found


def hold_directory(path: str) -> bool:
    """The directory: ours, 700, not a symlink — or nothing is written or read."""
    try:
        os.makedirs(path, mode=0o700, exist_ok=True)
        info = os.lstat(path)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
            return False
        if stat.S_IMODE(info.st_mode) != 0o700:
            os.chmod(path, 0o700)
    except OSError:
        return False
    return True


def sweep(directory: str, own: str) -> None:
    """A marker whose harness is gone is nobody's hold."""
    for path in glob.glob(os.path.join(glob.escape(directory), "*.json")):
        if path == own or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            doc = None
        doc = doc if isinstance(doc, dict) else {}
        if not alive(text_of(doc.get("pid"), "0"), text_of(doc.get("start"), "")):
            try:
                os.unlink(path)
            except OSError:
                pass


def hold(directory: str, marker: str, pid: str, session: str) -> None:
    """Written once: a marker already naming this pid stays."""
    if os.path.isfile(marker):
        return
    doc = {"session_id": session, "pid": int(pid), "start": start_of(pid), "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    import tempfile
    fd, tmp = tempfile.mkstemp(prefix=f".{pid}.", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, marker)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def handle(raw: bytes) -> None:
    try:
        payload = json.loads(raw)
    except ValueError:
        return
    event = value(payload, "hook_event_name")
    if not event or is_subagent(payload):
        return
    pid = os.environ.get("CLAUDE_PID") or str(os.getppid())
    session = os.environ.get("CLAUDE_CODE_SESSION_ID") or value(payload, "session_id")
    if not POSITIVE.fullmatch(pid):
        return
    home = os.environ.get("HOME")
    directory = os.environ.get("AGENT_FABRIC_HOLD_DIR") or (os.path.join(home, ".cache", "agent-fabric", "hold") if home else "")
    if not directory or not hold_directory(directory):
        return
    marker = os.path.join(directory, f"{pid}.json")
    sweep(directory, marker)
    if event != "SessionEnd" and value(payload, "permission_mode") == "plan":
        hold(directory, marker, pid, session)
    else:
        # Not planning, or ending: this session's own marker goes. Another live session's marker is its own.
        try:
            os.unlink(marker)
        except OSError:
            pass


def main() -> int:
    raw = sys.stdin.buffer.read()
    if raw.strip():
        try:
            handle(raw)
        except OSError:
            # A hold that cannot be written or cleared leaves the inbox as it was before this hook existed.
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
