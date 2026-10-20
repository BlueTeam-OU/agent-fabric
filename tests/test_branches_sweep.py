#!/usr/bin/env python3
"""fabric-branches --sweep (j301, the owner 2026-10-19): a clean linked worktree whose HEAD is on a remote is removed, attached or
detached; what keeps one, and what is said. `--sweep --all` over every working copy beside this one, and the ended sessions' scratch.
Run as the command (bin/fabric-branches, override with FABRIC_BRANCHES), in sandboxes of their own; the existing oracles
tests/test_fabric_branches_cli.py and tests/test_branches.py run unchanged beside it.

Each case names the mutation it fails on, planted on the source as formatted (29 were, each caught; the case is the test's name):
  tools/fabric/branches.py   removal asks `n == "0"` again (pushed_unmerged, detached_pushed_head, all_sweeps); `unpushed` clause dropped
                             (commits_on_no_remote, a_branch_the_remote_no_longer_has); changes read as none (changes_and_untracked);
                             `is_bytecode` always False or True (ignored_files); lock / "this one" / "in use" / live-cwd clauses dropped
                             (a_lock, the_current_worktree_and_in_use, a_worktree_a_live_session_stands_in); the "  freed" line
                             (removal_says_size); `--worktrees` ignored or a typo accepted (worktrees_only, a_misspelled_second_argument);
                             `sweep_all` ignoring a copy's status or forgetting the worktree it runs from (all_sweeps, all_from_a_linked);
                             remote_refs not filtered by ls-remote (a_branch_the_remote_no_longer_has); the removal not asking `live`, the
                             own session ignored, a dead harness read as live, a broken or malformed registry entry skipped, a missing
                             registry read as empty (the session cases); `session_dirs` following a link or taking any name; the cache of
                             uid + 1 (another_logins_cache).
  jobsparts, control         the switch's sweep not run / run without --worktrees / its report on stdout in --json / the kept lines dropped
                             (test_jobs_switch); the control agent's removable count on the old rule (test_control_branches).

The environment is built from scratch: PATH (a fake gh first, so no case reaches GitHub), HOME, LANG, TMPDIR, the state directory; no
AGENT_FABRIC_*, GITHUB_* or CLAUDE_* variable of the session reaches the command (the session id of the live case is planted)."""
from __future__ import annotations

