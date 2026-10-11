#!/usr/bin/env python3
"""tests/run_python_suites.py: the count of failed suites it prints for tests/run.sh. The runner finds its suites relative to its
own directory, so each case copies it into a scratch tree beside fake suites. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNER = os.path.join(ROOT, "tests", "run_python_suites.py")


def tree(base: str, suites: dict[str, tuple[int, str]]) -> str:
    """A scratch tree with the runner and fake suites {name: (exit status, what it prints)}."""
    os.makedirs(os.path.join(base, "tests"))
    shutil.copy(RUNNER, os.path.join(base, "tests", "run_python_suites.py"))
    for name, (status, out) in suites.items():
        with open(os.path.join(base, "tests", f"test_{name}.py"), "w", encoding="utf-8") as fh:
            fh.write(f"import sys\nsys.stdout.write({out!r})\nsys.exit({status})\n")
    return base


def run(base: str, jobs: str = "2") -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "GIT_"))}
    env["AGENT_FABRIC_TEST_JOBS"] = jobs
    return subprocess.run([sys.executable, os.path.join(base, "tests", "run_python_suites.py")], capture_output=True, text=True,
                          env=env, timeout=120)


def last_line(r: subprocess.CompletedProcess) -> str:
    return r.stdout.rstrip("\n").rsplit("\n", 1)[-1]


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as sandbox:
        cases = {
            "two failing among passing": ({"a": (0, "fine\n"), "b": (1, "bad\n"), "c": (3, "worse\n"), "d": (0, "fine\n")}, 1, 2),
            "one failing": ({"a": (0, "fine\n"), "b": (1, "bad\n")}, 1, 1),
            "none failing": ({"a": (0, "fine\n"), "b": (0, "fine\n")}, 0, 0),
            "all failing": ({"a": (1, ""), "b": (2, ""), "c": (1, "")}, 1, 3),
        }
        for label, (suites, status, count) in cases.items():
            r = run(tree(os.path.join(sandbox, label.replace(" ", "-")), suites))
            check(f"{label}: exit {status}, last line FAILED_SUITES={count}", r.returncode == status and last_line(r) == f"FAILED_SUITES={count}",
                  f"{r.returncode} {r.stdout!r} {r.stderr!r}")
        # the count is on a line of its own even when the last suite's output ends without a newline, and a suite that prints the
        # marker itself changes nothing
        r = run(tree(os.path.join(sandbox, "no-newline"), {"a": (1, "no newline at the end"), "b": (0, "FAILED_SUITES=99")}))
        check("a suite's output without a final newline does not swallow the count; a suite printing the marker does not change it",
              r.returncode == 1 and last_line(r) == "FAILED_SUITES=1" and sum(1 for ln in r.stdout.splitlines() if re.fullmatch(r"FAILED_SUITES=\d+", ln)) == 2,
              repr(r.stdout))
        # a bad AGENT_FABRIC_TEST_JOBS: exit 2, nothing ran, no count
        r = run(tree(os.path.join(sandbox, "badjobs"), {"a": (1, "bad\n")}), jobs="zero")
        check("a bad AGENT_FABRIC_TEST_JOBS exits 2 and prints no count", r.returncode == 2 and "FAILED_SUITES" not in r.stdout and "is not a positive number" in r.stderr,
              f"{r.returncode} {r.stdout!r} {r.stderr!r}")
        # the suites' output still comes whole under its header, before the count
        r = run(tree(os.path.join(sandbox, "headers"), {"a": (1, "AAA\n")}), jobs="1")
        check("the suite's header and output precede the count", "== tests/test_a.py\nAAA\n" in r.stdout and r.stdout.index("AAA") < r.stdout.index("FAILED_SUITES="), r.stdout)

    print(f"{'FAIL' if fails else 'ok'}: {fails} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
