#!/usr/bin/env python3
"""Tests for runtime/claude-code/hooks/session-state.py: which state each
hook event puts a session in, that the file changes only when a state
does, that an ended session leaves it, that nothing is printed and the
exit is 0 whatever the payload, against a scratch state directory."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(HERE, "runtime", "claude-code", "hooks", "session-state.py")
spec = importlib.util.spec_from_file_location("session_state", HOOK)
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    cases = [
        ({"hook_event_name": "SessionStart"}, "idle"),
        ({"hook_event_name": "UserPromptSubmit"}, "working"),
        ({"hook_event_name": "PreToolUse"}, "working"),
        ({"hook_event_name": "PermissionRequest"}, "blocked"),
        ({"hook_event_name": "Notification", "notification_type": "permission_prompt"}, "blocked"),
        ({"hook_event_name": "Notification", "notification_type": "elicitation_dialog"}, "blocked"),
        ({"hook_event_name": "Notification", "notification_type": "agent_needs_input"}, "blocked"),
        ({"hook_event_name": "Notification", "notification_type": "idle_prompt"}, "idle"),
        ({"hook_event_name": "Notification", "notification_type": "auth_success"}, None),
        ({"hook_event_name": "Stop"}, "idle"),
        ({"hook_event_name": "SessionEnd"}, "gone"),
        ({"hook_event_name": "SubagentStop"}, None),
    ]
    got = [(p, ss.state_of(p)) for p, _ in cases]
    check("each event's state", [g for _, g in got] == [w for _, w in cases], got)

    with tempfile.TemporaryDirectory() as tmp:
        d = os.path.join(tmp, "agents", "x")
        f = os.path.join(d, ss.FILE)
        ev = lambda e, **k: {"session_id": "s1", "hook_event_name": e, **k}  # noqa: E731
        check("a start writes idle", ss.record(ev("SessionStart"), d, 0) is True
              and json.load(open(f))["sessions"]["s1"]["state"] == "idle")
        check("…the file is 0600", os.stat(f).st_mode & 0o777 == 0o600, oct(os.stat(f).st_mode))
        check("a prompt: working", ss.record(ev("UserPromptSubmit"), d, 1) is True
              and json.load(open(f))["sessions"]["s1"] == {"state": "working", "since": "1970-01-01T00:00:01Z"})
        before = os.stat(f).st_mtime_ns
        check("tool calls while working write nothing", ss.record(ev("PreToolUse"), d, 2) is False
              and os.stat(f).st_mtime_ns == before)
        check("a permission prompt: blocked", ss.record(ev("Notification", notification_type="permission_prompt"), d, 3)
              and json.load(open(f))["sessions"]["s1"]["state"] == "blocked")
        ss.record({"session_id": "s2", "hook_event_name": "SessionStart"}, d, 4)
        check("two sessions kept apart", set(json.load(open(f))["sessions"]) == {"s1", "s2"})
        check("an ended session leaves the file", ss.record(ev("SessionEnd"), d, 5) is True
              and set(json.load(open(f))["sessions"]) == {"s2"})
        check("an end for an unknown session writes nothing", ss.record(ev("SessionEnd"), d, 6) is False)
        check("no session id: nothing", ss.record({"hook_event_name": "Stop"}, d, 7) is False)
        with open(f, "w") as fh:
            fh.write("{broken")
        check("an unreadable file starts over", ss.record(ev("SessionStart"), d, 8) is True
              and json.load(open(f))["sessions"] == {"s1": {"state": "idle", "since": "1970-01-01T00:00:08Z"}})
        check("no temporary file left", sorted(os.listdir(d)) == [ss.FILE, ss.FILE + ".lock"], os.listdir(d))

        env = {**os.environ, "AGENT_FABRIC_STATE_DIR": os.path.join(tmp, "cli")}
        for stdin in ('{"session_id":"c1","hook_event_name":"UserPromptSubmit"}', "not json", "[1,2]", ""):
            r = subprocess.run([sys.executable, HOOK], input=stdin, capture_output=True, text=True, env=env, timeout=30)
            check(f"the hook prints nothing and exits 0 on {stdin[:20]!r}", r.returncode == 0 and r.stdout == "" and r.stderr == "",
                  (r.returncode, r.stdout, r.stderr))
        login = os.listdir(os.path.join(tmp, "cli", "agents"))[0]
        written = json.load(open(os.path.join(tmp, "cli", "agents", login, ss.FILE)))
        check("…and the valid payload was kept under the login's state directory", written["sessions"]["c1"]["state"] == "working")

    print("all passed" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
