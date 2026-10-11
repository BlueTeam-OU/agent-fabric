#!/usr/bin/env python3
"""tests/section_groups.py, the parent half of the suites that run their sections as groups: the output comes back in
group order whatever order the groups finished in; a failed group fails the run; a group that overruns is stopped
through its process group (its sandbox removed, its child process gone), not left behind; and the number running at once
is the override, clamped to the cores and to MAX_PARALLEL_GROUPS. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import textwrap
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import section_groups  # noqa: E402

CHILD = textwrap.dedent('''\
    import os, subprocess, sys, tempfile, time
    sys.path.insert(0, {here!r})
    import section_groups
    group = int(sys.argv[2])
    section_groups.child_setup()
    scratch = {scratch!r}
    with open(os.path.join(scratch, "starts"), "a") as fh:
        fh.write(f"{{group}} {{time.monotonic()}}\\n")
    if group == 0 and {mode!r} == "overrun":
        with tempfile.TemporaryDirectory(dir=scratch, prefix="sandbox-") as sandbox:
            kid = subprocess.Popen(["sleep", "300"])
            with open(os.path.join(scratch, "kid"), "w") as fh:
                fh.write(str(kid.pid))
            time.sleep(300)
    time.sleep({nap!r} if group < 2 else 0)
    print(f"group {{group}}: output")
    sys.exit(1 if (group == 1 and {mode!r} == "fail") else 0)
''')


def run(mode: str, ngroups: int, order: tuple[int, ...], timeout_s: int = 60, nap: float = 0.0,
        jobs: str | None = None, cpus: int | None = None) -> tuple[int, str, str]:
    with tempfile.TemporaryDirectory() as scratch:
        script = os.path.join(scratch, "child.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(CHILD.format(here=HERE, scratch=scratch, mode=mode, nap=nap))
        out = io.StringIO()
        saved_env, saved_cpu = os.environ.get("TEST_GROUP_JOBS"), os.cpu_count
        if jobs is not None:
            os.environ["TEST_GROUP_JOBS"] = jobs
        if cpus is not None:
            os.cpu_count = lambda: cpus   # type: ignore[assignment]
        try:
            with contextlib.redirect_stdout(out):
                rc = section_groups.drive(script, "t", ngroups, order, "TEST_GROUP_JOBS", timeout_s)
        finally:
            os.cpu_count = saved_cpu   # type: ignore[assignment]
            if saved_env is None:
                os.environ.pop("TEST_GROUP_JOBS", None)
            else:
                os.environ["TEST_GROUP_JOBS"] = saved_env
        starts = open(os.path.join(scratch, "starts"), encoding="utf-8").read() if os.path.exists(os.path.join(scratch, "starts")) else ""
        left = [n for n in os.listdir(scratch) if n.startswith("sandbox-")]
        kid = open(os.path.join(scratch, "kid"), encoding="utf-8").read() if os.path.exists(os.path.join(scratch, "kid")) else ""
        try:
            with open(f"/proc/{kid}/cmdline", encoding="utf-8") as fh:
                alive = bool(kid) and "sleep" in fh.read()
        except OSError:
            alive = False
        return rc, out.getvalue(), "|".join([starts, ",".join(left), str(alive), kid])


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    rc, out, _ = run("ok", 3, (2, 1, 0), nap=0.3)
    check("every group ran: exit 0, and the output is in group order though group 2 finished first",
          rc == 0 and out.index("group 0: output") < out.index("group 1: output") < out.index("group 2: output")
          and out.rstrip().endswith("t: OK"), out)
    rc, out, _ = run("fail", 3, (0, 1, 2))
    check("a group that exits non-zero fails the run, the others still reported",
          rc == 1 and "group 2: output" in out and "t: FAILED — 1 group(s)" in out, out)
    started = time.monotonic()
    rc, out, state = run("overrun", 3, (0, 1, 2), timeout_s=6)
    _starts, left, alive, kid = state.split("|")
    check("a group that overruns fails the run, said with its limit", rc == 1 and "group 0: FAILED — it did not finish in 6 s" in out, out)
    check("…after it had made its sandbox and started its sleeper (else the two checks below prove nothing)", kid != "", state)
    check("…its sandbox is removed (it was told to stop, not killed)", left == "", state)
    check("…and the process it started is gone with its process group", alive == "False", state)
    check("…without waiting out the 300 s it slept, or the grace for a child that ignores the stop", time.monotonic() - started < 25)
    rc, out, state = run("ok", 3, (0, 1, 2), jobs="16", cpus=2, nap=1.0)
    stamps = sorted(float(line.split()[1]) for line in state.split("|")[0].splitlines())
    check("an override of 16 on 2 cores runs two groups at once: the third starts after the first pair", len(stamps) == 3
          and stamps[2] - stamps[0] >= 0.9 and stamps[1] - stamps[0] < 0.9, state)
    rc, out, state = run("ok", 3, (0, 1, 2), jobs="1", cpus=8, nap=0.5)
    stamps = sorted(float(line.split()[1]) for line in state.split("|")[0].splitlines())
    check("an override of 1 runs them one after another", len(stamps) == 3 and stamps[1] - stamps[0] >= 0.4, state)
    cap = section_groups.MAX_PARALLEL_GROUPS
    section_groups.MAX_PARALLEL_GROUPS = 1
    try:
        rc, out, state = run("ok", 3, (0, 1, 2), jobs="16", cpus=8, nap=0.5)
    finally:
        section_groups.MAX_PARALLEL_GROUPS = cap
    stamps = sorted(float(line.split()[1]) for line in state.split("|")[0].splitlines())
    check("the cap on groups at once holds over a large override and many cores", len(stamps) == 3 and stamps[1] - stamps[0] >= 0.4, state)
    try:
        section_groups.drive("x", "t", 3, (0, 1), "TEST_GROUP_JOBS", 1)
        check("a group left out of the order is refused", False)
    except AssertionError:
        check("a group left out of the order is refused", True)
    print("test_section_groups:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
