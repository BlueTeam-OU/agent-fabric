#!/usr/bin/env python3
"""The client unit's program (agent-fabric ADR-064 §5 rule 5): its source,
runtime/interweave/client, its installer (tools/fabric/gzcoord/carrier/
install_client.py) and the worker step that runs the installer as
the new account. The program is run for real in a scratch HOME with a fake
carrier behind $HOME/.local/bin/gzcoord-carrier, in the minimal environment
a systemd user unit has."""
from __future__ import annotations

import io
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools", "fabric")
sys.path.insert(0, TOOLS)
from gzcoord.carrier import install_client as inst  # noqa: E402
from provisioning import worker, worker_args as wa  # noqa: E402

INSTALLER = os.path.join(TOOLS, "gzcoord", "carrier", "install_client.py")
SOURCE = os.path.join(ROOT, "runtime", "interweave", "client")
LOGIN = "zz-unit-login"


def mode(path: str) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def run_installer(home: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", INSTALLER, *args], env={"HOME": home, "PATH": os.environ["PATH"]},
                          capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)


class Installer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="iw-client.")
        self.addCleanup(self.tmp.cleanup)
        self.home = self.tmp.name
        self.target = os.path.join(self.home, ".local", "libexec", "interweave", "client")

    def test_the_source_is_executable_in_git_and_the_copy_is_0755_with_its_bytes(self):
        self.assertEqual(mode(SOURCE), 0o755)
        got = run_installer(self.home)
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertIn("installed ~/.local/libexec/interweave/client", got.stderr)
        self.assertEqual(mode(self.target), 0o755)
        with open(SOURCE, "rb") as a, open(self.target, "rb") as b:
            self.assertEqual(a.read(), b.read())
        self.assertEqual(os.listdir(os.path.dirname(self.target)), ["client"], "no temporary left beside it")

    def test_a_second_run_changes_nothing_and_says_so(self):
        run_installer(self.home)
        before = os.stat(self.target)
        got = run_installer(self.home)
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertIn("already", got.stderr)
        self.assertEqual(os.stat(self.target).st_ino, before.st_ino, "not rewritten")

    def test_an_edited_copy_a_wrong_mode_and_a_symlink_are_each_put_right(self):
        run_installer(self.home)
        with open(self.target, "w") as fh:
            fh.write("#!/bin/sh\necho edited\n")
        self.assertIn("installed", run_installer(self.home).stderr)
        with open(SOURCE, "rb") as a, open(self.target, "rb") as b:
            self.assertEqual(a.read(), b.read())
        os.chmod(self.target, 0o700)
        self.assertIn("installed", run_installer(self.home).stderr)
        self.assertEqual(mode(self.target), 0o755)
        elsewhere = os.path.join(self.home, "elsewhere")
        with open(elsewhere, "w") as fh:
            fh.write("keep")
        os.unlink(self.target)
        os.symlink(elsewhere, self.target)
        self.assertEqual(run_installer(self.home).returncode, 0)
        self.assertFalse(os.path.islink(self.target))
        with open(elsewhere) as fh:
            self.assertEqual(fh.read(), "keep", "the link's target is not written through")

    def test_a_home_that_cannot_be_written_and_a_bad_call_are_failures_said_on_stderr(self):
        blocker = os.path.join(self.home, "file")
        open(blocker, "w").close()
        got = run_installer(blocker)
        self.assertEqual((got.returncode, got.stdout), (1, ""))
        self.assertIn("install_client:", got.stderr)
        self.assertEqual(run_installer(self.home, "extra").returncode, 2)
        env = {"PATH": os.environ["PATH"]}
        nohome = subprocess.run([sys.executable, "-I", INSTALLER], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(nohome.returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".local")), "positive control: the failing runs wrote nothing here")


