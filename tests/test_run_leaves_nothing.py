#!/usr/bin/env python3
"""A run, through tests/run.sh, leaves nothing behind however it ends (ADR-021): the forwarding from run.sh to run.py, the
run's own TMPDIR, and a run ended by TERM, by a group KILL, and by TERM then KILL while a suite ignores TERM.
tests/test_leak-check.sh (deleted, Wave 9 batch 10), case for case. run.py's own leak report on a planted entry, the
section argument and the signals through fake trees are tests/test_run.py's; this file runs the real tests/run.sh on the
real tree, as the bash test did, with a fake `shellcheck` first on PATH that blocks, so the static section stops where
the signal is wanted.

The bash test's cases, each a method here:
  the run, through run.sh, on a directory of its own
    test_run_sh_forwards_to_run_py_which_reports_with_leak_report   (run.sh's forwarding line and run.py's leak_report; and,
                                                                     what the greps stood for, run.sh names itself on the
                                                                     lines run.py prints)
    test_the_run_exports_its_own_tmpdir                             (the TMPDIR export; and the environment a suite gets)
  a run killed by a signal ENDS, and its directory goes with it
    test_term_ends_the_run_and_its_directory_goes                   (made its directory; TERM ends it; exit 143; directory
                                                                     gone; no suite counted as failed)
  a run killed by a group KILL leaves no directory and no process
    test_group_kill_leaves_no_directory_and_no_process
  a group KILL during cleanup's wait, with a suite that ignores TERM, leaves no directory
    test_term_then_kill_during_the_wait_leaves_no_directory

Changed from the bash, and why: the bash bound "TERM ends the run within fifteen seconds" was a stopwatch, and a stopwatch fails
under load (a bound of 7.4 s against 7 s failed once in twenty in tests/test_run.py). The fake shellcheck here sleeps 120 s and
the run must be gone within 60 s of the TERM: a run that does not end its suites' tree is still there at 60 s, one that does
is gone in the cleanup's ten. Every wait for a state hands the run to the wait and fails the case as a failed precondition
when the run ended first or the ceiling passed, instead of signalling a run that was never in the state (tests/test_run.py).

Mutations (planted one at a time on the source as formatted, 2026-10-19, each restored; the test that fails is named):
  run.sh: `AGENT_FABRIC_RUNNER=tests/run.sh` -> `...run.shx`          test_run_sh_forwards_...
  run.py: `def leak_report` renamed; leak_report returning False      test_run_sh_forwards_...
          after naming an entry
  run.py: `env["TMPDIR"] = scratch` -> the caller's TMPDIR when set   test_the_run_exports_its_own_tmpdir
  run.py: `return 128 + int(s.args[0])` -> `return 1`                 test_term_ends_...      (exit status)
  run.py: stop() no longer raises Signalled (the signal is ignored)   test_term_ends_...      (exit status, counted failure)
  run.py: the final `shutil.rmtree(scratch, ...)` removed             test_term_ends_...      (directory left)
  run.py: invoke()'s final `raise` -> `return 143`                    test_term_ends_...      (counted as a suite failure)
  run.py: the watcher without `start_new_session=True`                test_group_kill_..., test_term_then_kill_...
  run.py: suites started with `start_new_session=True`                test_group_kill_...     (the suite survives the KILL; only
                                                                      its own pid shows it: it is in no listing of the group)
  run.py: stop() kills the watcher                                    test_term_then_kill_...
Exit codes: 0 all passed, non-zero on any failure (unittest)."""
from __future__ import annotations

import contextlib
import io
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
import run  # noqa: E402 — tests/run.py: the module under test, for run_environment

RUN_SH = os.path.join(ROOT, "tests", "run.sh")
RUN_PY = os.path.join(ROOT, "tests", "run.py")
READY_TIMEOUT_S = 120.0
END_TIMEOUT_S = 60.0


