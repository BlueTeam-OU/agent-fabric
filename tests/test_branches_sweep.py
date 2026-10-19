#!/usr/bin/env python3
"""fabric-branches --sweep (j301, the owner 2026-10-19): a clean linked worktree whose HEAD is on a remote is removed, attached or
detached; what keeps one, and what is said. `--sweep --all` over every working copy beside this one, and the ended sessions' scratch.
Run as the command (bin/fabric-branches, override with FABRIC_BRANCHES), in sandboxes of their own; the existing oracles
tests/test_fabric_branches_cli.py and tests/test_branches.py run unchanged beside it.

Each case names the mutation it fails on, planted on tools/fabric/branches.py as formatted:
  pushed_unmerged_worktree_goes          the removal asks `n == "0" and not why` again (the old rule: on the default branch)
  detached_pushed_head_goes              the same, for a review head (detached)
  commits_on_no_remote_keep              `worktree_state` drops its `unpushed` clause
  changes_and_untracked_keep             `status_lines(path)` is read as empty
  ignored_files_keep_bytecode_does_not   `is_bytecode` always False (bytecode keeps it) or always True (a build directory goes)
  a_lock_keeps / the_current_worktree_and_in_use   the lock, "this one" and "in use" clauses dropped (`if False`)
  removal_says_size                      the "  freed" line dropped
  worktrees_only_deletes_no_branch       `--worktrees` ignored, so `zero` branches are deleted
  all_sweeps_every_copy_and_names_a_refusal   `sweep_all` ignores a copy's non-zero status (exit 0, nothing named)
  an_ended_session_goes / a_live_session_stays     the removal not asking `live` (`elif False`); `sid` not looked up in it
  a_process_that_cannot_be_read                    an unreadable claude process skipped (`continue`) where it is unknown (`return None`)
  a_link_and_other_names_are_not_followed          `session_dirs` accepting a link (`os.path.isdir`) or any name
  another_logins_cache_is_not_named      `claude_tmp_root` built from a fixed uid

The environment is built from scratch: PATH (a fake gh first, so no case reaches GitHub), HOME, LANG, TMPDIR, the state directory; no
AGENT_FABRIC_*, GITHUB_* or CLAUDE_* variable of the session reaches the command (the session id of the live case is planted)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
CMD = os.environ.get("FABRIC_BRANCHES") or os.path.join(ROOT, "bin", "fabric-branches")
UID = os.geteuid()
ENDED = "11111111-2222-3333-4444-555555555555"
LIVE = "66666666-7777-8888-9999-aaaaaaaaaaaa"
GIT = ("git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false")


class Sweep(unittest.TestCase):
    def setUp(self):
        self.t = os.path.realpath(tempfile.mkdtemp(prefix="sweep-"))
        self.addCleanup(shutil.rmtree, self.t, True)
        self.bin = os.path.join(self.t, "bin")
        os.makedirs(self.bin)
        with open(os.path.join(self.bin, "gh"), "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\necho '[]'\n")
        os.chmod(os.path.join(self.bin, "gh"), 0o755)
        self.tmp = os.path.join(self.t, "tmp")          # TMPDIR: the claude-tmp cache is under it
        os.makedirs(self.tmp)
        self.procs: list[subprocess.Popen] = []
        self.addCleanup(self.stop)
        self.origin = os.path.join(self.t, "origin.git")
        self.wc = self.repo("wc", self.origin)

    def stop(self):
        for p in self.procs:
            p.kill()
            p.wait()

    def env(self, **extra) -> dict:
        env = {"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": self.t, "LANG": "C.UTF-8", "TMPDIR": self.tmp,
               "AGENT_FABRIC_STATE_DIR": os.path.join(self.t, "state"), "GH_REPO": "o/r", "GIT_CONFIG_GLOBAL": os.devnull,
               "PYTHONDONTWRITEBYTECODE": "1"}
        env.update(extra)
        return env

    def git(self, cwd, *args, ok=False) -> str:
        r = subprocess.run([*GIT, "-C", cwd, *args], env=self.env(), capture_output=True, text=True, timeout=60)
        if r.returncode and not ok:
            raise AssertionError(f"git {args}: {r.stderr}")
        return r.stdout

    def repo(self, name, origin) -> str:
        path = os.path.join(self.t, name)
        if not os.path.isdir(origin):
            subprocess.run(["git", "init", "-q", "--bare", "-b", "main", origin], env=self.env(), check=True, timeout=30)
        subprocess.run(["git", "clone", "-q", origin, path], env=self.env(), check=True, timeout=30, stderr=subprocess.DEVNULL)
        self.git(path, "commit", "-q", "--allow-empty", "-m", "base")
        self.git(path, "push", "-q", "origin", "HEAD:main")
        self.git(path, "remote", "set-head", "origin", "main")
        return path

    def worktree(self, name, *, pushed: bool, detach=False, wc=None) -> str:
        """A linked worktree one commit past main: pushed to its own remote branch, or not."""
        wc = wc or self.wc
        path = os.path.join(self.t, name)
        self.git(wc, "worktree", "add", "-q", "-b", name, path, "main")
        self.git(path, "commit", "-q", "--allow-empty", "-m", name)
        if pushed:
            self.git(path, "push", "-q", "origin", f"{name}:{name}")
            self.git(path, "fetch", "-q", "origin")
        if detach:
            self.git(path, "checkout", "-q", "--detach")
            if pushed:
                self.git(wc, "branch", "-q", "-D", name)
        return path

    def sweep(self, *args, cwd=None, **extra):
        r = subprocess.run([CMD, "--sweep", *args], cwd=cwd or self.wc, env=self.env(**extra), capture_output=True, text=True, timeout=300)
        return r.returncode, r.stdout, r.stderr

    def test_pushed_unmerged_worktree_goes(self):
        wt = self.worktree("drain", pushed=True)
        rc, out, err = self.sweep()
        self.assertEqual(rc, 0, err)
        self.assertFalse(os.path.exists(wt))
        self.assertIn(f"removed worktree {wt}", out.splitlines())
        self.assertIn("drain", self.git(self.wc, "branch", "--list", "drain"), "its branch is not touched")

    def test_detached_pushed_head_goes(self):
        wt = self.worktree("review-head", pushed=True, detach=True)
        rc, out, err = self.sweep()
        self.assertEqual(rc, 0, err)
        self.assertFalse(os.path.exists(wt), out)

    def test_commits_on_no_remote_keep(self):
        wt = self.worktree("owed", pushed=False)
        rc, out, err = self.sweep()
        self.assertTrue(os.path.isdir(wt))
        self.assertIn("1 commit(s) on no remote", out)
        self.assertNotIn(f"removed worktree {wt}", out)

    def test_changes_and_untracked_keep(self):
        dirty = self.worktree("dirty", pushed=True)
        with open(os.path.join(dirty, "new"), "w", encoding="utf-8") as fh:
            fh.write("x\n")
        edited = self.worktree("edited", pushed=True)
        self.git(edited, "commit", "-q", "--allow-empty", "-m", "x")
        with open(os.path.join(edited, "f"), "w", encoding="utf-8") as fh:
            fh.write("1\n")
        self.git(edited, "add", "f")
        self.git(edited, "commit", "-q", "-m", "f")
        self.git(edited, "push", "-q", "origin", "edited:edited")
        self.git(edited, "fetch", "-q", "origin")
        with open(os.path.join(edited, "f"), "w", encoding="utf-8") as fh:
            fh.write("2\n")
        rc, out, err = self.sweep()
        self.assertTrue(os.path.isdir(dirty) and os.path.isdir(edited), out)
        self.assertEqual(out.count("uncommitted change(s)"), 2, out)

    def test_ignored_files_keep_bytecode_does_not(self):
        for wc_name in ("ignoring",):
            with open(os.path.join(self.wc, ".gitignore"), "w", encoding="utf-8") as fh:
                fh.write("__pycache__/\n*.pyc\nbuild/\n.env\n")
            self.git(self.wc, "add", ".gitignore")
            self.git(self.wc, "commit", "-q", "-m", "ignore")
            self.git(self.wc, "push", "-q", "origin", "HEAD:main")
            self.git(self.wc, "fetch", "-q", "origin")
        byte = self.worktree("bytecode", pushed=True)
        os.makedirs(os.path.join(byte, "pkg", "__pycache__"))
        for f in (os.path.join("pkg", "__pycache__", "a.cpython.pyc"), "loose.pyc"):
            open(os.path.join(byte, f), "wb").close()
        built = self.worktree("built", pushed=True)
        os.makedirs(os.path.join(built, "build"))
        open(os.path.join(built, "build", "out"), "wb").close()
        secret = self.worktree("secret", pushed=True)
        open(os.path.join(secret, ".env"), "wb").close()
        rc, out, err = self.sweep()
        self.assertFalse(os.path.exists(byte), "bytecode alone does not keep a worktree")
        self.assertTrue(os.path.isdir(built) and os.path.isdir(secret), out)
        self.assertEqual(out.count("ignored path(s)"), 2, out)

    def test_a_lock_keeps(self):
        wt = self.worktree("held", pushed=True)
        self.git(self.wc, "worktree", "lock", wt)
        rc, out, err = self.sweep()
        self.assertTrue(os.path.isdir(wt))
        self.assertRegex(out, r"(?m)^  1   .*/held  held  locked$")

    def test_the_current_worktree_and_in_use_are_kept(self):
        here = self.worktree("here", pushed=True)
        used = self.worktree("used", pushed=True)
        rc, out, err = self.sweep(cwd=here, AGENT_FABRIC_BRANCHES_KEEP=used)
        self.assertTrue(os.path.isdir(here) and os.path.isdir(used), out)
        self.assertIn("this one", out)
        self.assertIn("in use", out)

    def test_removal_says_size(self):
        wt = self.worktree("sized", pushed=True)
        with open(os.path.join(wt, "blob"), "wb") as fh:
            fh.write(b"x" * 3000)
        self.git(wt, "add", "blob")
        self.git(wt, "commit", "-q", "-m", "blob")
        self.git(wt, "push", "-q", "origin", "sized:sized")
        self.git(wt, "fetch", "-q", "origin")
        rc, out, err = self.sweep()
        lines = out.splitlines()
        i = lines.index(f"removed worktree {wt}")
        self.assertRegex(lines[i + 1], r"^  freed [0-9.]+ (B|KB)$")

    def test_worktrees_only_deletes_no_branch(self):
        self.git(self.wc, "branch", "at-tip", "main")          # a queued job's branch: 0 commits, on the default branch
        wt = self.worktree("drain", pushed=True)
        rc, out, err = self.sweep("--worktrees")
        self.assertFalse(os.path.exists(wt))
        self.assertIn("at-tip", self.git(self.wc, "branch", "--list", "at-tip"), "--worktrees deletes no branch")
        rc, out, err = self.sweep()
        self.assertEqual(self.git(self.wc, "branch", "--list", "at-tip").strip(), "", "the plain sweep still does")

    def test_all_sweeps_every_copy_and_names_a_refusal(self):
        other_origin = os.path.join(self.t, "other-origin.git")
        other = self.repo("other", other_origin)
        broken = self.repo("broken", os.path.join(self.t, "broken-origin.git"))
        self.git(broken, "remote", "set-url", "origin", os.path.join(self.t, "nowhere.git"))
        mine = self.worktree("mine", pushed=True)
        theirs = self.worktree("theirs", pushed=True, wc=other)
        stuck = self.worktree("stuck", pushed=True, wc=broken) if False else None
        rc, out, err = self.sweep("--all")
        self.assertEqual(rc, 1, out + err)
        self.assertFalse(os.path.exists(mine) or os.path.exists(theirs), out)
        self.assertIn(f"skipped, not swept or not recorded: {broken} (exit 2)", out)
        self.assertIn("git fetch origin failed", err)
        self.assertIsNone(stuck)

    def sessions(self, *names) -> list[str]:
        root = os.path.join(self.tmp, f"claude-{UID}", "-proj")
        out = []
        for n in names:
            d = os.path.join(root, n)
            os.makedirs(os.path.join(d, "scratchpad"))
            with open(os.path.join(d, "scratchpad", "f"), "w", encoding="utf-8") as fh:
                fh.write("x" * 2048)
            out.append(d)
        return out

    def test_an_ended_session_goes(self):
        (d,) = self.sessions(ENDED)
        rc, out, err = self.sweep()
        self.assertFalse(os.path.exists(d), out)
        self.assertRegex(out, rf"removed session scratch {d} \(2\.0 KB\)")

    def test_a_live_session_stays(self):
        ended, live = self.sessions(ENDED, LIVE)
        self.procs.append(subprocess.Popen(["sleep", "300"], env=self.env(CLAUDE_CODE_SESSION_ID=LIVE)))
        rc, out, err = self.sweep()
        self.assertTrue(os.path.isdir(live) and not os.path.exists(ended), out)
        self.assertIn(f"kept session scratch {live} — live session", out)

    def test_own_session_stays(self):
        (d,) = self.sessions(ENDED)
        rc, out, err = self.sweep(CLAUDE_CODE_SESSION_ID=ENDED)
        self.assertTrue(os.path.isdir(d), out)

    def test_unreadable_process_keeps_all(self):
        sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
        import branches
        (d,) = self.sessions(ENDED)
        saved_env, saved_live = dict(os.environ), branches.live_sessions
        os.environ["TMPDIR"] = self.tmp
        branches.live_sessions = lambda: None
        try:
            branches.sweep_sessions()
        finally:
            branches.live_sessions = saved_live
            os.environ.clear()
            os.environ.update(saved_env)
        self.assertTrue(os.path.isdir(d), "a process that cannot be read is unknown, never 'no session'")

    def test_a_process_that_cannot_be_read_is_unknown_unless_it_is_no_session(self):
        sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
        import branches
        fake = os.path.join(self.t, "proc")
        for pid, cmdline in (("101", b"claude\0--resume"), ("102", b"sshd-session: me")):
            os.makedirs(os.path.join(fake, pid))
            with open(os.path.join(fake, pid, "environ"), "wb") as fh:
                fh.write(f"CLAUDE_CODE_SESSION_ID={LIVE}\0".encode())
            with open(os.path.join(fake, pid, "cmdline"), "wb") as fh:
                fh.write(cmdline)
            os.chmod(os.path.join(fake, pid, "environ"), 0)
        self.assertIsNone(branches.live_sessions(fake), "claude's own environment unreadable: nothing is known")
        shutil.rmtree(os.path.join(fake, "101"))
        self.assertEqual(branches.live_sessions(fake), set(), "a daemon that is not a session is no reason to keep everything")
        os.chmod(os.path.join(fake, "102", "environ"), 0o644)
        self.assertEqual(branches.live_sessions(fake), {LIVE}, "and a readable one names its session")

    def test_a_link_and_other_names_are_not_followed(self):
        outside = os.path.join(self.t, "precious")
        os.makedirs(outside)
        open(os.path.join(outside, "f"), "w", encoding="utf-8").close()
        root = os.path.join(self.tmp, f"claude-{UID}", "-proj")
        os.makedirs(os.path.join(root, "not-a-session-id", "x"))
        os.symlink(outside, os.path.join(root, ENDED))
        rc, out, err = self.sweep()
        self.assertTrue(os.path.exists(os.path.join(outside, "f")) and os.path.islink(os.path.join(root, ENDED)), out)
        self.assertNotIn(ENDED, out, "a link is not a session directory: not removed, not even named")
        self.assertTrue(os.path.isdir(os.path.join(root, "not-a-session-id", "x")))

    def test_another_logins_cache_is_not_named(self):
        other = os.path.join(self.tmp, f"claude-{UID + 1}", "-proj", ENDED)
        os.makedirs(other)
        rc, out, err = self.sweep()
        self.assertTrue(os.path.isdir(other), out)


if __name__ == "__main__":
    unittest.main()