class Program(unittest.TestCase):
    """The installed copy, run as the unit runs it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="iw-client.")
        self.addCleanup(self.tmp.cleanup)
        self.home = self.tmp.name
        inst.install(self.home)
        self.client = os.path.join(self.home, ".local", "libexec", "interweave", "client")

    def start(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([self.client, *args], env={"HOME": self.home, "PATH": "/usr/bin:/bin"},
                              capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)

    def fake_carrier(self) -> str:
        bindir = os.path.join(self.home, ".local", "bin")
        os.makedirs(bindir)
        path = os.path.join(bindir, "gzcoord-carrier")
        with open(path, "w") as fh:
            fh.write('#!/bin/sh\nfor a in "$@"; do printf "[%s]" "$a"; done\nexit 7\n')
        os.chmod(path, 0o755)
        return path

    def test_it_execs_the_carriers_run_with_the_units_arguments_and_its_exit_status(self):
        self.fake_carrier()
        got = self.start("--profile", "gzcoord")
        self.assertEqual((got.stdout, got.returncode), ("[run][--profile][gzcoord]", 7))

    def test_without_the_carrier_it_says_what_to_run_and_exits_127(self):
        got = self.start("--profile", "gzcoord")
        self.assertEqual(got.returncode, 127)
        self.assertIn("bootstrap.sh", got.stderr)
        self.assertEqual(got.stdout, "")


class Step(unittest.TestCase):
    def worker(self, *argv: str) -> worker.Worker:
        w = worker.Worker(wa.parse_args(["finish", LOGIN, "python-dev", "--no-claude-account", *argv]), root=ROOT, env={})
        w.home = f"/home/{LOGIN}"
        return w

    def test_the_step_runs_the_installer_from_the_accounts_clone_as_the_account(self):
        calls, err = [], io.StringIO()

        def fake(argv, **kw):
            calls.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        with mock.patch.object(subprocess, "run", fake), redirect_stderr(err):
            worker.install_client(self.worker())
        self.assertEqual(len(calls), 1, calls)
        mine = f"/home/{LOGIN}/projects/agent-fabric/tools/fabric/gzcoord/carrier/install_client.py"
        self.assertEqual(calls[0][-3:], [worker.PY, "-I", mine])
        self.assertIn(LOGIN, calls[0])
        self.assertIn("7b. carrier client unit program installed", err.getvalue())

    def test_a_dry_run_runs_nothing_and_a_failure_stops_the_run(self):
        calls, err = [], io.StringIO()
        with mock.patch.object(subprocess, "run", side_effect=lambda *a, **k: calls.append(a)), redirect_stderr(err):
            worker.install_client(self.worker("--dry-run"))
        self.assertEqual(calls, [])
        self.assertIn(f"would: as {LOGIN}: install_client.py", err.getvalue())
        with mock.patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 1, stdout="boom\n", stderr="")), \
                redirect_stderr(io.StringIO()):
            with self.assertRaises(worker.Stop):
                worker.install_client(self.worker())

    def test_finish_installs_it_after_bootstrap_for_an_agent_and_never_for_a_human(self):
        for human in (False, True):
            order = []
            w = self.worker()
            w.a = wa.parse_args(["finish", LOGIN, *(["--human"] if human else ["python-dev", "--no-claude-account"]), "--dry-run"])
            with mock.patch.object(worker, "record_launch_provider", lambda w: order.append("record")), \
                    mock.patch.object(worker, "bootstrap_and_bind", lambda w: order.append("bootstrap")), \
                    mock.patch.object(worker, "install_client", lambda w: order.append("client")), \
                    mock.patch.object(worker, "toolchains", lambda w: order.append("toolchains")), \
                    mock.patch.object(worker, "operator_ssh", lambda w: None), \
                    mock.patch.object(worker, "verify", lambda w: 0), redirect_stderr(io.StringIO()):
                worker.finish(w)
            self.assertEqual(order, [] if human else ["record", "bootstrap", "client", "toolchains"], human)


if __name__ == "__main__":
    unittest.main()
