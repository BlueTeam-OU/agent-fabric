#!/usr/bin/env python3
"""A run of tests/run.sh leaves nothing behind however it ends (ADR-021; Wave 9 batch 10, ADR-040 rule 5). run.py's own leak
report is test_run.py's. The entry point is ONE constant, ENTRY (the path CI and every habit invoke; override with
LEAK_CHECK_ENTRY), run as a command in a process group of its own, so this file runs unchanged against the bash forwarder today
and against the port of the suite runners later.

The retired bash test tests/test_leak-check.sh (deleted, Wave 9 batch 10), case for case (each is a method here):
  run_forwards_and_reports_by_its_name        "run.sh forwards to run.py, which reports with its leak_report": the bash test grepped the
                                              forwarder's exec line and run.py's source for a function name; text is not behaviour, so
                                              here the run is asked for an unknown section and must answer under the name tests/run.sh
                                              (stderr, exit 2) - the forwarder's variable reached the runner
  run_exports_its_own_tmpdir                  "the run exports its own TMPDIR": a stand-in shellcheck, the static section's tool, writes
                                              the TMPDIR it was given; it is a directory af-t.* made under XDG_RUNTIME_DIR
  term_ends_the_run_with_its_directory        "a run killed by a signal ENDS, and its directory goes with it": the run made af-t.* under
                                              XDG_RUNTIME_DIR; TERM to the group ends it within END_S (a ceiling against a suite that sleeps 120 s); exit 143; the directory
                                              is gone; no "suite(s) FAILED" line
  group_kill_leaves_no_directory_or_process   "a run killed by a group KILL leaves no directory and no process": the watcher removes
                                              the directory; no process of the run's tree, taken by parent links before the signal, still runs (a zombie is dead, only unreaped)
  term_then_kill_during_the_wait              "a group KILL during cleanup's wait, with a suite that ignores TERM, leaves no directory"
Cases the bash test does not carry: the stand-in tool blocks the run until the test signals it, so every signal lands on a run
that has its directory and a live suite (a missing directory fails the case by name, before the signal). That made-directory assertion
is the positive control of the three "gone" assertions, which are otherwise true of a run that never made a directory.

Mutations each case fails on (one per behaviour; planted on tests/run.py as formatted): dropping `env["TMPDIR"] = scratch`, or letting the caller's TMPDIR outrank it (TMPDIR);
returning 1 instead of `128 + signum` from `except Signalled` (exit 143); removing the `shutil.rmtree(scratch ...)` in `finally`
(TERM); killing the watcher at once after it starts (group KILL, and TERM then KILL); starting a suite with start_new_session=True in invoke() (group KILL, and TERM then KILL: a group KILL no longer reaches it); naming the runner tests/run.py instead of reading the variable (forwards by its name); `def leak_report` renamed, or returning False after it names an entry (leak report).
Each was planted one at a time, 2026-10-19, and restored; the bounds are ceilings, not stopwatches (END_S, READY_S below), and a state waited for is a precondition that names itself when the run exited first or the ceiling passed.

The environment is built from scratch: PATH (the stand-in first), HOME, LANG, XDG_RUNTIME_DIR of the case's own; no
AGENT_FABRIC_*, GITHUB_* or CLAUDE_* variable of the session reaches the run."""
from __future__ import annotations

import contextlib
import glob
import io
import os
import re
import shutil
import signal
import sys
import subprocess
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
ENTRY = os.environ.get("LEAK_CHECK_ENTRY") or os.path.join(ROOT, "tests", "run.sh")
# A bound is a ceiling a loaded machine does not reach, never a stopwatch: the stand-ins sleep 120 s, so a run that does not end
# its suites is still there when END_S passes, and one that does is gone in the cleanup's ten (a 15 s bound failed under load).
READY_S = 120.0
END_S = 60.0
BLOCKING = "#!/usr/bin/env bash\nprintf '%s' \"$$\" > \"$STARTED\"\nsleep 120\n"
# the TERM-deaf suite: cleanup is still waiting when the KILL comes, so only the watcher can remove the directory
# It writes "$STARTED.term" when it is TERMed and stays: the case waits for that file, so the KILL lands while cleanup waits on it, never
# on a timer. Its child ignores TERM (a handler is not inherited, an ignore is) and `wait` returns on the trap, so it loops.
# $STARTED is written by the child once it ignores TERM (a subshell resets a handler until its own trap runs, and a TERM before that
# would end it), so "started" means a suite that cleanup can only wait on, and the tree snapshot holds the child.
DEAF = ("#!/usr/bin/env bash\ntrap 'printf x > \"$STARTED.term\"' TERM\n"
        "(trap '' TERM; printf '%s' \"$$\" > \"$STARTED\"; exec sleep 120) &\n"
        "child=$!\nwhile kill -0 $child 2>/dev/null; do wait $child; done\n")
