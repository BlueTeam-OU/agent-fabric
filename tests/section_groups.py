"""Run the sections of a long end-to-end CLI suite side by side. A suite that takes this shape keeps its sections in
groups (`if _want(n):` blocks that need nothing from one another), each run as a child of the suite with its own sandbox:
the cases are the same, the wall time is the longest group's. This is the parent half, and the child's signal setup.

Bounded by the cores: the CI wrapper may run suites in parallel too, so the groups of one suite never outnumber
os.cpu_count(), whatever the override says, and never MAX_PARALLEL_GROUPS (the gateway section's timing checks see the
load of the others past about four)."""
from __future__ import annotations

import concurrent.futures
import os
import signal
import subprocess
import sys

MAX_PARALLEL_GROUPS = 4
GRACE_S = 30


def child_setup() -> None:
    """A group that is told to stop unwinds, so its TemporaryDirectory goes and its `with` blocks run."""
    signal.signal(signal.SIGTERM, lambda _signum, _frame: sys.exit(143))


def _one(script: str, group: int, timeout_s: int) -> tuple[int, str]:
    proc = subprocess.Popen([sys.executable, script, "--group", str(group)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, errors="replace", start_new_session=True)
    try:
        out, _ = proc.communicate(timeout=timeout_s)
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        # The whole process group, so the launchers and fakes the group started stop with it; SIGTERM first so its
        # sandbox is removed, SIGKILL only if it does not unwind.
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            out, _ = proc.communicate(timeout=GRACE_S)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            out, _ = proc.communicate()
        return 1, f"{out}\ngroup {group}: FAILED — it did not finish in {timeout_s} s\n"


def drive(script: str, label: str, ngroups: int, slowest_first: tuple[int, ...], jobs_env: str, timeout_s: int) -> int:
    """Run every group, print each one's output in the order of the sections, and fail if any group did."""
    assert sorted(slowest_first) == list(range(ngroups)), "every group is run once"
    cpus = os.cpu_count() or 1
    asked = int(os.environ.get(jobs_env) or MAX_PARALLEL_GROUPS)
    jobs = max(1, min(asked, cpus, MAX_PARALLEL_GROUPS))
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {g: pool.submit(_one, os.path.abspath(script), g, timeout_s) for g in slowest_first}
        results = [futures[g].result() for g in range(ngroups)]
    failed = 0
    for rc, text in results:
        sys.stdout.write(text)
        failed += rc != 0
    print(f"\n{label}: {'OK' if not failed else f'FAILED — {failed} group(s)'}")
    return 1 if failed else 0
