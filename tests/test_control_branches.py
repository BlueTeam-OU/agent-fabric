#!/usr/bin/env python3
"""The control agent's `branches` (a read) and `branches-sweep` (a signed action): tools/fabric/control/branches_op.py,
its --json read in tools/fabric/branches.py, and fabric-ctl's side. Real git in scratch clones with a local origin,
a fake `gh` that fails at once, a fake /proc where a process must be seen, and a scratch state directory: the real
sweep runs, and what it must leave alone is looked for on disk. The sweep's own behaviour is
tests/test_fabric_branches_cli.py's."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402

own_instance_tree()
from control import agentd, ctl, ops  # noqa: E402
from control import branches_op as bo  # noqa: E402

GIT = shutil.which("git") or "/usr/bin/git"
NOW = 1_800_000_000.0


class Scratch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="control-branches-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.home = os.path.join(self.dir, "home")
        os.makedirs(os.path.join(self.home, "projects"))
        self.state = os.path.join(self.dir, "state")
        bindir = os.path.join(self.dir, "bin")
        os.makedirs(bindir)
        with open(os.path.join(bindir, "gh"), "w") as fh:
            fh.write("#!/bin/sh\nexit 1\n")       # a pull request lookup that fails at once: "?" in the report
        os.chmod(os.path.join(bindir, "gh"), 0o755)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "GIT_"))}
        env.update(PATH=bindir + os.pathsep + os.environ["PATH"], AGENT_FABRIC_STATE_DIR=self.state, GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_CONFIG_SYSTEM=os.devnull, GH_TOKEN="", GH_REPO="o/r", AGENT_FABRIC_ROOT=HERE, HOME=self.home)
        self.env = env
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def git(self, cwd: str, *args: str) -> str:
        return subprocess.run([GIT, "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@e.invalid", "-c", "commit.gpgsign=false", *args],
                              capture_output=True, text=True, check=True, env=self.env).stdout

    def clone(self, name: str, origin: bool = True) -> str:
        """~/projects/<name>: main, `merged` (on main) and `owed` (one commit off it); origin is a local bare repository."""
        wc = os.path.join(self.home, "projects", name)
        if origin:
            bare = os.path.join(self.dir, name + ".git")
            self.git(self.dir, "init", "-q", "--bare", "-b", "main", bare)
            self.git(self.dir, "clone", "-q", bare, wc)
        else:
            self.git(self.dir, "init", "-q", "-b", "main", wc)
        self.git(wc, "commit", "-q", "--allow-empty", "-m", "base")
        if origin:
            self.git(wc, "push", "-q", "origin", "HEAD:main")
            self.git(wc, "remote", "set-head", "origin", "main")
        self.git(wc, "branch", "merged")
        self.git(wc, "checkout", "-q", "-b", "owed")
        self.git(wc, "commit", "-q", "--allow-empty", "-m", "owed")
        self.git(wc, "checkout", "-q", "main")
        if origin:
            self.git(wc, "fetch", "-q", "origin")
        return wc

    def branches(self, wc: str) -> list[str]:
        return self.git(wc, "for-each-ref", "--format=%(refname:short)", "refs/heads/").split()

    def proc(self, *entries: tuple[str, list[str]]) -> str:
        """A /proc with one process per (cwd, argv)."""
        root = os.path.join(self.dir, "proc")
        shutil.rmtree(root, True)
        for i, (cwd, argv) in enumerate(entries, start=4242):
            os.makedirs(os.path.join(root, str(i)))
            os.symlink(cwd, os.path.join(root, str(i), "cwd"))
            with open(os.path.join(root, str(i), "cmdline"), "wb") as fh:
                fh.write(b"\0".join(a.encode() for a in argv) + b"\0")
        os.makedirs(root, exist_ok=True)
        return root

    def sweep(self, proc: str | None = None, request: dict | None = None) -> dict:
        return bo.branches_sweep(request or {"op": "branches-sweep"}, home=self.home, root=HERE, proc=proc or self.proc())

    def read(self) -> dict:
        return bo.branches(home=self.home, root=HERE, proc=self.proc(), now=NOW)

    def row(self, doc: dict, name: str) -> dict:
        return next(r for r in doc["working_copies"] if r["working_copy"] == name)


class WorkingCopies(Scratch):
    def test_only_a_real_directory_with_a_git_directory_one_level_down_is_one(self):
        alpha = self.clone("alpha")
        self.git(alpha, "worktree", "add", "-q", os.path.join(self.home, "projects", "alpha-linked"), "-b", "linked")
        os.makedirs(os.path.join(self.home, "projects", ".hidden", ".git"))
        os.makedirs(os.path.join(self.home, "projects", "plain"))
        os.symlink(alpha, os.path.join(self.home, "projects", "via-link"))
        self.assertEqual([n for n, _ in bo.working_copies(self.home)], ["alpha"])

    def test_no_projects_directory_is_no_working_copy_not_an_error(self):
        shutil.rmtree(os.path.join(self.home, "projects"))
        self.assertEqual(bo.working_copies(self.home), [])


class Read(Scratch):
    def test_counts_of_branches_merged_and_worktrees_and_no_sweep_yet(self):
        self.clone("alpha")
        r = self.row(self.read(), "alpha")
        self.assertEqual((r["status"], r["default"], r["branches"], r["merged"], r["worktrees"], r["dirty"], r["last_sweep"]),
                         ("ok", "main", 2, 1, 0, False, None))

    def test_a_clean_merged_linked_worktree_is_counted_and_removable_and_a_dirty_one_is_not(self):
        alpha = self.clone("alpha")
        merged = os.path.join(self.dir, "wt-merged")
        self.git(alpha, "worktree", "add", "-q", merged, "merged")
        r = self.row(self.read(), "alpha")
        self.assertEqual((r["worktrees"], r["removable_worktrees"]), (1, 1))
        with open(os.path.join(merged, "scratch.txt"), "w") as fh:
            fh.write("x")
        r = self.row(self.read(), "alpha")
        self.assertEqual((r["worktrees"], r["removable_worktrees"]), (1, 0), "an untracked file keeps it")

    def test_a_worktree_a_process_stands_in_is_not_counted_removable(self):
        alpha = self.clone("alpha")
        merged = os.path.join(self.dir, "wt-merged")
        self.git(alpha, "worktree", "add", "-q", merged, "merged")
        doc = bo.branches(home=self.home, root=HERE, proc=self.proc((os.path.realpath(merged), ["bash"])), now=NOW)
        self.assertEqual(self.row(doc, "alpha")["removable_worktrees"], 0)

    def test_the_read_fetches_nothing_and_changes_nothing(self):
        alpha = self.clone("alpha")
        other = os.path.join(self.dir, "other")
        self.git(self.dir, "clone", "-q", os.path.join(self.dir, "alpha.git"), other)
        self.git(other, "commit", "-q", "--allow-empty", "-m", "newer")
        self.git(other, "push", "-q", "origin", "HEAD:main")
        before = (self.git(alpha, "rev-parse", "origin/main"), self.branches(alpha))
        self.read()
        self.assertEqual((self.git(alpha, "rev-parse", "origin/main"), self.branches(alpha)), before)
        self.assertFalse(os.path.exists(os.path.join(self.state, "branch-sweep.json")) or
                         bool(list(os.scandir(self.state)) if os.path.isdir(self.state) else []), "no state written")

    def test_dirty_and_the_age_of_the_last_fetch(self):
        alpha = self.clone("alpha")
        with open(os.path.join(alpha, "new.txt"), "w") as fh:
            fh.write("x")
        os.utime(os.path.join(alpha, ".git", "FETCH_HEAD"), (NOW - 7200, NOW - 7200))
        r = self.row(self.read(), "alpha")
        self.assertEqual((r["dirty"], r["fetched_age_s"]), (True, 7200))

    def test_a_copy_git_cannot_read_is_a_failed_row_not_a_missing_one_or_zero(self):
        self.clone("alpha")
        self.clone("noremote", origin=False)
        doc = self.read()
        self.assertEqual([r["working_copy"] for r in doc["working_copies"]], ["alpha", "noremote"])
        r = self.row(doc, "noremote")
        self.assertEqual(r["status"], "failed")
        self.assertNotIn("merged", r)
        self.assertEqual(self.row(doc, "alpha")["status"], "ok")

    def test_the_read_is_the_collect_section_the_daemon_answers(self):
        self.clone("alpha")
        got = ops.collect("branches", {"home": self.home, "root": HERE})
        self.assertEqual(list(got), ["branches"])
        self.assertEqual(got["branches"]["working_copies"][0]["working_copy"], "alpha")

    def test_no_path_leaves_the_account(self):
        alpha = self.clone("alpha")
        self.git(alpha, "worktree", "add", "-q", os.path.join(self.dir, "wt-merged"), "merged")
        text = json.dumps(self.read())
        self.assertNotIn(self.dir, text)
        self.assertNotIn(self.home, text)


class Sweep(Scratch):
    def test_a_clean_copy_loses_what_is_on_main_keeps_what_is_not_and_records_itself(self):
        alpha = self.clone("alpha")
        row = self.row(self.sweep(), "alpha")
        self.assertEqual((row["status"], row["deleted"], row["kept"]), ("swept", ["merged"], ["owed"]))
        self.assertEqual(sorted(self.branches(alpha)), ["main", "owed"])
        self.assertTrue(self.row(self.read(), "alpha")["last_sweep"], "recorded as fabric-branches records")

    def test_a_branch_with_a_commit_off_main_is_never_deleted_even_when_a_pull_request_merged(self):
        alpha = self.clone("alpha")
        self.sweep()
        self.sweep()
        self.assertIn("owed", self.branches(alpha))

    def test_a_dirty_copy_is_skipped_untouched(self):
        alpha = self.clone("alpha")
        with open(os.path.join(alpha, "wip.txt"), "w") as fh:
            fh.write("x")
        row = self.row(self.sweep(), "alpha")
        self.assertEqual((row["status"], row["why"]), ("skipped", "uncommitted changes"))
        self.assertIn("merged", self.branches(alpha))
        self.assertFalse(os.path.exists(os.path.join(self.state, "branch-sweep.json")))

    def test_a_copy_with_a_build_or_suite_running_in_it_is_skipped_untouched(self):
        alpha = self.clone("alpha")
        row = self.row(self.sweep(self.proc((os.path.realpath(alpha), ["cargo", "build"]))), "alpha")
        self.assertEqual((row["status"], row["why"]), ("skipped", "busy: cargo"))
        self.assertIn("merged", self.branches(alpha))

    def test_a_suite_in_a_linked_worktree_of_the_copy_makes_it_busy_too(self):
        alpha = self.clone("alpha")
        linked = os.path.join(self.dir, "wt-owed")
        self.git(alpha, "worktree", "add", "-q", linked, "owed")
        proc = self.proc((os.path.realpath(linked) + "/sub", ["python3", "tests/test_x.py"]))
        os.makedirs(os.path.join(linked, "sub"))
        row = self.row(self.sweep(proc), "alpha")
        self.assertEqual(row["status"], "skipped")
        self.assertIn("merged", self.branches(alpha))

    def test_an_agents_shell_or_harness_in_the_copy_is_not_a_reason_to_skip(self):
        alpha = self.clone("alpha")
        proc = self.proc((os.path.realpath(alpha), ["bash"]), (os.path.realpath(alpha), ["claude", "--resume"]),
                         (os.path.dirname(os.path.realpath(alpha)), ["cargo", "build"]))
        self.assertEqual(self.row(self.sweep(proc), "alpha")["status"], "swept")
        self.assertNotIn("merged", self.branches(alpha))

    def test_a_process_table_that_cannot_be_read_skips_every_copy(self):
        alpha = self.clone("alpha")
        row = self.row(self.sweep(proc=os.path.join(self.dir, "no-proc")), "alpha")
        self.assertEqual(row["status"], "skipped")
        self.assertIn("unknown", row["why"])
        self.assertIn("merged", self.branches(alpha))

    def test_a_merged_worktree_a_shell_stands_in_is_kept_and_without_the_shell_it_goes(self):
        alpha = self.clone("alpha")
        wt = os.path.join(self.dir, "wt-merged")
        self.git(alpha, "worktree", "add", "-q", wt, "merged")
        self.git(wt, "checkout", "-q", "--detach")        # a branch checked out in a worktree is kept for that reason alone
        row = self.row(self.sweep(self.proc((os.path.realpath(wt), ["bash"]))), "alpha")
        self.assertTrue(os.path.isdir(wt), "the directory a session stands in is still there")
        self.assertEqual((row["worktrees_kept"], row["worktrees_removed"]), (["wt-merged"], []))
        row = self.row(self.sweep(), "alpha")
        self.assertFalse(os.path.exists(wt))
        self.assertEqual((row["worktrees_kept"], row["worktrees_removed"]), ([], ["wt-merged"]))

    def test_a_copy_the_tool_refuses_is_a_row_that_says_so_and_does_not_fail_the_sweep(self):
        self.clone("alpha")
        self.clone("noremote", origin=False)
        doc = self.sweep()
        self.assertEqual(doc["status"], "swept")
        r = self.row(doc, "noremote")
        self.assertEqual(r["status"], "refused", "no origin: the tool's own refusal, said, and nothing deleted")
        self.assertEqual(self.row(doc, "alpha")["status"], "swept")

    def test_arguments_are_refused_and_nothing_is_swept(self):
        alpha = self.clone("alpha")
        for bad in ({"op": "branches-sweep", "args": {"x": 1}}, {"op": "branches-sweep", "args": None}, {"op": "branches-sweep", "args": []}):
            self.assertEqual(self.sweep(request=bad)["status"], "refused", bad)
        self.assertIn("merged", self.branches(alpha))

    def test_a_timeout_is_a_failed_row_and_the_sweep_goes_on(self):
        self.clone("alpha")
        calls = []

        def run(cmd, **kw):
            calls.append(cmd[-1])
            if cmd[-1] == "--sweep":
                raise subprocess.TimeoutExpired(cmd, 1)
            return subprocess.run(cmd, **kw)
        doc = bo.branches_sweep({"op": "branches-sweep"}, home=self.home, root=HERE, run=run, proc=self.proc())
        self.assertEqual((doc["status"], doc["working_copies"][0]["status"]), ("failed", "failed"))
        self.assertEqual(calls, ["--json", "--sweep"])


    def test_worktrees_that_cannot_be_listed_after_a_sweep_are_unknown_not_none(self):
        alpha = self.clone("alpha")
        self.git(alpha, "worktree", "add", "-q", os.path.join(self.dir, "wt"), "owed")
        seen = []

        def run(cmd, **kw):
            seen.append(cmd[-1])
            if cmd[-1] == "--json" and seen.count("--json") > 1:
                raise subprocess.TimeoutExpired(cmd, 1)       # the read after the sweep
            return subprocess.run(cmd, **kw)
        row = bo.branches_sweep({"op": "branches-sweep"}, home=self.home, root=HERE, run=run, proc=self.proc())["working_copies"][0]
        self.assertEqual((row["status"], row["worktrees_kept"]), ("swept", None))
        text = ctl.table("branches-sweep", ctl.rows([{"login": "a", "host": "h", "address": "h/a"}],
                                                    [{"kind": "reply", "from": "h/a", "op": "branches-sweep", "latency_ms": 1,
                                                      "data": {"branches-sweep": {"status": "swept", "working_copies": [row]}}}]))
        self.assertIn("kept ?", text)


class JsonRead(Scratch):
    def test_a_count_git_cannot_give_is_null_never_zero(self):
        import io
        import contextlib
        import branches as br
        alpha = self.clone("alpha")
        self.git(alpha, "worktree", "add", "-q", os.path.join(self.dir, "wt"), "owed")
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        os.chdir(alpha)
        buf = io.StringIO()
        with mock.patch.object(br, "ahead", lambda *a, **k: "?"), contextlib.redirect_stdout(buf):
            self.assertEqual(br.run(["--json"]), 0)
        d = json.loads(buf.getvalue())
        self.assertEqual([b["ahead"] for b in d["branches"]], [None, None])
        self.assertEqual([w["ahead"] for w in d["worktrees"]], [None])


class Runners(unittest.TestCase):
    def test_builds_and_suites_by_name(self):
        for argv, want in ((["cargo", "build"], "cargo"), (["/usr/bin/pytest", "-q"], "pytest"), (["bash", "tests/run.sh"], "run.sh"),
                           (["python3", "tests/test_x.py"], "test_x.py"), (["python3", "-u", "/a/tests/test_y.py"], "test_y.py"),
                           (["flutter", "test"], "flutter"), (["npm", "test"], "npm"), (["make"], "make")):
            self.assertEqual(bo.runner_of(argv), want, argv)

    def test_shells_harnesses_editors_and_a_script_that_is_not_a_test_are_not(self):
        for argv in (["bash"], ["-bash"], ["claude", "--resume"], ["python3", "tools/fabric/fleet.py"], ["vim", "tests/notes.txt"], ["git", "status"],
                     ["sleep", "30"], [], ["python3"], ["fabric-python", "-I", "/x/gzcoord-inbox", "--until-delivery"]):
            self.assertIsNone(bo.runner_of(argv), argv)

    def test_a_process_is_inside_a_copy_by_path_not_by_prefix(self):
        self.assertTrue(bo._inside("/h/p/alpha/sub", "/h/p/alpha"))
        self.assertTrue(bo._inside("/h/p/alpha", "/h/p/alpha"))
        self.assertFalse(bo._inside("/h/p/alpha-linked", "/h/p/alpha"))


class Ctl(unittest.TestCase):
    def test_sweep_makes_the_signed_action_and_branches_alone_the_read(self):
        self.assertEqual(ctl.parse_args(["all", "branches"])["op"], "branches")
        a = ctl.parse_args(["all", "branches", "--sweep"])
        self.assertEqual((a["op"], a["timeout"]), ("branches-sweep", bo.BRANCHES_SWEEP_BUDGET_S))
        self.assertIn("branches-sweep", ctl.ACTION_OPS)
        self.assertNotIn("branches", ctl.ACTION_OPS)
        self.assertEqual(ctl.parse_args(["all", "branches"])["timeout"], 60)

    def test_sweep_with_another_op_is_refused(self):
        for argv in (["all", "jobs", "--sweep"], ["all", "--sweep"], ["all", "local", "--sweep"]):
            with self.assertRaises(ctl.CtlError):
                ctl.parse_args(argv)

    def test_the_ops_are_in_the_closed_set_and_only_the_sweep_is_an_action(self):
        self.assertIn("branches", ops.OPS)
        self.assertIn("branches-sweep", ops.OPS)
        self.assertNotIn("branches", ops.PUBLIC_OPS)
        self.assertNotIn("branches-sweep", ops.PUBLIC_OPS)

    def rows(self, op: str, data: dict) -> list:
        return ctl.rows([{"login": "a", "host": "h", "address": "h/a"}],
                        [{"kind": "reply", "from": "h/a", "op": op, "latency_ms": 3, "data": {op: data}}])

    def test_the_read_table_has_a_line_per_copy_and_the_numbers(self):
        w = {"working_copy": "alpha", "status": "ok", "default": "main", "dirty": True, "last_sweep": "2026-09-29T08:00:00Z",
             "fetched_age_s": 7300, "branches": 9, "merged": 4, "worktrees": 3, "removable_worktrees": 2, "unknown": 1}
        text = ctl.table("branches", self.rows("branches", {"status": "ok", "working_copies": [w, {"working_copy": "b", "status": "failed", "why": "no origin"}]}))
        first, second = text.splitlines()[1:3]
        for want in ("alpha", "2026-09-29T08:00:00Z", "9", "4", "3", "2", "2h", "yes", "1 not counted"):
            self.assertIn(want, first)
        self.assertIn("failed", second)
        self.assertIn("no origin", second)

    def test_the_sweep_table_names_what_was_deleted_kept_and_skipped(self):
        doc = {"status": "swept", "working_copies": [
            {"working_copy": "alpha", "status": "swept", "deleted": ["x", "y"], "kept": ["owed"], "worktrees_removed": ["wt"], "worktrees_kept": [],
             "deleted_total": 2, "kept_total": 1},
            {"working_copy": "beta", "status": "skipped", "why": "busy: cargo"}]}
        lines = ctl.table("branches-sweep", self.rows("branches-sweep", doc)).splitlines()
        self.assertIn("deleted x y; kept owed", lines[1])
        self.assertIn("busy: cargo", lines[2])

    def test_what_an_account_sends_is_escaped_in_the_table(self):
        hostile = "evil\x1b]0;pwned\x07name"
        doc = {"status": "swept", "working_copies": [{"working_copy": hostile, "status": "swept", "deleted": [hostile], "kept": [], "worktrees_removed": [],
                                                       "worktrees_kept": [], "deleted_total": 1, "kept_total": 0}]}
        text = ctl.table("branches-sweep", self.rows("branches-sweep", doc))
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\x07", text)

    def test_a_sweep_that_failed_fails_the_run_and_one_that_skipped_does_not(self):
        self.assertEqual(ctl.ACTION_OK["branches-sweep"], ["swept"])


class Daemon(Scratch):
    def test_the_daemon_answers_the_sweep_with_its_own_home_and_the_read_through_collect(self):
        self.clone("alpha")
        ctx = {"me": {"address": "h/a"}, "started": "2026-10-10T00:00:00.000Z", "home": self.home, "root": HERE}
        reply = agentd.answer({"op": "branches-sweep", "id": "r1"}, ctx)
        self.assertEqual(reply["data"]["branches-sweep"]["working_copies"][0]["deleted"], ["merged"])
        reply = agentd.answer({"op": "branches", "id": "r2"}, ctx)
        self.assertEqual(reply["data"]["branches"]["working_copies"][0]["merged"], 0, "swept: nothing left to count")


if __name__ == "__main__":
    unittest.main()
