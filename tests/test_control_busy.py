#!/usr/bin/env python3
"""The account's busy locks across processes (tools/fabric/control/busy.py, and
how upgrade, restart and secrets-sync use them). agentd and `fabric-op` are two
processes of one account; a flag in a module is not seen by the other. Every
"another process holds it" case here is a real child process holding the real
flock, never a fake; each refusal has its positive control (the same call with
nothing held does the work), and a run leaves all three locks free."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from control import busy, restart as R, upgrade as U  # noqa: E402
import test_control_secrets as TS  # noqa: E402

HOLDER = """
import sys
sys.path.insert(0, sys.argv[1])
from control import busy
fd = busy.hold(sys.argv[2], sys.argv[3], shared=sys.argv[4] == "shared")
print("held" if fd is not None else "refused", flush=True)
sys.stdin.read()
"""


class Held:
    """Another process holding `name` in `directory` until the block ends (or it is killed)."""

    def __init__(self, directory: str, name: str, shared: bool = False) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-c", HOLDER, os.path.join(HERE, "tools", "fabric"), directory, name, "shared" if shared else "exclusive"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, env={"PATH": os.environ.get("PATH", "")}, text=True)
        said = self.proc.stdout.readline().strip()
        assert said == "held", said

    def kill(self) -> None:
        self.proc.send_signal(signal.SIGKILL)
        self.proc.wait(timeout=30)

    def __enter__(self) -> "Held":
        return self

    def __exit__(self, *_exc) -> None:
        self.proc.stdin.close()
        self.proc.wait(timeout=30)
        self.proc.stdout.close()


class Case(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="busy-")
        self.addCleanup(tmp.cleanup)
        self.dir = os.path.join(tmp.name, "state")
        self.addCleanup(self.assert_all_free)

    def assert_all_free(self) -> None:
        for name in busy.NAMES:
            self.assertFalse(busy.held(self.dir, name), f"{name} was left held")


class Primitives(Case):
    def test_exclusive_refuses_both_kinds_shared_refuses_exclusive_only(self):
        a = busy.hold(self.dir, "marker", shared=True)
        b = busy.hold(self.dir, "marker", shared=True)
        self.assertIsNotNone(a)
        self.assertIsNotNone(b, "two shared holds overlap")
        self.assertIsNone(busy.hold(self.dir, "marker"))
        busy.release(a)
        busy.release(b)
        x = busy.hold(self.dir, "marker")
        self.assertIsNotNone(x)
        self.assertIsNone(busy.hold(self.dir, "marker", shared=True))
        self.assertTrue(busy.held(self.dir, "marker"))
        busy.release(x)
        self.assertFalse(busy.held(self.dir, "marker"))

    def test_names_are_independent(self):
        x = busy.hold(self.dir, "sync")
        try:
            self.assertFalse(busy.held(self.dir, "restart"))
            self.assertTrue(busy.held(self.dir, "sync"))
        finally:
            busy.release(x)

    def test_a_holder_that_dies_leaves_no_stale_lock_and_a_live_one_does(self):
        with Held(self.dir, "restart") as h:
            self.assertTrue(busy.held(self.dir, "restart"), "positive control: the child's lock is seen")
            h.kill()
            self.assertFalse(busy.held(self.dir, "restart"))

    def test_a_child_the_holder_starts_does_not_keep_the_lock(self):
        fd = busy.hold(self.dir, "sync")
        child = subprocess.Popen(["sleep", "30"], close_fds=False, env={"PATH": os.environ.get("PATH", "")})
        try:
            busy.release(fd)
            self.assertFalse(busy.held(self.dir, "sync"))
        finally:
            child.kill()
            child.wait()

    def test_a_lock_that_cannot_be_opened_is_unavailable_never_free(self):
        os.makedirs(self.dir)
        os.symlink("/dev/null", os.path.join(self.dir, "busy-sync"))
        with self.assertRaises(busy.Unavailable):
            busy.held(self.dir, "sync")
        with self.assertRaises(busy.Unavailable):
            busy.hold(self.dir, "sync")
        os.unlink(os.path.join(self.dir, "busy-sync"))
        with open(os.path.join(self.dir, "x"), "w") as fh:
            fh.write("a file where the directory should be")
        with self.assertRaises(busy.Unavailable):
            busy.hold(os.path.join(self.dir, "x"), "sync")


class UpgradeBeside(Case):
    def run_upgrade(self) -> dict:
        saved = U.upgrade_once
        U.upgrade_once = lambda request, **opts: {"status": "ran"}
        try:
            return U.upgrade({"id": "u"}, directory=self.dir)
        finally:
            U.upgrade_once = saved

    def test_another_processes_upgrade_or_restart_makes_it_busy_and_nothing_runs(self):
        self.assertEqual(self.run_upgrade(), {"status": "ran"})
        with Held(self.dir, "marker"):
            self.assertEqual(self.run_upgrade(), {"status": "busy", "note": "an upgrade is already running on this account"})
        with Held(self.dir, "marker", shared=True):
            self.assertEqual(self.run_upgrade(), {"status": "busy", "note": "a secrets-sync is restarting the session on this account"})
        self.assertEqual(self.run_upgrade(), {"status": "ran"}, "the hold went with the holder")

    def test_it_holds_the_marker_while_it_runs(self):
        seen = []
        saved = U.upgrade_once
        U.upgrade_once = lambda request, **opts: seen.append((busy.held(self.dir, "marker"), busy.hold(self.dir, "marker", shared=True))) or {"status": "ran"}
        try:
            U.upgrade({"id": "u"}, directory=self.dir)
        finally:
            U.upgrade_once = saved
        self.assertEqual(seen, [(True, None)])

    def test_a_lock_it_cannot_take_is_a_failure_with_nothing_run(self):
        os.makedirs(self.dir)
        os.symlink("/dev/null", os.path.join(self.dir, "busy-marker"))
        r = self.run_upgrade()
        self.assertEqual(r["status"], "failed")
        self.assertIn("nothing stopped", r["reason"])
        os.unlink(os.path.join(self.dir, "busy-marker"))


class RestartBeside(Case):
    def run_restart(self) -> dict:
        return R.restart({"id": "r", "from": "h/user"}, directory=self.dir, me="h/py", sessions=[])

    def test_another_processes_restart_upgrade_or_sync_stops_it_and_a_free_account_does_not(self):
        self.assertEqual(self.run_restart(), {"status": "no-session"})
        with Held(self.dir, "restart"):
            self.assertEqual(self.run_restart()["status"], "busy")
        with Held(self.dir, "marker"):
            r = self.run_restart()
            self.assertEqual(r["status"], "failed")
            self.assertIn("an upgrade is running", r["reason"])
        with Held(self.dir, "marker", shared=True):
            self.assertEqual(self.run_restart(), {"status": "no-session"}, "a secrets-sync's restart phase shares the marker")
        with Held(self.dir, "sync"):
            r = self.run_restart()
            self.assertEqual(r["status"], "failed")
            self.assertIn("a secrets-sync is running", r["reason"])
        self.assertEqual(self.run_restart(), {"status": "no-session"})

    def test_a_lock_it_cannot_take_is_a_failure_and_releases_the_process_lock(self):
        os.makedirs(self.dir)
        os.symlink("/dev/null", os.path.join(self.dir, "busy-restart"))
        r = self.run_restart()
        self.assertEqual(r["status"], "failed")
        self.assertFalse(R.running(), "the in-process lock is released on this path too")
        os.unlink(os.path.join(self.dir, "busy-restart"))


class SyncBeside(Case):
    def sync(self, **more) -> tuple[dict, list]:
        f = TS.Fixture(self, before=TS.OLD)
        f.opts["directory"] = self.dir
        sigs: list[int] = []
        r = f.sync({"id": "s", "from": "h/user", "args": {"restart": True}}, sessions=[3], me="h/db-admin", env_of=TS.env_with(TS.OLD),
                   kill=lambda p, s: sigs.append(s), alive=lambda p: not sigs, sleep=lambda s: None, **more)
        return r, sigs

    def test_another_processes_sync_makes_it_busy_and_an_upgrade_or_restart_stops_the_restart(self):
        r, sigs = self.sync()
        self.assertEqual((r["status"], r["session"], sigs), ("synced", "restarting", [signal.SIGTERM]))
        with Held(self.dir, "sync"):
            r, sigs = self.sync()
            self.assertEqual((r["status"], sigs), ("busy", []))
        with Held(self.dir, "marker"):
            r, sigs = self.sync()
            self.assertEqual((r["status"], sigs), ("failed", []))
            self.assertIn("an upgrade is running", r["reason"])
        with Held(self.dir, "restart"):
            r, sigs = self.sync()
            self.assertEqual((r["status"], sigs), ("failed", []))
            self.assertIn("a restart is running", r["reason"])

    def test_it_holds_sync_and_the_marker_shared_while_it_stops_the_session(self):
        seen = []
        f = TS.Fixture(self, before=TS.OLD)
        f.opts["directory"] = self.dir

        def kill(pid, sig):
            other = busy.hold(self.dir, "marker", shared=True)   # the marker is shared, as a restart's is
            busy.release(other)
            seen.append((busy.held(self.dir, "sync"), busy.hold(self.dir, "marker") is None, other is not None))
        f.sync({"id": "s", "from": "h/user", "args": {"restart": True}}, sessions=[3], me="h/db-admin", env_of=TS.env_with(TS.OLD),
               kill=kill, alive=lambda p: False, sleep=lambda s: None)
        self.assertEqual(seen, [(True, True, True)])


if __name__ == "__main__":
    unittest.main()
