#!/usr/bin/env python3
"""Tests for runtime/claude-code/hooks/session-state.py: which state each
hook event puts a session in, that the file changes only when a state
does, that an ended session leaves it, that nothing is printed and the
exit is 0 whatever the payload, against a scratch state directory."""
from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

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
    P = (4242, 777)
    got = [(p, ss.state_of(p)) for p, _ in cases]
    check("each event's state", [g for _, g in got] == [w for _, w in cases], got)

    with tempfile.TemporaryDirectory() as tmp:
        def proc(pid: int, comm: str, ppid: int, start: int) -> None:
            os.makedirs(f"{tmp}/proc/{pid}", exist_ok=True)
            # Field 22 is the start time; the comm may hold spaces and parentheses.
            fields = ["S", str(ppid)] + ["0"] * 17 + [str(start)]
            open(f"{tmp}/proc/{pid}/stat", "w").write(f"{pid} ({comm}) " + " ".join(fields) + " 0 0\n")
        proc(1, "systemd", 0, 1)
        proc(50, "claude", 1, 4000)
        proc(60, "sh (x)", 50, 4100)
        proc(70, "python3", 60, 4200)
        proc(80, "bash", 1, 4300)
        proc(4242, "claude", 1, 777)
        proc(5151, "claude", 1, 888)
        PROC = f"{tmp}/proc"
        check("the harness is the nearest claude ancestor, with its start time", ss.harness(f"{tmp}/proc", 70) == (50, 4000),
              ss.harness(f"{tmp}/proc", 70))
        check("no claude ancestor: None", ss.harness(f"{tmp}/proc", 80) is None)
        check("a vanished process: None", ss.harness(f"{tmp}/proc", 99) is None)
        d = os.path.join(tmp, "agents", "x")
        f = os.path.join(d, ss.FILE)
        ev = lambda e, **k: {"session_id": "s1", "hook_event_name": e, **k}  # noqa: E731
        check("a start writes idle", ss.record(ev("SessionStart"), d, 0, P, PROC) is True
              and json.load(open(f))["sessions"]["s1"]["state"] == "idle")
        check("…the file is 0600", os.stat(f).st_mode & 0o777 == 0o600, oct(os.stat(f).st_mode))
        check("a prompt: working", ss.record(ev("UserPromptSubmit"), d, 1, P, PROC) is True
              and json.load(open(f))["sessions"]["s1"] == {"state": "working", "since": "1970-01-01T00:00:01Z", "pid": 4242, "start": 777})
        before = os.stat(f).st_mtime_ns
        check("tool calls while working write nothing", ss.record(ev("PreToolUse"), d, 2, P, PROC) is False
              and os.stat(f).st_mtime_ns == before)
        check("a permission prompt: blocked", ss.record(ev("Notification", notification_type="permission_prompt"), d, 3, P, PROC)
              and json.load(open(f))["sessions"]["s1"]["state"] == "blocked")
        ss.record({"session_id": "s2", "hook_event_name": "SessionStart"}, d, 4, P, PROC)
        check("two sessions kept apart", set(json.load(open(f))["sessions"]) == {"s1", "s2"})
        check("an ended session leaves the file", ss.record(ev("SessionEnd"), d, 5, P, PROC) is True
              and set(json.load(open(f))["sessions"]) == {"s2"})
        check("an end for an unknown session writes nothing", ss.record(ev("SessionEnd"), d, 6, P, PROC) is False)
        check("no session id: nothing", ss.record({"hook_event_name": "Stop"}, d, 7, P, PROC) is False)
        with open(f, "w") as fh:
            fh.write("{broken")
        check("an unreadable file starts over", ss.record(ev("SessionStart"), d, 8, P, PROC) is True
              and json.load(open(f))["sessions"] == {"s1": {"state": "idle", "since": "1970-01-01T00:00:08Z", "pid": 4242, "start": 777}})
        check("a resumed session (same id, new process) is rewritten", ss.record(ev("SessionStart"), d, 9, (5151, 888), PROC) is True
              and json.load(open(f))["sessions"]["s1"]["pid"] == 5151)
        proc(6161, "claude", 1, 999)
        ss.record({"session_id": "s3", "hook_event_name": "SessionStart"}, d, 11, (6161, 999), PROC)
        shutil.rmtree(f"{PROC}/6161")
        check("a killed session (no SessionEnd) is pruned when another session writes",
              ss.record(ev("UserPromptSubmit"), d, 12, (5151, 888), PROC) is True and "s3" not in json.load(open(f))["sessions"],
              json.load(open(f)))
        proc(6161, "claude", 1, 1000)
        ss.record({"session_id": "s4", "hook_event_name": "SessionStart"}, d, 13, (6161, 1000), PROC)
        os.makedirs(f"{PROC}/6161", exist_ok=True)
        check("…and a reused pid (other start time) is not the session's own",
              ss.alive(6161, 999, PROC) is False and ss.alive(6161, 1000, PROC) is True)
        before = open(f).read()
        shutil.rmtree(f"{PROC}/6161")
        check("a gone event for an unknown session still writes when it prunes",
              ss.record({"session_id": "zz", "hook_event_name": "SessionEnd"}, d, 14, P, PROC) is True
              and "s4" not in json.load(open(f))["sessions"] and open(f).read() != before)
        with open(f + ".lock", "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            t0 = time.monotonic()
            got = ss.record(ev("Stop"), d, 15, (5151, 888), PROC)
            waited = time.monotonic() - t0
        check("a held lock is waited on for about a second, then the event is dropped",
              got is False and 0.9 <= waited < 3, (got, waited))
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
