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
runtime/control/upgrade.mjs's stateDir name), mode 0600, rewritten whole
under a lock and only when a session's state changes: PreToolUse fires on
every tool call and writes nothing while the session stays working.

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
NEEDS_A_PERSON = {"permission_prompt", "worker_permission_prompt", "elicitation_dialog",
                  "elicitation_url_dialog", "agent_needs_input"}


def state_dir() -> str:
    login = pwd.getpwuid(os.getuid()).pw_name
    root = os.environ.get("AGENT_FABRIC_STATE_DIR")
    root = os.path.abspath(root) if root else os.path.join(
        os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state"), "agent-fabric")
    return os.path.join(root, "agents", login)


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


def record(payload: dict, directory: str | None = None, now: float | None = None) -> bool:
    """True when the file changed."""
    sid = payload.get("session_id")
    state = state_of(payload)
    if not isinstance(sid, str) or not sid or state is None:
        return False
    directory = directory or state_dir()
    os.makedirs(directory, mode=0o700, exist_ok=True)
    path = os.path.join(directory, FILE)
    with open(os.path.join(directory, FILE + ".lock"), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
            sessions = doc.get("sessions") if isinstance(doc, dict) and isinstance(doc.get("sessions"), dict) else {}
        except (OSError, ValueError):
            sessions = {}
        current = sessions.get(sid, {}).get("state") if isinstance(sessions.get(sid), dict) else None
        if state == "gone":
            if sid not in sessions:
                return False
            del sessions[sid]
        elif current == state:
            return False
        else:
            sessions[sid] = {"state": state, "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))}
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
