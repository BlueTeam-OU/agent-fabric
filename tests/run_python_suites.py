#!/usr/bin/env python3
"""The python suites of tests/run.sh, up to AGENT_FABRIC_TEST_JOBS at a time.

Default: the cores; 1 is the old serial run. Each suite is independent: it
makes its own scratch under the run's TMPDIR (exported by run.sh), binds
port 0 for any socket and gives itself a HOME (the one fixed path,
/var/tmp/agent-fabric-<login> in test_launch_cli, is created idempotently).
The slowest start first, so the last one started is a short one and not the
3-minute launcher alone at the end. A suite's output is buffered and printed
whole when it ends, under the "== <suite>" header the serial run printed, so
the log reads the same but in completion order. Exit status: 1 if any suite
failed, 2 for a bad AGENT_FABRIC_TEST_JOBS. The last line of stdout is
`FAILED_SUITES=<n>`, n the number of suites that exited non-zero (0 when none),
so run.sh can say how many failed and not only that one did; it is not printed
for the exit 2, where nothing ran, nor when the runner itself fails or is killed
(a suite that cannot be started raises out of its worker; a signal ends the
process): a missing line is "unknown, at least one", never 0.

run.sh starts this in the background (`&`, then `wait`), so a trap fires at
once; bash starts an async command with INT and QUIT ignored, and every suite
would inherit that (test_fabric_lease_cli asserts its command is not deaf to
them). set -m would restore them but puts each job in a group of its own,
which run.sh's group-wide signals and its cleanup rely on not happening; so
the dispositions are reset here, before the first suite starts.
"""
import concurrent.futures
import glob
import os
import signal
import subprocess
import sys
import threading

SLOW = (
    "test_launch_cli", "test_new_agent_cli", "test_gzcoord_port", "test_bootstrap_cli",
    "test_secret_store", "test_control_agentd", "test_gzcoord_protocol", "test_jobs",
    "test_roots_readers", "test_control_ctl", "test_pr_review_status_cli", "test_arm_cli",
    "test_session_start", "test_lint", "test_assemble",
)
HERE = os.path.dirname(os.path.abspath(__file__))


def ordered_suites() -> list[str]:
    every = sorted(glob.glob(os.path.join("tests", "test_*.py")))
    slow = [p for p in (os.path.join("tests", n + ".py") for n in SLOW) if p in every]
    return slow + [p for p in every if p not in slow]


def main() -> int:
    for sig in (signal.SIGINT, signal.SIGQUIT):
        signal.signal(sig, signal.SIG_DFL)
    os.chdir(os.path.dirname(HERE))
    slots = os.environ.get("AGENT_FABRIC_TEST_JOBS") or str(os.cpu_count() or 1)
    if not (slots.isdigit() and int(slots) >= 1):
        print(f"tests/run.sh: AGENT_FABRIC_TEST_JOBS='{slots}' is not a positive number", file=sys.stderr)
        return 2
    printing = threading.Lock()
    failed = 0

    def run(path: str) -> None:
        nonlocal failed
        done = subprocess.run([sys.executable, path], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        with printing:
            sys.stdout.write(f"\n== {path}\n")
            sys.stdout.flush()
            sys.stdout.buffer.write(done.stdout)
            sys.stdout.buffer.flush()
            failed += done.returncode != 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=int(slots)) as pool:
        list(pool.map(run, ordered_suites()))
    # A suite's output is written whole and may end without a newline: the count starts a line of its own.
    print(f"\nFAILED_SUITES={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