import json
import os
import re
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
        self.cfg = os.path.join(self.t, "claude-config")   # CLAUDE_CONFIG_DIR: the harness's registry of its sessions is under it
        self.procs: list[subprocess.Popen] = []
        self.addCleanup(self.stop)
        self.origin = os.path.join(self.t, "origin.git")
        self.wc = self.repo("wc", self.origin)
        self.registry()   # a registry that lists no session: readable, so a sweep removes what it proves removable. The tests of an unreadable one delete it

    def stop(self):
        for p in self.procs:
            p.kill()
            p.wait()

    def env(self, **extra) -> dict:
        env = {"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": self.t, "LANG": "C.UTF-8", "TMPDIR": self.tmp,
               "AGENT_FABRIC_STATE_DIR": os.path.join(self.t, "state"), "GH_REPO": "o/r", "GIT_CONFIG_GLOBAL": os.devnull,
               "PYTHONDONTWRITEBYTECODE": "1", "CLAUDE_CONFIG_DIR": self.cfg}
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
        rc, out, err = self.sweep("--all")
        self.assertEqual(rc, 1, out + err)
        self.assertFalse(os.path.exists(mine) or os.path.exists(theirs), out)
        self.assertIn(f"skipped, not swept or not recorded: {broken} (exit 2)", out)
        self.assertIn("git fetch origin failed", err)

    def registry(self, *entries) -> None:
        """The harness's registry: sessions/<pid>.json, (session id, pid, cwd) each, procStart as /proc says it."""
        sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
        import plan_hold
        directory = os.path.join(self.cfg, "sessions")
        os.makedirs(directory, exist_ok=True)
        for sid, pid, cwd in entries:
            with open(os.path.join(directory, f"{pid}.json"), "w", encoding="utf-8") as fh:
                json.dump({"pid": pid, "sessionId": sid, "cwd": cwd, "procStart": plan_hold.start_of(str(pid))}, fh)

    def harness(self) -> int:
        """A process that runs for the test, whose environment carries no session id: the harness's own does not either."""
        p = subprocess.Popen(["sleep", "300"], env=self.env())
        self.procs.append(p)
        return p.pid

    def test_a_branch_the_remote_no_longer_has_is_no_proof(self):
        wt = self.worktree("gone-upstream", pushed=True, detach=True)
        subprocess.run(["git", "-C", self.origin, "branch", "-q", "-D", "gone-upstream"], env=self.env(), check=True)
        rc, out, err = self.sweep()        # the fetch does not prune: refs/remotes/origin/gone-upstream is still here
        self.assertIn("refs/remotes/origin/gone-upstream", self.git(self.wc, "for-each-ref", "refs/remotes/origin/gone-upstream"))
        self.assertTrue(os.path.isdir(wt), out)
        self.assertIn("1 commit(s) on no remote", out)

    def test_a_branch_force_pushed_since_the_fetch_is_no_proof(self):
        sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
        import branches
        self.worktree("moved", pushed=True)
        self.git(self.wc, "fetch", "-q", "origin")
        other = os.path.join(self.t, "other")
        subprocess.run(["git", "clone", "-q", self.origin, other], env=self.env(), check=True, stderr=subprocess.DEVNULL)
        self.git(other, "checkout", "-q", "-b", "elsewhere", "origin/main")
        self.git(other, "commit", "-q", "--allow-empty", "-m", "different")
        self.git(other, "push", "-q", "-f", "origin", "elsewhere:moved")        # the name is still there, the commit is not
        self.git(other, "push", "-q", "origin", "elsewhere:elsewhere")
        self.git(self.wc, "fetch", "-q", "origin", "elsewhere:refs/remotes/origin/elsewhere")
        self.git(other, "push", "-q", "origin", "elsewhere:main")             # the default moves after the fetch: its old tip is still proven
        cwd = os.getcwd()
        os.chdir(self.wc)
        try:
            refs = branches.remote_refs("refs/remotes/origin/main")
        finally:
            os.chdir(cwd)
        self.assertIn("refs/remotes/origin/main", refs, "the base was fetched a moment ago; a push to it since does not unprove it")
        self.assertIn("refs/remotes/origin/elsewhere", refs, "ls-remote answered: a ref that is the same commit on both sides counts")
        self.assertNotIn("refs/remotes/origin/moved", refs, "the remote's branch of that name is another commit now")

    def no_registry(self) -> None:
        shutil.rmtree(os.path.join(self.cfg, "sessions"))

    def unreadable_registry(self) -> None:
        with open(os.path.join(self.cfg, "sessions", "1.json"), "w", encoding="utf-8") as fh:
            fh.write("{broken")

    def test_an_unlistable_registry_is_said_for_the_worktrees_too(self):
        self.worktree("w", pushed=True)
        self.no_registry()
        rc, out, err = self.sweep()
        self.assertIn("no worktree is removed", err)
        self.assertIn(os.path.join(self.cfg, "sessions"), err, "it names the directory it looked in")

    def test_a_missing_or_unreadable_registry_keeps_a_clean_pushed_worktree_and_says_why(self):
        wt = self.worktree("w", pushed=True)
        for setup in (self.no_registry, self.unreadable_registry):
            with self.subTest(setup.__name__):
                if setup == self.unreadable_registry:
                    self.registry()
                setup()
                rc, out, err = self.sweep()
                self.assertEqual(rc, 0, err)
                self.assertTrue(os.path.isdir(wt), "the directory a session may stand in is still there")
                self.assertRegex(out, rf"(?m)^  \d+\s+{re.escape(wt)}  w  session registry unreadable$")
                self.assertNotIn("removed worktree", out)
                self.assertIn("w", self.git(self.wc, "branch", "--list", "w"))

    def test_an_unreadable_registry_still_deletes_a_branch_with_no_worktree(self):
        self.git(self.wc, "branch", "at-tip", "main")
        self.no_registry()
        rc, out, err = self.sweep()
        self.assertEqual(self.git(self.wc, "branch", "--list", "at-tip"), "", out)

    def test_an_unreadable_registry_names_its_reason_beside_the_worktrees_own(self):
        wt = self.worktree("owed", pushed=False)
        self.no_registry()
        rc, out, err = self.sweep()
        self.assertTrue(os.path.isdir(wt))
        self.assertIn("1 commit(s) on no remote", out)
        self.assertNotIn("session registry unreadable", out, "a worktree already kept says its own reason, not this one")

    def test_json_counts_a_worktree_kept_for_an_unreadable_registry_as_kept(self):
        wt = self.worktree("w", pushed=True)

        def kept_because() -> object:
            r = subprocess.run([CMD, "--json"], cwd=self.wc, env=self.env(), capture_output=True, text=True, timeout=300)
            self.assertEqual(r.returncode, 0, r.stderr)
            (entry,) = [w for w in json.loads(r.stdout)["worktrees"] if w["path"] == wt]
            return entry["kept_because"]
        self.assertIsNone(kept_because(), "a readable registry: the control agent counts it removable (the positive control)")
        self.no_registry()
        self.assertEqual(kept_because(), "session registry unreadable")

    def test_a_readable_registry_that_lists_no_one_in_the_worktree_removes_it(self):
        wt = self.worktree("w", pushed=True)
        rc, out, err = self.sweep()
        self.assertFalse(os.path.exists(wt), out)
        self.assertNotIn("session registry unreadable", out)

    def test_all_from_a_linked_worktree_keeps_that_worktree(self):
        here = self.worktree("here", pushed=True)
        rc, out, err = self.sweep("--all", cwd=here)
        self.assertTrue(os.path.isdir(here), out)

    def test_a_misspelled_second_argument_is_refused(self):
        self.git(self.wc, "branch", "at-tip", "main")
        rc, out, err = self.sweep("--worktree")
        self.assertEqual(rc, 2, out)
        self.assertIn("unknown argument '--worktree'", err)
        self.assertIn("at-tip", self.git(self.wc, "branch", "--list", "at-tip"), "nothing was deleted")

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
        self.registry()
        rc, out, err = self.sweep()
        self.assertFalse(os.path.exists(d), out)
        self.assertRegex(out, rf"removed session scratch {d} \(2\.0 KB\)")

    def test_a_live_session_stays(self):
        ended, live = self.sessions(ENDED, LIVE)
        self.registry((LIVE, self.harness(), self.t))
        rc, out, err = self.sweep()
        self.assertTrue(os.path.isdir(live) and not os.path.exists(ended), out)
        self.assertIn(f"kept session scratch {live} — live session", out)

    def test_a_registry_entry_of_a_dead_harness_is_no_session(self):
        (d,) = self.sessions(ENDED)
        gone = subprocess.Popen(["true"])
        gone.wait()
        self.registry((ENDED, gone.pid, self.t))
        rc, out, err = self.sweep()
        self.assertFalse(os.path.exists(d), out)

    def test_own_session_stays(self):
        (d,) = self.sessions(ENDED)
        self.registry()
        rc, out, err = self.sweep(CLAUDE_CODE_SESSION_ID=ENDED)
        self.assertTrue(os.path.isdir(d), out)

    def test_no_registry_or_one_that_cannot_be_read_keeps_all(self):
        (d,) = self.sessions(ENDED)
        self.no_registry()
        rc, out, err = self.sweep()                       # no sessions/ at all
        self.assertTrue(os.path.isdir(d), out)
        self.assertIn("cannot be listed", out)
        os.makedirs(os.path.join(self.cfg, "sessions"))
        self.unreadable_registry()
        rc, out, err = self.sweep()
        self.assertTrue(os.path.isdir(d), "a file the harness wrote that cannot be understood is unknown, never none")
        with open(os.path.join(self.cfg, "sessions", "1.json"), "w", encoding="utf-8") as fh:
            fh.write('{"pid": "x"}')
        rc, out, err = self.sweep()
        self.assertTrue(os.path.isdir(d), "...and so is one without a pid and a session id")

    def test_a_worktree_a_live_session_stands_in_is_in_use(self):
        wt = self.worktree("occupied", pushed=True)
        self.registry((LIVE, self.harness(), wt))
        rc, out, err = self.sweep()
        self.assertTrue(os.path.isdir(wt), out)
        self.assertIn("in use", out)

    def test_a_link_and_other_names_are_not_followed(self):
        self.registry()                                   # a registry that lists no live session: the scratch is judged
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

    def test_every_suite_that_runs_a_sweep_names_a_configuration_directory_of_its_own(self):
        """The sweep removes the ended sessions' scratch under $TMPDIR that the harness's registry (under CLAUDE_CONFIG_DIR, else
        HOME) does not list: a suite that runs it on the real ones removes this login's real scratch. Each names its own."""
        missing = []
        for name in sorted(os.listdir(os.path.join(ROOT, "tests"))):
            path = os.path.join(ROOT, "tests", name)
            if not name.endswith(".py") or name == os.path.basename(__file__):
                continue
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            if '"--sweep"' in text and "claude-config" not in text:
                missing.append(name)
        self.assertEqual(missing, [], "these run a sweep with this login's own registry and cache")

    def test_another_logins_cache_is_not_named(self):
        self.registry()                                   # a registry that lists no live session: the scratch is judged
        other = os.path.join(self.tmp, f"claude-{UID + 1}", "-proj", ENDED)
        os.makedirs(other)
        rc, out, err = self.sweep()
        self.assertTrue(os.path.isdir(other), out)


if __name__ == "__main__":
    unittest.main()
