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
        check("…and still silent much later", go(table(), 5000.0) is None)
        # up resets the spell, down again reminds
        check("watch up: silent", go(table(WATCH), 6000.0) is None)
        out = go(table(), 6100.0)
        check("up, then down again: reminds again", out is not None and stop.COMMAND in ctx(out), out)
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
        check("no harness ancestor: silent", go({1: (0, "init", "init"), ME: (1, "python3", "hook")}, 1000.0) is None)
        check("no session_id: silent", nudge.decide({}, 1000.0, path, table(), yes, own_pid=ME, run_dir=run_dir) is None)
        check("a non-string session_id: silent",
              nudge.decide({"session_id": 5}, 1000.0, path, table(), yes, own_pid=ME, run_dir=run_dir) is None)
        down = os.path.join(run_dir, "agent-fabric", "gzcoord-inbox-x.relay-down")
        with open(down, "w", encoding="utf-8") as fh:
            fh.write("900\n")
        check("a fresh relay-down marker: silent, no probe", go(table(), 1000.0) is None)
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

        # The real entry point, as a subprocess with a minimal environment: this process is no harness's child,
        # so the answer is silence, and the state directory is a temp one.
        env = {**clean_env(), "AGENT_FABRIC_STATE_DIR": os.path.join(tmp, "state"), "AGENT_FABRIC_ROOT": HERE}
        for raw in ('{"session_id": "s1", "tool_name": "Bash"}', "{", ""):
            r = subprocess.run([sys.executable, HOOK], input=raw, capture_output=True, text=True, env=env, timeout=30, check=False)
            check(f"the installed command on {raw[:12]!r}: exit 0, silent, no traceback",
                  r.returncode == 0 and r.stdout == "" and r.stderr == "", (r.returncode, r.stdout, r.stderr))

    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
