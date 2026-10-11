#!/usr/bin/env python3
"""runtime/claude-code/hooks/watch-on-stop.py: a Stop with no live inbox
watch under the session's harness is blocked once with the command; a watch
present, a repeat inside the window, stop_hook_active, a project with no
GZCoord, and any internal error all pass silently."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(HERE, "runtime", "claude-code", "hooks", "watch-on-stop.py")
spec = importlib.util.spec_from_file_location("watch_on_stop", HOOK)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

ME = 500
# pid -> (ppid, comm, command line): init, the harness, a shell, this hook.
BASE = {1: (0, "init", "init"), 100: (1, "claude", "claude"), 200: (100, "bash", "bash"), ME: (200, "python3", "hook")}


def table(*extra):
    return {**BASE, **dict(extra)}


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "agents", "x", "watch-on-stop.json")
        yes, no = (lambda c, s: True), (lambda c, s: False)

        def go(payload, procs, now=1000.0, integ=yes):
            return mod.decide({"session_id": "s1", **payload}, procs, now, path, integ, own_pid=ME)

        def fresh():
            if os.path.exists(path):
                os.remove(path)

        out = go({}, table((300, (200, "python3", "python3 /x/bin/gzcoord-inbox --until-delivery"))))
        check("a watch under the harness: passes", out is None, out)
        out = go({}, table((300, (200, "python3", "gzcoord-inbox --wait"))))
        check("--wait counts as a watch", out is None, out)
        nested = table((301, (200, "sh", "sh -c x")), (302, (301, "python3", "gzcoord-inbox --until-delivery")))
        check("a watch nested below the harness: passes", go({}, nested) is None)
        check("no state written for a pass", not os.path.exists(path))
        other = table((300, (999, "python3", "gzcoord-inbox --until-delivery")), (999, (1, "claude", "claude")))
        out = go({}, other)
        check("a watch under another session's harness: blocked, with the command",
              out and out["decision"] == "block" and "gzcoord-inbox --until-delivery" in out["reason"], out)
        fresh()
        out = go({}, table((300, (200, "python3", "gzcoord-inbox --follow"))))
        check("--follow counts as a watch, as in session-start", out is None, out)
        out = go({}, table((300, (200, "python3", "gzcoord-inbox --status"))))
        check("a gzcoord-inbox without --until-delivery/--follow/--wait is not a watch: blocked",
              out and out["decision"] == "block", out)
        out = go({}, table(), now=1100.0)
        check("blocked again 100 s later: passes", out is None, out)
        out = go({}, table(), now=1000.0 + mod.WINDOW_S + 1)
        check("blocked again after the window: blocks", out and out["decision"] == "block", out)
        fresh()
        check("stop_hook_active: passes", go({"stop_hook_active": True}, table()) is None)
        check("no integration: passes", go({}, table(), integ=no) is None)
        check("no harness ancestor: passes", go({}, {1: (0, "init", "init"), ME: (1, "python3", "h")}) is None)
        check("no state written for those passes", not os.path.exists(path))

        def run(stdin):
            return subprocess.run([sys.executable, HOOK], input=stdin, capture_output=True, text=True, timeout=30,
                                  env={**os.environ, "AGENT_FABRIC_STATE_DIR": tmp})
        for label, stdin in (("unreadable payload", "not json"), ("a non-object payload", "[1]"), ("empty", "")):
            r = run(stdin)
            check(f"{label}: exit 0, silent", r.returncode == 0 and not r.stdout and not r.stderr,
                  (r.returncode, r.stdout, r.stderr))
        r = run(json.dumps({"session_id": "s", "cwd": tmp}))
        check("a real run outside a fabric binding: exit 0, silent", r.returncode == 0 and not r.stdout,
              (r.stdout, r.stderr))

        def boom(*a, **k):
            raise RuntimeError("x")
        orig, mod.read_procs = mod.read_procs, boom
        sys.stdin = io.StringIO(json.dumps({"session_id": "s"}))
        check("an internal error in main(): returns 0", mod.main() == 0)
        mod.read_procs = orig

    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