class RunLeavesNothing(unittest.TestCase):
    def setUp(self) -> None:
        self.sandbox = tempfile.mkdtemp(prefix="leak.")
        self.addCleanup(shutil.rmtree, self.sandbox, ignore_errors=True)
        self.started: list[subprocess.Popen] = []
        self.addCleanup(self.end_groups)

    def end_groups(self) -> None:
        for p in self.started:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                p.wait(timeout=30)
            except subprocess.TimeoutExpired:
                pass

    def fake_shellcheck(self, name: str, body: str) -> str:
        """A directory holding an executable `shellcheck` that is `body`: the static section blocks in it."""
        bindir = os.path.join(self.sandbox, name)
        os.makedirs(bindir)
        path = os.path.join(bindir, "shellcheck")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("#!/usr/bin/env bash\n" + body)
        os.chmod(path, 0o755)
        return bindir

    def environment(self, bindir: str, runtmp: str) -> dict[str, str]:
        # Not the session's: its PATH, HOME, credentials or AGENT_FABRIC_*. run.sh makes af-t.* under XDG_RUNTIME_DIR
        # (short_dir), so that is pointed at the sandbox.
        return {"PATH": f"{bindir}:{os.path.dirname(sys.executable)}:/usr/bin:/bin", "HOME": os.path.join(self.sandbox, "home"),
                "XDG_RUNTIME_DIR": runtmp, "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}

    def start(self, name: str, shellcheck_body: str) -> tuple[subprocess.Popen, str, str]:
        """`run.sh static` in a process group of its own, over the real tree: (the run, its runtime directory, its output)."""
        runtmp = os.path.join(self.sandbox, f"runtmp-{name}")
        os.makedirs(runtmp)
        out = os.path.join(self.sandbox, f"{name}.out")
        bindir = self.fake_shellcheck(f"bin-{name}", shellcheck_body)
        with open(out, "w", encoding="utf-8") as fh:
            p = subprocess.Popen(["bash", RUN_SH, "static"], cwd=ROOT, env=self.environment(bindir, runtmp), stdin=subprocess.DEVNULL,
                                 stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)
        self.started.append(p)
        return p, runtmp, out

    def wait_for(self, p: subprocess.Popen, ready, what: str, timeout: float = READY_TIMEOUT_S) -> None:
        """Waits for `ready` with the run alive. A signal sent to a run that never reached the state proves nothing, so a run
        that ended first or a ceiling that passed ends the run and fails the case as a failed precondition."""
        deadline = time.monotonic() + timeout
        while not ready():
            if p.poll() is not None:
                why = f"the run exited ({p.returncode}) before {what}"
            elif time.monotonic() > deadline:
                why = f"{what} did not happen within {timeout:g} s"
            else:
                time.sleep(0.1)
                continue
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
            self.fail(f"precondition: {why}")

    @staticmethod
    def slurp(path: str) -> str:
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    @staticmethod
    def entries(directory: str) -> list[str]:
        return sorted(os.listdir(directory))

    @staticmethod
    def running(pid: int) -> bool:
        try:
            with open(f"/proc/{pid}/stat", "rb") as fh:
                return fh.read().rsplit(b")", 1)[1].split()[0] != b"Z"
        except (OSError, IndexError):
            return False

    @staticmethod
    def alive_in_group(pgid: int) -> list[str]:
        """A zombie is dead, only not yet reaped: a container with no init as PID 1 never reaps the orphans, so only
        processes that still run count."""
        ps = subprocess.run(["ps", "-e", "-o", "pgid=,stat=,pid=,args="], capture_output=True, text=True, check=True, timeout=30)
        found = []
        for line in ps.stdout.splitlines():
            fields = line.split(None, 3)
            if len(fields) >= 3 and fields[0] == str(pgid) and not fields[1].startswith("Z"):
                found.append(line.strip())
        return found

    def test_run_sh_forwards_to_run_py_which_reports_with_leak_report(self) -> None:
        forwarder, runner = self.slurp(RUN_SH), self.slurp(RUN_PY)
        self.assertRegex(forwarder, re.compile(r'^AGENT_FABRIC_RUNNER=tests/run\.sh exec python3 .*tests/run\.py" "\$@"$', re.M),
                         "run.sh forwards to run.py")
        self.assertRegex(runner, re.compile(r"^def leak_report\(", re.M), "run.py reports with its leak_report")
        # The substring the bash grep looked for is also in `def leak_reportx`; the function itself says what it reports.
        planted = os.path.join(self.sandbox, "planted")
        os.makedirs(os.path.join(planted, "left behind"))
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            found = run.leak_report(planted, [])
            nothing = run.leak_report(planted, ["left behind"])
        self.assertEqual((found, nothing), (True, False))
        self.assertIn("   left behind\n", said.getvalue())
        # What the two greps stood for: a section the runner does not know is refused under run.sh's own name, so the
        # forwarder reached run.py and said who started it.
        p = subprocess.run(["bash", RUN_SH, "bogus"], cwd=ROOT, env=self.environment("/nonexistent", self.sandbox),
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60, check=False)
        self.assertEqual((p.returncode, p.stdout), (2, ""), p.stderr)
        self.assertTrue(p.stderr.startswith("tests/run.sh: no section 'bogus'"), p.stderr)

    def test_the_run_exports_its_own_tmpdir(self) -> None:
        self.assertIn('env["TMPDIR"] = scratch', self.slurp(RUN_PY), "the run exports its own TMPDIR")
        # So a concurrent writer is never a leak: whatever TMPDIR the caller had, a suite gets the run's directory.
        env = run.run_environment({"TMPDIR": "/the/callers", "PATH": "/usr/bin"}, "/the/runs")
        self.assertEqual(env["TMPDIR"], "/the/runs")
        self.assertEqual(env["PATH"], "/usr/bin")

    def test_term_ends_the_run_and_its_directory_goes(self) -> None:
        # Behaviour, not text: a trap that removed the directory and let the script carry on passed a grep for its own
        # line while every remaining suite ran against a deleted TMPDIR. A static run in its own group, a shellcheck
        # that blocks, TERM to the group: the run must end, with no af-t.* left under the directory it was made in.
        p, runtmp, out = self.start("term", "sleep 120\n")
        self.wait_for(p, lambda: any(n.startswith("af-t.") for n in os.listdir(runtmp)), "the run made its directory")
        os.killpg(p.pid, signal.SIGTERM)
        try:
            rc = p.wait(timeout=END_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            self.fail(f"the run outlived TERM by {END_TIMEOUT_S:g} s: {self.slurp(out)}")
        self.assertEqual(rc, 143, "and it exits 143, the conventional status")
        self.assertEqual(self.entries(runtmp), [], "and its directory is gone")
        self.assertNotIn("suite(s) FAILED", self.slurp(out), "the interrupted run reports no suite failures")

    def test_group_kill_leaves_no_directory_and_no_process(self) -> None:
        # KILL runs no trap: the directories go by the watcher run.py starts.
        pidfile = os.path.join(self.sandbox, "shellcheck.pid")
        p, runtmp, _out = self.start("kill", f'echo $$ > "{pidfile}"\nsleep 120\n')
        self.wait_for(p, lambda: os.path.exists(pidfile) and self.slurp(pidfile).strip() != "", "the suite started")
        self.wait_for(p, lambda: any(n.startswith("af-t.") for n in os.listdir(runtmp)), "the run made its directory")
        os.killpg(p.pid, signal.SIGKILL)
        p.wait(timeout=END_TIMEOUT_S)
        deadline = time.monotonic() + 30
        while self.entries(runtmp) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertEqual(self.entries(runtmp), [], "a group KILL leaves no directory behind")
        self.assertEqual(self.alive_in_group(p.pid), [], "and no process of the group survives")
        # Beyond the bash's group listing: a suite that left the group (a session of its own) is in no listing of it, yet
        # survives the group KILL; the fake suite's own pid is looked up whatever its group.
        self.assertFalse(self.running(int(self.slurp(pidfile))), "nor does the suite, wherever it runs")

    def test_term_then_kill_during_the_wait_leaves_no_directory(self) -> None:
        # Cleanup must not TERM the watcher: the suite (a shellcheck that ignores TERM, the static section's tool; the
        # forwarder execs python3 into the run, so a stand-in python3 would BE the run and prove nothing) outlives the
        # first signal, so cleanup is still waiting when the KILL comes, and only the watcher can remove the directory.
        started = os.path.join(self.sandbox, "started")
        p, runtmp, out = self.start("stubborn", f'trap "" TERM\ntouch "{started}"\nsleep 120\n')
        self.wait_for(p, lambda: os.path.exists(started), "the suite that ignores TERM started")
        os.kill(p.pid, signal.SIGTERM)
        # The run is in cleanup, waiting on the suite that ignored TERM: not yet gone, not yet killed by the grace.
        self.wait_for(p, lambda: any(n.startswith("af-t.") for n in os.listdir(runtmp)), "the run still waiting on the suite that ignored TERM")
        time.sleep(1)
        os.killpg(p.pid, signal.SIGKILL)
        p.wait(timeout=END_TIMEOUT_S)
        deadline = time.monotonic() + 30
        while self.entries(runtmp) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertEqual(self.entries(runtmp), [], f"TERM then KILL during the wait leaves no directory: {self.slurp(out)}")


if __name__ == "__main__":
    unittest.main()
