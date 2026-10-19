#!/usr/bin/env python3
"""A run of tests/run.sh leaves nothing behind however it ends (ADR-021; Wave 9 batch 10, ADR-040 rule 5). run.py's own leak
report is test_run.py's. The entry point is ONE constant, ENTRY (the path CI and every habit invoke; override with
LEAK_CHECK_ENTRY), run as a command in a process group of its own, so this file runs unchanged against the bash forwarder today
and against the port of the suite runners later.

The bash oracle tests/test_leak-check.sh, case for case (each is a method here):
  run_forwards_and_reports_by_its_name        "run.sh forwards to run.py, which reports with its leak_report": the bash test grepped the
                                              forwarder's exec line and run.py's source for a function name; text is not behaviour, so
                                              here the run is asked for an unknown section and must answer under the name tests/run.sh
                                              (stderr, exit 2) - the forwarder's variable reached the runner
  run_exports_its_own_tmpdir                  "the run exports its own TMPDIR": a stand-in shellcheck, the static section's tool, writes
                                              the TMPDIR it was given; it is a directory af-t.* made under XDG_RUNTIME_DIR
  term_ends_the_run_with_its_directory        "a run killed by a signal ENDS, and its directory goes with it": the run made af-t.* under
                                              XDG_RUNTIME_DIR; TERM to the group ends it within fifteen seconds; exit 143; the directory
                                              is gone; no "suite(s) FAILED" line
  group_kill_leaves_no_directory_or_process   "a run killed by a group KILL leaves no directory and no process": the watcher removes
                                              the directory; no process of the run's tree, taken by parent links before the signal, still runs (a zombie is dead, only unreaped)
  term_then_kill_during_the_wait              "a group KILL during cleanup's wait, with a suite that ignores TERM, leaves no directory"
Cases the bash test does not carry: the stand-in tool blocks the run until the test signals it, so every signal lands on a run
that has its directory and a live suite (a missing directory fails the case by name, before the signal). That made-directory assertion
is the positive control of the three "gone" assertions, which are otherwise true of a run that never made a directory.

Mutations each case fails on (one per behaviour; planted on tests/run.py as formatted): dropping `env["TMPDIR"] = scratch` (TMPDIR);
returning 1 instead of `128 + signum` from `except Signalled` (exit 143); removing the `shutil.rmtree(scratch ...)` in `finally`
(TERM); killing the watcher at once after it starts (group KILL, and TERM then KILL); starting a suite with start_new_session=True in invoke() (group KILL, and TERM then KILL: a group KILL no longer reaches it); naming the runner tests/run.py instead of reading the variable (forwards by its name).

The environment is built from scratch: PATH (the stand-in first), HOME, LANG, XDG_RUNTIME_DIR of the case's own; no
AGENT_FABRIC_*, GITHUB_* or CLAUDE_* variable of the session reaches the run."""
from __future__ import annotations

import glob
import os
import shutil
import signal
import sys
import subprocess
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.environ.get("LEAK_CHECK_ENTRY") or os.path.join(ROOT, "tests", "run.sh")
BLOCKING = "#!/usr/bin/env bash\nprintf '%s' \"$$\" > \"$STARTED\"\nsleep 30\n"
# the TERM-deaf suite: cleanup is still waiting when the KILL comes, so only the watcher can remove the directory
DEAF = "#!/usr/bin/env bash\ntrap '' TERM\nprintf '%s' \"$$\" > \"$STARTED\"\nsleep 30\n"
RECORDING = "#!/usr/bin/env bash\nprintf '%s' \"$TMPDIR\" > \"$STARTED\"\nsleep 30\n"


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
                "PYTHONDONTWRITEBYTECODE": "1", "STARTED": self.started}

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

    def started_run(self, body: str) -> subprocess.Popen:
        """A run blocked in the static section's tool, with its directory made: the state every signal case needs."""
        proc = self.start(self.stand_in(body))
        self.assertTrue(self.wait_for(lambda: os.path.exists(self.started) and os.path.getsize(self.started) > 0),
                        "the stand-in tool never started\n" + self.output())
        # taken before the signal: the pids are what must be gone after it, wherever the run put its suites
        self.tree = tree_of(proc.pid)
        self.assertTrue(self.made_dirs(), "the run made no af-t.* under XDG_RUNTIME_DIR: " + repr(os.listdir(self.runtmp)))
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

    def test_run_exports_its_own_tmpdir(self):
        proc = self.start(self.stand_in(RECORDING))
        self.assertTrue(self.wait_for(lambda: os.path.exists(self.started) and os.path.getsize(self.started) > 0), self.output())
        with open(self.started, encoding="utf-8") as fh:
            tmpdir = fh.read()
        made = self.made_dirs()
        self.assertEqual(len(made), 1, made)
        self.assertEqual(tmpdir, made[0], "a suite's TMPDIR is not the run's own directory")
        os.killpg(proc.pid, signal.SIGTERM)
        self.assertTrue(self.ended(proc, 15))

    def test_term_ends_the_run_with_its_directory(self):
        before = os.listdir(self.runtmp)
        proc = self.started_run(BLOCKING)
        os.killpg(proc.pid, signal.SIGTERM)
        # run.py's cleanup TERMs its suites, KILLs what is left after 5 s and waits about 10 s in all, so a loaded runner may
        # take that long: 15 s is the bound.
        self.assertTrue(self.ended(proc, 15), "the run outlived TERM\n" + self.output())
        self.assertEqual(proc.returncode, 143, self.output())
        self.assertEqual(os.listdir(self.runtmp), before, "the run's directory is left")
        self.assertNotIn("suite(s) FAILED", self.output())

    def test_group_kill_leaves_no_directory_or_process(self):
        proc = self.started_run(BLOCKING)
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        # KILL runs no trap: the directory goes by the watcher the run started
        self.assertTrue(self.wait_for(lambda: not os.listdir(self.runtmp), 10), repr(os.listdir(self.runtmp)))
        # the watcher exits after it has removed the directory, so the tree is polled, not read once
        self.wait_for(lambda: not alive(self.tree), 10)
        self.assertEqual(alive(self.tree), [])

    def test_term_then_kill_during_the_wait(self):
        proc = self.started_run(DEAF)
        os.kill(proc.pid, signal.SIGTERM)
        time.sleep(1)
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        self.assertTrue(self.wait_for(lambda: not os.listdir(self.runtmp), 10), repr(os.listdir(self.runtmp)))
        # the watcher exits after it has removed the directory, so the tree is polled, not read once
        self.wait_for(lambda: not alive(self.tree), 10)
        self.assertEqual(alive(self.tree), [])


if __name__ == "__main__":
    unittest.main()