RECORDING = "#!/usr/bin/env bash\nprintf '%s' \"$TMPDIR\" > \"$STARTED\"\nsleep 120\n"


def stat_fields(pid: int) -> list[str] | None:
    """State, ppid and pgrp of a process, None once it is gone. The comm field may hold spaces and parentheses: cut at the last one."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    return text[text.rindex(")") + 2:].split()


def tree_of(root: int) -> list[int]:
    """The run and everything below it, by parent links. A suite a run started outside its process group is still in this list,
    which the group alone (what a group KILL reaches) would not show."""
    parent = {}
    for stat in glob.glob("/proc/[0-9]*/stat"):
        pid = int(stat.split("/")[2])
        fields = stat_fields(pid)
        if fields:
            parent[pid] = int(fields[1])
    found, grew = {root}, True
    while grew:
        grew = False
        for pid, ppid in parent.items():
            if ppid in found and pid not in found:
                found.add(pid)
                grew = True
    return sorted(found)


def alive(pids: list[int]) -> list[int]:
    """Those that still run; a zombie is dead, only not yet reaped, and a container with no init as PID 1 never reaps."""
    return [p for p in pids if (f := stat_fields(p)) and f[0] != "Z"]


class RunLeaves(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="leak-check-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.runtmp = os.path.join(self.tmp, "runtmp")
        os.mkdir(self.runtmp)
        self.started = os.path.join(self.tmp, "started")
        # The caller's TMPDIR, a directory that is not the run's: the run must hand its suites its own, not pass this one on
        # (a concurrent writer in the caller's directory is then never mistaken for a leak).
        self.decoy = os.path.join(self.tmp, "callers-tmp")
        os.mkdir(self.decoy)
        self.groups: list[int] = []
        self.tree: list[int] = []
        self.addCleanup(self.reap_groups)

    def reap_groups(self):
        for pgid in self.groups:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for pid in alive(self.tree):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def env(self, bindir=None) -> dict:
        # the interpreter running this test comes after the stand-in: run.sh's `python3` is then the host's, as CI's, not /usr/bin's
        path = (bindir + ":" if bindir else "") + os.path.dirname(sys.executable) + ":/usr/bin:/bin"
        return {"PATH": path, "HOME": self.tmp, "LANG": "C.UTF-8", "XDG_RUNTIME_DIR": self.runtmp,
                "PYTHONDONTWRITEBYTECODE": "1", "STARTED": self.started, "TMPDIR": self.decoy}

    def stand_in(self, body: str, name="bin") -> str:
        bindir = os.path.join(self.tmp, name)
        os.mkdir(bindir)
        tool = os.path.join(bindir, "shellcheck")
        with open(tool, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.chmod(tool, 0o755)
        return bindir

    def start(self, bindir, out_name="run.out") -> subprocess.Popen:
        self.out = open(os.path.join(self.tmp, out_name), "w", encoding="utf-8")
        self.addCleanup(self.out.close)
        proc = subprocess.Popen([ENTRY, "static"], env=self.env(bindir), cwd=ROOT, stdin=subprocess.DEVNULL, stdout=self.out,
                                stderr=subprocess.STDOUT, start_new_session=True)
        self.groups.append(proc.pid)
        return proc

    def output(self) -> str:
        self.out.flush()
        with open(self.out.name, encoding="utf-8", errors="replace") as fh:
            return fh.read()

    def made_dirs(self) -> list[str]:
        return glob.glob(os.path.join(self.runtmp, "af-t.*"))

    def wait_for(self, what, timeout=30.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if what():
                return True
            time.sleep(0.1)
        return what()

    def await_state(self, proc, ready, what, timeout=READY_S) -> None:
        """Waits for a state the case signals the run in, with the run alive. A signal sent to a run that never reached it proves
        nothing (tests/test_run.py met the same: a run signalled before its suites existed exited right with nothing to show), so
        a run that exited first or a ceiling that passed ends the run and fails the case as a failed precondition, named."""
        deadline = time.monotonic() + timeout
        while not ready():
            if proc.poll() is not None:
                why = f"the run exited ({proc.returncode}) before {what}"
            elif time.monotonic() > deadline:
                why = f"{what} did not happen within {timeout:g} s"
            else:
                time.sleep(0.1)
                continue
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.fail(f"precondition: {why}\n" + self.output())

    def started_run(self, body: str) -> subprocess.Popen:
        """A run blocked in the static section's tool, with its directory made: the state every signal case needs."""
        proc = self.start(self.stand_in(body))
        self.await_state(proc, lambda: os.path.exists(self.started) and os.path.getsize(self.started) > 0, "the stand-in tool started")
        # taken before the signal: the pids are what must be gone after it, wherever the run put its suites
        self.tree = tree_of(proc.pid)
        self.await_state(proc, self.made_dirs, "the run made its af-t.* under XDG_RUNTIME_DIR")
        return proc

    def ended(self, proc, seconds) -> bool:
        try:
            proc.wait(timeout=seconds)
            return True
        except subprocess.TimeoutExpired:
            return False

    def test_run_forwards_and_reports_by_its_name(self):
        done = subprocess.run([ENTRY, "no-such-section"], env=self.env(), cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 2)
        self.assertEqual(done.stdout, "")
        self.assertTrue(done.stderr.startswith("tests/run.sh: no section 'no-such-section'"), done.stderr)
        self.assertEqual(os.listdir(self.runtmp), [], "a refused run made a directory")

    @unittest.skipIf(os.environ.get("LEAK_CHECK_ENTRY"), "run.py's own function: not what another entry's suite runner is asked")
    def test_leak_report_is_a_function_that_names_what_is_left(self):
        # The bash test grepped run.py for `def leak_report`, a substring that `def leak_reportx` also holds. The function is
        # called: a directory entry not in the snapshot is named and True is returned; one that was in it is not.
        import run
        with open(run.__file__, encoding="utf-8") as fh:
            self.assertRegex(fh.read(), re.compile(r"^def leak_report\(", re.M))
        planted = os.path.join(self.tmp, "planted")
        os.makedirs(os.path.join(planted, "left behind"))
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            found = run.leak_report(planted, [])
            nothing = run.leak_report(planted, ["left behind"])
        self.assertEqual((found, nothing), (True, False))
        self.assertIn("   left behind\n", said.getvalue())

    def test_run_exports_its_own_tmpdir(self):
        proc = self.start(self.stand_in(RECORDING))
        self.await_state(proc, lambda: os.path.exists(self.started) and os.path.getsize(self.started) > 0, "the stand-in tool started")
        with open(self.started, encoding="utf-8") as fh:
            tmpdir = fh.read()
        made = self.made_dirs()
        self.assertEqual(len(made), 1, made)
        self.assertEqual(tmpdir, made[0], "a suite's TMPDIR is not the run's own directory")
        self.assertNotEqual(tmpdir, self.decoy, "the caller's TMPDIR reached the suite")
        os.killpg(proc.pid, signal.SIGTERM)
        self.assertTrue(self.ended(proc, END_S), "the run outlived TERM\n" + self.output())

    def test_term_ends_the_run_with_its_directory(self):
        before = os.listdir(self.runtmp)
        proc = self.started_run(BLOCKING)
        os.killpg(proc.pid, signal.SIGTERM)
        # run.py's cleanup TERMs its suites, KILLs what is left after 5 s and waits about 10 s in all: the bash test's bound of
        # fifteen seconds was a stopwatch that a loaded runner can pass, so END_S is against a suite that sleeps 120 s.
        self.assertTrue(self.ended(proc, END_S), "the run outlived TERM\n" + self.output())
        self.assertEqual(proc.returncode, 143, self.output())
        self.assertEqual(os.listdir(self.runtmp), before, "the run's directory is left")
        self.assertNotIn("suite(s) FAILED", self.output())

    def test_group_kill_leaves_no_directory_or_process(self):
        proc = self.started_run(BLOCKING)
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        # KILL runs no trap: the directory goes by the watcher the run started
        self.assertTrue(self.wait_for(lambda: not os.listdir(self.runtmp), END_S), repr(os.listdir(self.runtmp)))
        # the watcher exits after it has removed the directory, so the tree is polled, not read once
        self.wait_for(lambda: not alive(self.tree), END_S)
        self.assertEqual(alive(self.tree), [])

    def test_term_then_kill_during_the_wait(self):
        proc = self.started_run(DEAF)
        os.kill(proc.pid, signal.SIGTERM)
        # cleanup has TERMed the suite and is now waiting out its grace on it: the state the KILL is meant to land in
        self.await_state(proc, lambda: os.path.exists(self.started + ".term"), "cleanup TERMed the suite that ignores it")
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        # The .term file stays once written, and cleanup waits only its 5 s grace: a test process stalled past it sends the KILL to a
        # run that has already finished (exit 143, directory removed by cleanup, no watcher needed), a pass that proves nothing.
        self.assertEqual(proc.returncode, -signal.SIGKILL, "precondition: cleanup ended the run before the KILL landed")
        self.assertTrue(self.wait_for(lambda: not os.listdir(self.runtmp), END_S), repr(os.listdir(self.runtmp)))
        # the watcher exits after it has removed the directory, so the tree is polled, not read once
        self.wait_for(lambda: not alive(self.tree), END_S)
        self.assertEqual(alive(self.tree), [])


if __name__ == "__main__":
    unittest.main()
