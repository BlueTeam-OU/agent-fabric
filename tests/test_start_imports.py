#!/usr/bin/env python3
"""What the commands the suites start most do NOT load on a cheap argument (j830 W5). Asserted by module NAME under
-X importtime, never by milliseconds, so load cannot turn it red. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = os.environ.get("AGENT_FABRIC_PYTHON") or sys.executable
failures = 0


def loaded(argv: list[str], extra_env: dict | None = None) -> set[str]:
    env = {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/"), "AGENT_FABRIC_ROOT": ROOT, **(extra_env or {})}
    p = subprocess.run([PY, "-X", "importtime", *argv], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, (argv, p.returncode, p.stderr[-400:])
    return {line.split("|")[2].strip() for line in p.stderr.splitlines() if line.startswith("import time:") and line.count("|") == 2}


def check(name: str, mods: set[str], absent: tuple[str, ...] = (), present: tuple[str, ...] = ()) -> None:
    global failures
    wrongly = [m for m in absent if m in mods]
    missing = [m for m in present if m not in mods]
    if wrongly or missing:
        failures += 1
        print(f"FAIL {name}: loaded {wrongly}, not loaded {missing}")
    else:
        print(f"ok   {name}")


T = os.path.join(ROOT, "tools", "fabric")
# jobs.py: a path that parses no stamp and reads no cargo configuration loads neither calendar nor tomllib.
check("jobs.py --help", loaded([os.path.join(T, "jobs.py"), "--help"]), absent=("calendar", "tomllib", "tomllib._parser"))
# addenda.py --help never asks whether a name is an IANA zone.
check("addenda.py --help", loaded([os.path.join(T, "addenda.py"), "--help"]), absent=("zoneinfo",))
# The entries import the module, so its bytecode is cached; run as a script it is __main__ and never in this list.
# Through bin/fabric-ctl itself (not -I, so the environment's switch reaches the interpreter): the shim must name the entry.
_p = subprocess.run(["bash", os.path.join(ROOT, "bin", "fabric-ctl"), "--help"], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120,
                    env={"PATH": "/usr/bin:/bin", "HOME": "/", "AGENT_FABRIC_PYTHON": PY, "AGENT_FABRIC_ROOT": ROOT, "PYTHONPROFILEIMPORTTIME": "1"})
check("bin/fabric-ctl imports control.ctl", {l.split("|")[2].strip() for l in _p.stderr.splitlines() if l.startswith("import time:") and l.count("|") == 2},
      present=("control.ctl",))
# bin/fabric-branches runs under -I, where PYTHONPROFILEIMPORTTIME is ignored: its proof is the module's cache file, which
# only an import writes (runpy.run_path compiles every start and caches nothing).
import glob
for old in glob.glob(os.path.join(T, "__pycache__", "branches.*.pyc")):
    os.unlink(old)
subprocess.run(["bash", os.path.join(ROOT, "bin", "fabric-branches"), "--help"], env={"PATH": "/usr/bin:/bin", "HOME": "/", "AGENT_FABRIC_PYTHON": PY},
               stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
check("fabric-branches caches its bytecode", {"cached"} if glob.glob(os.path.join(T, "__pycache__", "branches.*.pyc")) else set(), present=("cached",))
sys.exit(1 if failures else 0)
