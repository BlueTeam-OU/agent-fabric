#!/usr/bin/env python3
"""runtime/claude-code/hooks/session-state.py — what each of this
account's Claude Code sessions is doing, kept where the account's control
agent reads it (ADR-029 rule 16).

Registered at user scope (user-settings.py) on SessionStart,
UserPromptSubmit, PreToolUse, PermissionRequest, Notification, Stop and
SessionEnd. Reads the hook payload on stdin and keeps, per session id,
one of:

    working   a prompt was submitted, or a tool is about to run
    blocked   the session waits on a person: a permission prompt, an
              input or elicitation dialog
    idle      the session started, a turn ended, or it sat waiting
    (gone)    the session ended: its entry is removed

in <state>/session-state.json (the directory runtime/identity.py and
tools/fabric/control/upgrade.py's state dir name), mode 0600, rewritten whole
under a lock and only when a session's state changes: PreToolUse fires on
every tool call and writes nothing while the session stays working.

Beside the state, the session's own `claude` process (the nearest
ancestor of that name) and its start time: a session killed or crashed
never sends SessionEnd, so an entry whose process is gone is dropped —
by the reader when it says the state, and here whenever the file is
written — the start time telling a reused pid from the session's own.

The lock is waited on for LOCK_WAIT_S at most: a holder that is stopped
(not crashed — a crash releases it) would otherwise hold every session's
hook until the harness's timeout kills it and shows an error. A state
that could not be written is lost; the next event says it again.

A hook must never stand in a session's way: any failure is swallowed,
nothing is printed, the exit is 0. It runs nothing and reaches nothing
but that one file; the control agent decides what leaves the account.
"""
from __future__ import annotations

import fcntl
import json
import os
import pwd
import sys
import time

FILE = "session-state.json"
LOCK_WAIT_S = 1.0
NEEDS_A_PERSON = {"permission_prompt", "worker_permission_prompt", "elicitation_dialog",
                  "elicitation_url_dialog", "agent_needs_input"}


def state_dir() -> str:
    login = pwd.getpwuid(os.getuid()).pw_name
    root = os.environ.get("AGENT_FABRIC_STATE_DIR")
    root = os.path.abspath(root) if root else os.path.join(
        os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state"), "agent-fabric")
    return os.path.join(root, "agents", login)


def harness(proc: str = "/proc", pid: int | None = None) -> tuple[int, int] | None:
    """The nearest ancestor named `claude`, as (pid, start time in clock
    ticks since boot, /proc/<pid>/stat field 22); None outside a harness."""
    p = pid or os.getpid()
    for _ in range(64):
        try:
            with open(f"{proc}/{p}/stat", encoding="utf-8", errors="replace") as fh:
                raw = fh.read()
        except OSError:
            return None
        rest = raw[raw.rindex(")") + 2:].split()
        if raw[raw.index("(") + 1:raw.rindex(")")] == "claude":
            return p, int(rest[19])
        if int(rest[1]) <= 1:
            return None
        p = int(rest[1])
    return None


def alive(pid: object, start: object, proc: str = "/proc") -> bool:
    """Whether an entry's process is still its session's; an entry that
    names none is kept, since nothing says it is gone."""
    if not isinstance(pid, int):
        return True
    try:
        with open(f"{proc}/{pid}/stat", encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    except OSError:
        return False
    return not isinstance(start, int) or int(raw[raw.rindex(")") + 2:].split()[19]) == start


def lock(fh, wait: float = LOCK_WAIT_S) -> bool:
    deadline = time.monotonic() + wait
    while True:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.02)


def state_of(payload: dict) -> str | None:
    """The state an event puts a session in; None when it says nothing."""
    event = payload.get("hook_event_name")
    if event in ("UserPromptSubmit", "PreToolUse"):
        return "working"
    if event == "PermissionRequest":
        return "blocked"
    if event == "Notification":
        kind = payload.get("notification_type")
        if kind in NEEDS_A_PERSON:
            return "blocked"
        return "idle" if kind == "idle_prompt" else None
    if event in ("SessionStart", "Stop"):
        return "idle"
    if event == "SessionEnd":
        return "gone"
    return None


def record(payload: dict, directory: str | None = None, now: float | None = None,
           process: tuple[int, int] | None = None, proc: str = "/proc") -> bool:
    """True when the file changed. `process` is the session's harness
    (pid, start); looked up when not given."""
    sid = payload.get("session_id")
    state = state_of(payload)
    if not isinstance(sid, str) or not sid or state is None:
        return False
    directory = directory or state_dir()
    os.makedirs(directory, mode=0o700, exist_ok=True)
    path = os.path.join(directory, FILE)
    with open(os.path.join(directory, FILE + ".lock"), "a") as held:
        if not lock(held):
            return False
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
            sessions = doc.get("sessions") if isinstance(doc, dict) and isinstance(doc.get("sessions"), dict) else {}
        except (OSError, ValueError):
            sessions = {}
        before = len(sessions)
        sessions = {k: v for k, v in sessions.items()
                    if k == sid or (isinstance(v, dict) and alive(v.get("pid"), v.get("start"), proc))}
        pruned = len(sessions) != before
        current = sessions.get(sid) if isinstance(sessions.get(sid), dict) else {}
        if state == "gone":
            if sid not in sessions and not pruned:
                return False
            sessions.pop(sid, None)
        else:
            # A resumed session keeps its id under a new process: the
            # process is part of what changes, or its entry would point
            # at the old one and be dropped as dead.
            pid, start = process if process is not None else (harness() or (None, None))
            # `since` is when the session entered its state: a write made
            # only to prune another entry keeps it (review of #105).
            if (current.get("state"), current.get("pid"), current.get("start")) == (state, pid, start):
                if not pruned:
                    return False
            else:
                sessions[sid] = {"state": state, "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                                 "pid": pid, "start": start}
        tmp = f"{path}.{os.getpid()}"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"sessions": sessions}, fh, sort_keys=True)
        os.replace(tmp, path)
        return True


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if isinstance(payload, dict):
            record(payload)
    except Exception:  # noqa: BLE001 — a hook never stands in a session's way
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
