#!/usr/bin/env python3
"""The launcher's TMPDIR (tools/fabric/launcher/session.py settle_tmpdir):
where the default is, that a launch prunes it and only it, and what the prune
keeps. Staleness is ctime as well as mtime, and ctime cannot be set back, so
the cases age nothing: they run the prune with a `now` past the keep window
and plant what must survive after taking that time."""
from __future__ import annotations

import os
import re
import sys
import tarfile
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import launch  # noqa: E402,F401  (loads the fabric_launcher package)
from fabric_launcher import session  # noqa: E402

WEEK = session.TMPDIR_KEEP_S


def put(path: str, text: str = "x") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class TmpdirTest(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.sandbox = self._d.name
        self.home = os.path.join(self.sandbox, "home")
        os.makedirs(self.home)

    def tearDown(self):
        self._d.cleanup()

    def later(self) -> float:
        """A `now` past the keep window of everything planted so far."""
        return time.time() + WEEK + 60

    def test_the_default_is_in_the_home_and_in_no_hidden_directory(self):
        env = {"HOME": self.home}
        session.settle_tmpdir(env)
        tmp = env["TMPDIR"]
        self.assertEqual(tmp, os.path.join(self.home, "agent-fabric-tmp"))
        self.assertEqual(oct(os.stat(tmp).st_mode & 0o777), "0o700")
        rel = os.path.relpath(tmp, self.home)
        self.assertFalse(any(part.startswith(".") for part in rel.split("/")), rel)

    def test_the_review_tools_accept_the_default(self):
        # review_codex.scratch_root and the review Bash guard both refuse a
        # home's hidden directory; the default must pass both (review of #292).
        import review_codex
        env = {"HOME": self.home}
        session.settle_tmpdir(env)
        old = tempfile.tempdir
        tempfile.tempdir = env["TMPDIR"]
        try:
            repo = os.path.join(self.sandbox, "repo")
            os.makedirs(repo)
            self.assertEqual(review_codex.scratch_root(repo, env), os.path.realpath(env["TMPDIR"]))
        finally:
            tempfile.tempdir = old
        with open(os.path.join(HERE, "runtime", "claude-code", "hooks", "review-bash-guard.py"), encoding="utf-8") as fh:
            guard = fh.read()
        ns: dict = {}
        exec(compile(re.search(r"^HOME_PATH = \(.*?\)\n", guard, re.S | re.M).group(0), "guard", "exec"), ns)
        cmd = "git -C /home/someone/agent-fabric-tmp/fabric-review/x-0123456789ab log --oneline"
        self.assertIsNone(re.search(ns["HOME_PATH"], cmd), "the guard would refuse the default as a search path")
        self.assertIsNotNone(re.search(ns["HOME_PATH"], cmd.replace("agent-fabric-tmp", ".cache/agent-fabric/tmp")),
                             "control: the guard does refuse a hidden directory")

    def test_a_launch_prunes_what_nothing_touched_for_a_week(self):
        env = {"HOME": self.home}
        tmp = session.default_tmpdir(env)
        put(f"{tmp}/stale-file")
        put(f"{tmp}/stale-dir/deep/old")
        now = self.later()
        session.settle_tmpdir(env, now=now)
        self.assertEqual(os.listdir(tmp), [])
        self.assertTrue(os.path.isdir(tmp), "the directory itself stays")

    def test_it_keeps_a_directory_written_deep_inside(self):
        env = {"HOME": self.home}
        tmp = session.default_tmpdir(env)
        put(f"{tmp}/live/a/b/old")
        put(f"{tmp}/stale")
        now = self.later()
        # Written after the window starts: what a running session does.
        os.utime(f"{tmp}/live/a/b/old", (now, now))
        session.settle_tmpdir(env, now=now)
        self.assertEqual(sorted(os.listdir(tmp)), ["live"])

    def test_it_keeps_what_arrived_recently_with_old_mtimes(self):
        # tar, cp -p, rsync -a and a rename keep old mtimes; ctime says it arrived.
        env = {"HOME": self.home}
        tmp = session.default_tmpdir(env)
        os.makedirs(tmp)
        src = os.path.join(self.sandbox, "pkg-1.0")
        put(f"{src}/member")
        old = time.time() - 30 * 86400
        for p in (f"{src}/member", src):
            os.utime(p, (old, old))
        archive = os.path.join(self.sandbox, "pkg.tar")
        with tarfile.open(archive, "w") as tar:
            tar.add(src, arcname="pkg-1.0")
        with tarfile.open(archive) as tar:
            tar.extractall(tmp, filter="tar")
        moved = os.path.join(self.sandbox, "build")
        put(f"{moved}/old")
        for p in (f"{moved}/old", moved):
            os.utime(p, (old, old))
        os.rename(moved, f"{tmp}/build")
        self.assertLess(os.lstat(f"{tmp}/pkg-1.0/member").st_mtime, time.time() - WEEK, "control: the mtimes are old")
        session.settle_tmpdir(env)
        self.assertEqual(sorted(os.listdir(tmp)), ["build", "pkg-1.0"])

    def test_a_symlink_is_judged_by_itself_and_its_target_survives(self):
        env = {"HOME": self.home}
        tmp = session.default_tmpdir(env)
        outside = os.path.join(self.sandbox, "outside")
        put(f"{outside}/old")
        os.makedirs(tmp)
        os.symlink(outside, f"{tmp}/link")
        now = self.later()
        put(f"{outside}/fresh")
        os.utime(f"{outside}/fresh", (now, now))
        walked = []
        real_walk = os.walk
        session.os.walk = lambda top, *a, **k: walked.append(top) or real_walk(top, *a, **k)
        try:
            session.settle_tmpdir(env, now=now)
        finally:
            session.os.walk = real_walk
        self.assertFalse(os.path.lexists(f"{tmp}/link"), "a stale link is removed, as itself")
        self.assertEqual(sorted(os.listdir(outside)), ["fresh", "old"], "nothing outside the TMPDIR is removed")
        self.assertNotIn(f"{tmp}/link", walked, "the link is never walked into")

    def test_a_tmpdir_the_account_set_is_used_as_it_is_and_never_pruned(self):
        own = os.path.join(self.sandbox, "own")
        put(f"{own}/old")
        env = {"HOME": self.home, "TMPDIR": own}
        session.settle_tmpdir(env, now=self.later())
        self.assertEqual(env["TMPDIR"], own)
        self.assertEqual(os.listdir(own), ["old"])
        self.assertFalse(os.path.exists(session.default_tmpdir(env)), "the default is not made beside it")

    def test_this_logins_pre_292_default_is_replaced_by_the_home_default(self):
        env = {"HOME": self.home, "TMPDIR": "/var/tmp/agent-fabric-alice"}
        session.settle_tmpdir(env, login="alice")
        self.assertEqual(env["TMPDIR"], session.default_tmpdir(env))
        self.assertTrue(os.path.isdir(env["TMPDIR"]))

    def test_another_logins_legacy_path_and_any_other_value_are_the_accounts_own(self):
        for value in ("/var/tmp/agent-fabric-bob", "/var/tmp/agent-fabric-alice/x",
                      "/var/tmp/agent-fabric-alice/", os.path.join(self.sandbox, "own")):
            env = {"HOME": self.home, "TMPDIR": value}
            session.settle_tmpdir(env, login="alice")
            self.assertEqual(env["TMPDIR"], value, value)
            self.assertFalse(os.path.exists(session.default_tmpdir(env)), value)

    def test_the_login_defaults_to_the_effective_user(self):
        import pwd
        me = pwd.getpwuid(os.geteuid()).pw_name
        env = {"HOME": self.home, "TMPDIR": session.legacy_tmpdir(me)}
        session.settle_tmpdir(env)
        self.assertEqual(env["TMPDIR"], session.default_tmpdir(env))

    def test_a_login_the_passwd_database_cannot_name_keeps_the_tmpdir(self):
        own = os.path.join(self.sandbox, "own")
        env = {"HOME": self.home, "TMPDIR": own}
        real = session.pwd.getpwuid
        session.pwd.getpwuid = lambda uid: (_ for _ in ()).throw(KeyError(uid))
        try:
            session.settle_tmpdir(env)
        finally:
            session.pwd.getpwuid = real
        self.assertEqual(env["TMPDIR"], own)


if __name__ == "__main__":
    unittest.main()
