#!/usr/bin/env python3
"""tools/fabric/langid_install.py's bounded child (quiet): the exit-code
mapping, and that a timeout or an interrupt takes the child's whole group
with it. test_langid_install.py, the oracle for the shell's contract, cannot
reach either: its pip stand-in always returns at once.

Mutations this fails on: start_new_session dropped, the killpg dropped,
the BaseException handler narrowed back to TimeoutExpired, == 0 turned
into != 0."""
from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import langid_install  # noqa: E402


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class Quiet(unittest.TestCase):
    def setUp(self) -> None:
        self.sandbox = os.path.realpath(tempfile.mkdtemp(prefix="lq."))
        self.addCleanup(shutil.rmtree, self.sandbox, ignore_errors=True)
        self.pidfile = os.path.join(self.sandbox, "grandchild.pid")
        self.addCleanup(self.reap)

    def reap(self) -> None:
        if os.path.exists(self.pidfile):
            with open(self.pidfile, encoding="utf-8") as fh:
                pid = int(fh.read())
            if alive(pid):
                os.kill(pid, signal.SIGKILL)

    @staticmethod
    def reap_group(parent: subprocess.Popen) -> None:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(parent.pid, signal.SIGKILL)
        parent.wait(timeout=10)

    def grandchild(self) -> int:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                with open(self.pidfile, encoding="utf-8") as fh:
                    return int(fh.read())
            except (OSError, ValueError):
                time.sleep(0.02)
        self.fail("the child never started its own child")

    @property
    def hang(self) -> list[str]:
        return ["sh", "-c", f"sleep 300 & echo $! > {self.pidfile}; wait"]

    def test_exit_codes_and_missing_command(self) -> None:
        self.assertTrue(langid_install.quiet(["true"], 10))
        self.assertFalse(langid_install.quiet(["false"], 10))
        self.assertFalse(langid_install.quiet([os.path.join(self.sandbox, "absent")], 10))

    def test_timeout_is_no_and_kills_the_group(self) -> None:
        started = time.monotonic()
        self.assertFalse(langid_install.quiet(self.hang, 1))
        self.assertLess(time.monotonic() - started, 30)
        pid = self.grandchild()
        time.sleep(0.2)
        self.assertFalse(alive(pid), "the timed-out child's own child survived")

    def test_interrupt_kills_the_group_and_propagates(self) -> None:
        # A terminal's Ctrl-C reaches the foreground group only: run quiet in a
        # parent of its own and send that group SIGINT, as the terminal would.
        code = ("import signal, sys; signal.signal(signal.SIGINT, signal.default_int_handler); sys.path.insert(0, %r); import langid_install, json;"
                "langid_install.quiet(json.loads(sys.argv[1]), 300)" % os.path.join(HERE, "tools", "fabric"))
        import json
        parent = subprocess.Popen([sys.executable, "-c", code, json.dumps(self.hang)],
                                  stderr=subprocess.DEVNULL, start_new_session=True)
        self.addCleanup(self.reap_group, parent)
        pid = self.grandchild()
        os.killpg(parent.pid, signal.SIGINT)
        self.assertEqual(parent.wait(timeout=30), -signal.SIGINT)
        time.sleep(0.2)
        self.assertFalse(alive(pid), "an interrupt left the child running")


class HalfMadeVenv(unittest.TestCase):
    def test_a_venv_that_fails_midway_is_removed_not_left_to_poison_the_next_run(self) -> None:
        sandbox = os.path.realpath(tempfile.mkdtemp(prefix="lh."))
        self.addCleanup(shutil.rmtree, sandbox, ignore_errors=True)
        fakebin = os.path.join(sandbox, "bin")
        os.makedirs(fakebin)
        fake = os.path.join(fakebin, "python3")
        with open(fake, "w", encoding="utf-8") as fh:
            fh.write('#!/bin/sh\nmkdir -p "$3/bin" && : > "$3/bin/python" && chmod 755 "$3/bin/python"\nexit 1\n')
        os.chmod(fake, 0o755)
        target = os.path.join(sandbox, "langid")
        env = {"PATH": f"{fakebin}{os.pathsep}/usr/bin:/bin", "HOME": sandbox, "AGENT_FABRIC_LANGID_DIR": target}
        p = subprocess.run([sys.executable, os.path.join(HERE, "tools", "fabric", "langid_install.py")],
                           env=env, capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("python3 -m venv failed", p.stdout)
        self.assertFalse(os.path.exists(os.path.join(target, "venv")), "a half-made venv was left behind")


if __name__ == "__main__":
    unittest.main()
