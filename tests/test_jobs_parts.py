#!/usr/bin/env python3
"""tools/fabric/jobs.py and its parts, tools/fabric/jobsparts/ (ADR-040 Wave 9: the
job list decomposed along its verbs). tests/test_jobs.py, test_control_jobs.py,
test_gzcoord_intake.py and test_types.py are the oracle for what the command does;
this is what they cannot see: the facade still answers to every name its callers use,
the parts load by path the way the shim runs them (-I, from any directory), two copies
of the tool in one process keep their own parts, and no part reaches a later one.
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import ast
import glob
import importlib.util
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS = os.path.join(ROOT, "tools", "fabric", "jobs.py")
PARTS = os.path.join(ROOT, "tools", "fabric", "jobsparts")
# What the rest of the tree takes from `import jobs`: the intake (mutate, new_job, Refused...),
# the types test (Job, STATES...), the control plane's test (PRIORITIES) and the CLI itself.
NAMES = ["main", "mutate", "new_job", "request_job", "fetch_message", "Refused", "NothingQueued", "Job", "PRIORITIES", "DEFAULT_PRIORITY",
         "STATES", "OPEN", "TERMINAL", "MESSAGE_ID", "POOL_ID", "identity", "find", "active", "transition", "queue_order", "stored_priority",
         "effective_priority", "stream_waits", "ask_queue", "ask_pool", "claimed_job", "pool_job", "line", "show", "summary", "decide",
         "FABRIC_ROOT", "HERE", "INBOX", "QUEUE", "QUEUE_TIMEOUT_S", "Unreachable", "Unanswered"]
ORDER = ["base", "ranking", "records", "queue", "pool", "render", "verbs"]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, JOBS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    a = load("jobs_a")
    check("the facade answers to every name its callers use", all(hasattr(a, n) for n in NAMES), [n for n in NAMES if not hasattr(a, n)])
    check("HERE is tools/fabric/ and FABRIC_ROOT the checkout, as before the split",
          a.HERE == os.path.join(ROOT, "tools", "fabric") and a.FABRIC_ROOT in (ROOT, os.environ.get("AGENT_FABRIC_ROOT")), (a.HERE, a.FABRIC_ROOT))
    check("a name is one object: the facade's and its part's", a.mutate.__module__ == "fabric_jobs.base" and a.Refused is sys.modules["fabric_jobs"].base.Refused)
    first = sys.modules["fabric_jobs"]
    b = load("jobs_b")
    check("a second copy of the tool in one process loads parts of its own",
          sys.modules["fabric_jobs"] is not first and b.Refused is not a.Refused, (b.Refused, a.Refused))

    r = subprocess.run([sys.executable, "-I", JOBS, "--help"], cwd=tempfile.gettempdir(), capture_output=True, text=True, timeout=60)
    check("run under -I from another directory (the shim's way), it prints its usage", r.returncode == 0 and "fabric-jobs" in r.stdout, (r.returncode, r.stderr))

    # No part imports a later one: the parts are acyclic in the order the facade loads them.
    bad = []
    for path in glob.glob(os.path.join(PARTS, "*.py")):
        mod = os.path.basename(path)[:-3]
        if mod not in ORDER:
            continue
        for node in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("fabric_jobs."):
                target = node.module.split(".", 1)[1]
                if ORDER.index(target) >= ORDER.index(mod):
                    bad.append(f"{mod} imports {target}")
    check("no part imports itself or a later part", not bad, bad)
    check("every part is listed here, so a new one has an order", sorted(os.path.basename(p)[:-3] for p in glob.glob(os.path.join(PARTS, "*.py"))) == sorted(ORDER + ["__init__"]))

    print(f"\ntest_jobs_parts: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
