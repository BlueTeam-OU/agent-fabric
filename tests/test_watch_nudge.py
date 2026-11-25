#!/usr/bin/env python3
"""runtime/claude-code/hooks/watch-nudge.py: a PostToolUse call with no live inbox
watch under the session's harness is told once, per spell of "down", to re-arm it;
a repeat inside the window, a watch up, a subagent, no binding and malformed
input are silent; every path exits 0."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
HOOKS = os.path.join(HERE, "runtime", "claude-code", "hooks")
HOOK = os.path.join(HOOKS, "watch-nudge.py")


def load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


nudge = load(HOOK, "watch_nudge")
stop = load(os.path.join(HOOKS, "watch-on-stop.py"), "watch_on_stop_for_nudge")

ME = 500
BASE = {1: (0, "init", "init"), 100: (1, "claude", "claude"), 200: (100, "bash", "bash"), ME: (200, "python3", "hook")}
WATCH = {300: (200, "python3", "python3 /x/bin/gzcoord-inbox --until-delivery")}


def table(extra=None):
    return {**BASE, **(extra or {})}


def clean_env() -> dict:
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/nonexistent"}


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "agents", "x", "watch-nudge.json")
        run_dir = os.path.join(tmp, "run")
        os.makedirs(os.path.join(run_dir, "agent-fabric"))
        yes, no = (lambda c, s: True), (lambda c, s: False)

        def go(procs, now, payload=None, integ=yes):
            return nudge.decide({"session_id": "s1", **(payload or {})}, now, path, procs, integ, own_pid=ME, run_dir=run_dir)

        def ctx(out):
            return out["hookSpecificOutput"]["additionalContext"] if out else None

        def fresh():
            if os.path.exists(path):
                os.remove(path)

        # The words the session is told are watch-on-stop.py's: its command and its Bash(...) shape.
        shape = nudge.message(stop.COMMAND)
        bash = shape[shape.index("Bash("):shape.index("). Never")] + ")"
        check("the Bash(...) shape is the one in watch-on-stop.py's REASON", bash in stop.REASON, bash)
        check("the command is watch-on-stop.py's COMMAND", stop.COMMAND in shape and stop.COMMAND == "gzcoord-inbox --until-delivery")

        # watch down: one reminder, in additionalContext, nothing that refuses
        out = go(table(), 1000.0)
        check("watch down: one reminder", out is not None and stop.COMMAND in ctx(out), out)
        check("…as hookSpecificOutput for PostToolUse, no decision key",
              out == {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": ctx(out)}}, out)
        check("…the record is 0600", os.stat(path).st_mode & 0o777 == 0o600, oct(os.stat(path).st_mode))
        # inside the window: no read at all (the procs callable would raise)
        def no_read():
            raise AssertionError("the process table was read inside the window")
        check("a second call inside the window: silent, no process-table read",
              go(no_read, 1000.0 + nudge.CHECK_S - 1) is None)
        # after the window, still down: the same spell is not said again
        check("after the window, still down: silent (once per spell)", go(table(), 1000.0 + nudge.CHECK_S + 1) is None)
        check("…and still silent until AGAIN_S after the reminder", go(table(), 1000.0 + nudge.AGAIN_S - 1) is None)
        out = go(table(), 1000.0 + nudge.AGAIN_S + nudge.CHECK_S)
        check("…reminded again once AGAIN_S has passed (review of #705, F2)", out is not None and stop.COMMAND in ctx(out), out)
        # up resets the spell, down again reminds
        check("watch up: silent", go(table(WATCH), 6000.0) is None)
        out = go(table(), 6100.0)
        check("up, then down again: reminds again", out is not None and stop.COMMAND in ctx(out), out)
        # The session's own re-arm ends the spell, though no read saw the watch up: a watch that a delivery ends while
        # the session is idle is a new spell (review of #705, F2).
        fresh()
        check("down: reminded", go(table(), 1000.0) is not None)
        rearm = {"tool_name": "Bash", "tool_input": {"command": stop.COMMAND}}
        check("the re-arm call itself: silent, no process-table read", go(no_read, 1005.0, rearm) is None)
        out = go(table(), 1600.0)
        check("…down again at the next read: reminded", out is not None and stop.COMMAND in ctx(out), out)
        check("a Bash call that only names the flag is no re-arm",
              go(no_read, 1610.0, {"tool_name": "Bash", "tool_input": {"command": "grep -- --until-delivery x"}}) is None)
        check("…and the spell stays reminded", go(table(), 1700.0) is None)
        # No harness ancestor: the read is recorded, so the next call inside the window reads nothing (F1).
        fresh()
        orphan = {1: (0, "init", "init"), ME: (1, "python3", "hook")}
        check("no harness ancestor: silent", go(orphan, 1000.0) is None)
        check("…the read recorded: the next call inside the window reads nothing",
              os.path.exists(path) and go(no_read, 1001.0) is None)
        # A record that cannot be written costs the bound, never the reminder (F1).
        fresh()
        orig_write = nudge.write_state
        nudge.write_state = lambda p, seen: (_ for _ in ()).throw(OSError("read-only"))
        try:
            out = go(table(), 1000.0)
        finally:
            nudge.write_state = orig_write
        check("an unwritable record: still reminds", out is not None and stop.COMMAND in ctx(out), out)
        fresh()
        # a watch holding the login's lock outside the tree counts as up (has_watch's rule)
        fresh()
        with open(os.path.join(run_dir, "agent-fabric", "gzcoord-inbox-x.lock"), "w", encoding="utf-8") as fh:
            fh.write("300\n2026-11-24T00:00:00Z\n")
        outside = table({300: (999, "python3", "gzcoord-inbox --until-delivery"), 999: (1, "claude", "claude")})
        check("a lock-holding watch outside the tree: silent", go(outside, 1000.0) is None)
        os.remove(os.path.join(run_dir, "agent-fabric", "gzcoord-inbox-x.lock"))
        fresh()

        # sessions are told apart
        go(table(), 1000.0)
        out = nudge.decide({"session_id": "s2"}, 1001.0, path, table(), yes, own_pid=ME, run_dir=run_dir)
        check("another session's record does not silence this one", out is not None, out)
        fresh()

        # silent cases leave no record where they are cheap passes
        check("a subagent's call (agent_id): silent", go(table(), 1000.0, {"agent_id": "a1"}) is None)
        check("a subagent's call (agent_type): silent", go(table(), 1000.0, {"agent_type": "Explore"}) is None)
        check("…and no record written", not os.path.exists(path))
        check("no binding or no GZCoord: silent", go(table(), 1000.0, integ=no) is None)
        check("…and not remembered as reminded: reminds once the project is integrated",
              go(table(), 1100.0) is not None)
        fresh()
        check("no session_id: silent", nudge.decide({}, 1000.0, path, table(), yes, own_pid=ME, run_dir=run_dir) is None)
        check("a non-string session_id: silent",
              nudge.decide({"session_id": 5}, 1000.0, path, table(), yes, own_pid=ME, run_dir=run_dir) is None)
        down = os.path.join(run_dir, "agent-fabric", "gzcoord-inbox-x.relay-down")
        with open(down, "w", encoding="utf-8") as fh:
            fh.write("900\n")
        # No probe on a per-tool hook: the relay and carrier probes raise if called (review of #705, F3).
        ws = nudge.on_stop()
        probes = (ws.relay_answers, ws.carrier_answers)
        def probed(*a, **k):
            raise AssertionError("a relay or carrier probe ran")
        ws.relay_answers = ws.carrier_answers = probed
        try:
            check("a fresh relay-down marker: silent, no probe", go(table(), 1000.0) is None)
        finally:
            ws.relay_answers, ws.carrier_answers = probes
        out = go(table(), 900.0 + stop.RELAY_DOWN_S)
        check("…the reason ended: the spell it kept silent is reminded", out is not None, out)
        os.remove(down)
        fresh()
        # a damaged record is no record
        os.makedirs(os.path.dirname(path), exist_ok=True)
        for junk in ("not json", "[1]", '{"s1": 5}', '{"s1": {"checked": "x"}}'):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(junk)
            check(f"a damaged record {junk!r}: reminds", go(table(), 1000.0) is not None)
        fresh()

        # main(): malformed input and internal errors exit 0 and print nothing
        orig_in, orig_out = sys.stdin, sys.stdout
        for raw in ("", "{", "null", "[]", '"x"', "\xff"):
            sys.stdin, sys.stdout = io.StringIO(raw), io.StringIO()
            try:
                rc, printed = nudge.main(), sys.stdout.getvalue()
            finally:
                sys.stdin, sys.stdout = orig_in, orig_out
            check(f"main on {raw!r}: exit 0, silent", rc == 0 and printed == "", (rc, printed))
        orig = nudge.state_path
        nudge.state_path = lambda: (_ for _ in ()).throw(RuntimeError("x"))
        sys.stdin, sys.stdout = io.StringIO('{"session_id": "s"}'), io.StringIO()
        try:
            rc, printed = nudge.main(), sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout, nudge.state_path = orig_in, orig_out, orig
        check("an internal error in main(): exit 0, silent", rc == 0 and printed == "", (rc, printed))
        # main() prints decide()'s answer as one JSON line (review of #705, F3: no case reached the print).
        answer = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "x"}}
        orig_decide, orig_path = nudge.decide, nudge.state_path
        nudge.decide, nudge.state_path = (lambda payload, now, path: answer), (lambda: path)
        sys.stdin, sys.stdout = io.StringIO('{"session_id": "s"}'), io.StringIO()
        try:
            rc, printed = nudge.main(), sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout, nudge.decide, nudge.state_path = orig_in, orig_out, orig_decide, orig_path
        check("main(): decide's answer printed as one JSON line", rc == 0 and printed == json.dumps(answer) + "\n", printed)

        # The real entry point, as a subprocess with a minimal environment. Run from a Claude Code session it may well
        # be a harness's child; it is silent because its state directory is an empty temp one, with no binding, so
        # nothing is integrated, and malformed input is silence whatever the tree.
        env = {**clean_env(), "AGENT_FABRIC_STATE_DIR": os.path.join(tmp, "state"), "AGENT_FABRIC_ROOT": HERE}
        for raw in ('{"session_id": "s1", "tool_name": "Bash"}', "{", ""):
            r = subprocess.run([sys.executable, HOOK], input=raw, capture_output=True, text=True, env=env, timeout=30, check=False)
            check(f"the installed command on {raw[:12]!r}: exit 0, silent, no traceback",
                  r.returncode == 0 and r.stdout == "" and r.stderr == "", (r.returncode, r.stdout, r.stderr))

    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
