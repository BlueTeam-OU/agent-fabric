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
        # The lock directory, empty unless a case plants a lock: the login's
        # real one may hold a live watch.
        run_dir = os.path.join(tmp, "run")
        os.makedirs(os.path.join(run_dir, "agent-fabric"))
        lock = os.path.join(run_dir, "agent-fabric", "gzcoord-inbox-x.lock")

        def go(payload, procs, now=1000.0, integ=yes):
            return mod.decide({"session_id": "s1", **payload}, procs, now, path, integ, own_pid=ME, run_dir=run_dir)

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
        # The same watch holding the login's one-watch lock, in the lock's
        # own format ("<pid>\n<started>\n"): the login has its watch, and a
        # second would be refused, so no block (review of #242, R2).
        with open(lock, "w", encoding="utf-8") as fh:
            fh.write("300\n2026-10-13T18:00:00Z\n")
        out = go({}, other)
        check("decide: an out-of-tree live watch holding the lock: passes", out is None, out)
        check("…and no state written for it", not os.path.exists(path))
        stale = {k: v for k, v in other.items() if k != 300}
        out = go({}, stale)
        check("decide: the lock names a watch that is gone: blocked", out and out["decision"] == "block", out)
        os.remove(lock)
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

        # integrated(): a binding with a role is required besides the project's
        # GZCoord integration; the fabric root is a stub tree so only that is tested.
        stub = os.path.join(tmp, "stubroot")
        cfg = os.path.join(stub, "tools", "fabric", "gzcoord", "inbox_parts")
        os.makedirs(cfg)
        os.makedirs(os.path.join(stub, "runtime"))
        for d in (os.path.dirname(cfg), cfg):
            open(os.path.join(d, "__init__.py"), "w").close()
        with open(os.path.join(cfg, "config.py"), "w") as fh:
            fh.write("def integration_config(project):\n    return {'configured': True}\n")

        def stub_identity(binding: str) -> None:
            with open(os.path.join(stub, "runtime", "identity.py"), "w") as fh:
                fh.write("def resolve_context(cwd=None, session=None):\n    return {'agent': 'a', 'project': 'p'}\n"
                         f"def read_binding(agent=None):\n    return {binding}\n")
        real_root, mod.FABRIC_ROOT = mod.FABRIC_ROOT, stub
        stub_identity("{}")
        check("integrated: no fabric binding passes silently", mod.integrated(tmp, "s") is False)
        stub_identity("{'role': None}")
        check("integrated: a binding without a role passes silently", mod.integrated(tmp, "s") is False)
        stub_identity("{'role': 'fabric-coordinator'}")
        check("integrated: a binding with a role and a configured project", mod.integrated(tmp, "s") is True)
        mod.FABRIC_ROOT = real_root

        # gzcoord-inbox's one-watch lock names the holder: a live watch there is this login's
        # watch even outside this session's tree; a stale pid, or a pid that is no watch, is not.
        with tempfile.TemporaryDirectory() as rd:
            os.makedirs(os.path.join(rd, "agent-fabric"))
            lock = os.path.join(rd, "agent-fabric", "gzcoord-inbox-user.lock")
            watch_cmd = "/usr/local/bin/fabric-python -I /home/u/.local/bin/gzcoord-inbox --until-delivery"
            procs = {4242: (1, "fabric-python", watch_cmd), 4343: (1, "sleep", "sleep 100")}
            # The lock's own format: the holder's pid, then when it started.
            for content, want, label in (("4242\n2026-10-13T18:00:00Z\n", True, "a live watch holds the lock"),
                                         ("9999\n2026-10-13T18:00:00Z\n", False, "the lock names a pid that is gone"),
                                         ("4343\n2026-10-13T18:00:00Z\n", False, "the lock names a pid that is no watch"),
                                         ("", False, "an empty lock file")):
                with open(lock, "w", encoding="utf-8") as fh:
                    fh.write(content)
                check(f"lock holder: {label}", mod.lock_holder_is_watch(procs, rd) is want)
            os.remove(lock)
            check("lock holder: no lock file", mod.lock_holder_is_watch(procs, rd) is False)

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
