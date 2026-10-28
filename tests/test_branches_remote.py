#!/usr/bin/env python3
"""fabric-branches on origin (j92, the owner 2026-10-28): --sweep also deletes this login's own branches of origin that are on the
default branch and head no open pull request; the plain report lists them as "on origin, on main, would delete".
Run as the command (bin/fabric-branches, override with FABRIC_BRANCHES) in sandboxes of their own, against a bare origin and a fake gh.
The oracles tests/test_branches_sweep.py, tests/test_branches.py and tests/test_fabric_branches_cli.py run unchanged beside it.

Mutations planted on the source as formatted, each caught by the case named:
  tools/fabric/branches.py   prefix filter dropped / widened to the login without the host (another_logins_branch); ancestry not asked
                             (a_commit_off_main_stays, a_branch_pushed_since_the_fetch_stays); the open-PR check dropped, or its answer
                             read as none on a failure (an_open_pull_request_stays, gh_unavailable_skips_the_step); `--worktrees` also
                             deleting on origin (worktrees_only_deletes_nothing_on_origin); the plain report deleting (the_report_is_the_dry_run);
                             the lease dropped (a_branch_pushed_during_the_run_stays); a refused delete stopping the rest or exiting 0
                             (a_refused_delete_is_named_and_the_rest_go_on); the default branch never filtered (the_default_branch_stays); ls-remote replaced by the fetched refs (a_branch_the_host_deleted_is_not_offered).

The environment is built from scratch: PATH (a fake gh first, so no case reaches GitHub), HOME, LANG, TMPDIR, the state directory."""
from __future__ import annotations

import os
import pwd
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
CMD = os.environ.get("FABRIC_BRANCHES") or os.path.join(ROOT, "bin", "fabric-branches")
GIT = ("git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false")
HOST = socket.gethostname().split(".")[0]
LOGIN = pwd.getpwuid(os.geteuid()).pw_name
MINE = f"{HOST}/{LOGIN}/"
# Answers `gh pr list --head <b> --state open --json number`: a row for each branch named in $GH_OPEN_FILE, an error when $GH_FAIL is set.
FAKE_GH = """#!/bin/sh
[ -n "$GH_FAIL" ] && { echo "gh: To get started with GitHub CLI, please run:  gh auth login" >&2; exit 4; }
while [ $# -gt 0 ]; do [ "$1" = --head ] && head="$2"; shift; done
# $GH_RACE_REPO: someone pushes to the branch while its pull requests are being read, after ls-remote gave its tip.
[ -n "$GH_RACE_REPO" ] && git -C "$GH_RACE_REPO" push -q -f origin "later:refs/heads/$head"
if [ -n "$GH_OPEN_FILE" ] && grep -qxF "$head" "$GH_OPEN_FILE" 2>/dev/null; then echo '[{"number":7}]'; else echo '[]'; fi
"""


class Remote(unittest.TestCase):
    def setUp(self):
        self.t = os.path.realpath(tempfile.mkdtemp(prefix="remote-"))
        self.addCleanup(shutil.rmtree, self.t, True)
        self.bin = os.path.join(self.t, "bin")
        os.makedirs(self.bin)
        self.write_gh(FAKE_GH)
        self.open_file = os.path.join(self.t, "open")
        self.cfg = os.path.join(self.t, "claude-config")
        os.makedirs(os.path.join(self.cfg, "sessions"))
        self.tmp = os.path.join(self.t, "tmp")
        os.makedirs(self.tmp)
        self.origin = os.path.join(self.t, "origin.git")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", self.origin], env=self.env(), check=True, timeout=30)
        self.wc = os.path.join(self.t, "wc")
        subprocess.run(["git", "clone", "-q", self.origin, self.wc], env=self.env(), check=True, timeout=30, stderr=subprocess.DEVNULL)
        self.git("commit", "-q", "--allow-empty", "-m", "base")
        self.git("push", "-q", "origin", "HEAD:main")
        self.git("remote", "set-head", "origin", "main")

    def write_gh(self, text):
        path = os.path.join(self.bin, "gh")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(path, 0o755)

    def env(self, **extra) -> dict:
        env = {"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": self.t, "LANG": "C.UTF-8", "TMPDIR": self.tmp,
               "AGENT_FABRIC_STATE_DIR": os.path.join(self.t, "state"), "GH_REPO": "o/r", "GIT_CONFIG_GLOBAL": os.devnull,
               "PYTHONDONTWRITEBYTECODE": "1", "CLAUDE_CONFIG_DIR": self.cfg, "CLAUDE_CODE_TMPDIR": self.tmp, "GH_OPEN_FILE": self.open_file if hasattr(self, "open_file") else ""}
        env.update(extra)
        return env

    def git(self, *args, cwd=None) -> str:
        r = subprocess.run([*GIT, "-C", cwd or self.wc, *args], env=self.env(), capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, f"git {args}: {r.stderr}")
        return r.stdout

    def push(self, name, *, merged: bool) -> str:
        """origin gains branch `name`: at main's tip (merged), or one commit past it."""
        self.git("checkout", "-q", "-B", "scratch", "origin/main")
        if not merged:
            self.git("commit", "-q", "--allow-empty", "-m", name)
        self.git("push", "-q", "origin", f"scratch:refs/heads/{name}")
        self.git("checkout", "-q", "--detach")
        self.git("branch", "-q", "-D", "scratch")
        return self.git("rev-parse", "HEAD").strip()

    def on_origin(self) -> set[str]:
        out = subprocess.run(["git", "-C", self.origin, "for-each-ref", "--format=%(refname:short)", "refs/heads/"],
                             capture_output=True, text=True, timeout=30, env=self.env()).stdout
        return set(out.split())

    def run_cmd(self, *args, **extra):
        r = subprocess.run([CMD, *args], cwd=self.wc, env=self.env(**extra), capture_output=True, text=True, timeout=300)
        return r.returncode, r.stdout, r.stderr

    def test_own_merged_branch_is_listed_then_deleted(self):
        self.push(f"{MINE}for/x/done", merged=True)
        rc, out, err = self.run_cmd()
        self.assertEqual(rc, 0, err)
        self.assertIn("on origin, on main, would delete:", out)
        self.assertIn(f"  {MINE}for/x/done", out.splitlines())
        self.assertIn(f"{MINE}for/x/done", self.on_origin(), "the report is the dry run")   # the_report_is_the_dry_run
        rc, out, err = self.run_cmd("--sweep")
        self.assertEqual(rc, 0, err)
        self.assertTrue(any(l.startswith(f"  deleted origin/{MINE}for/x/done (") for l in out.splitlines()), out)
        self.assertNotIn(f"{MINE}for/x/done", self.on_origin())
        self.assertIn("main", self.on_origin())

    def test_another_logins_branch_stays(self):
        self.push(f"{HOST}/someone-else/feat/x", merged=True)
        self.push(f"{HOST}/{LOGIN}2/feat/x", merged=True)      # a login that only starts with this one's name
        self.push(f"{LOGIN}/feat/x", merged=True)               # this login without the host
        rc, out, err = self.run_cmd("--sweep")
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.on_origin() - {"main"},
                         {f"{HOST}/someone-else/feat/x", f"{HOST}/{LOGIN}2/feat/x", f"{LOGIN}/feat/x"}, out)
        self.assertNotIn("on origin, on main", out)

    def test_an_open_pull_request_stays(self):
        self.push(f"{MINE}feat/open", merged=True)
        self.push(f"{MINE}feat/closed", merged=True)
        with open(self.open_file, "w", encoding="utf-8") as fh:
            fh.write(f"{MINE}feat/open\n")
        rc, out, err = self.run_cmd("--sweep")
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.on_origin() - {"main"}, {f"{MINE}feat/open"}, out)
        self.assertIn(f"KEPT origin/{MINE}feat/open — heads an open pull request", out)

    def test_a_commit_off_main_stays(self):
        self.push(f"{MINE}feat/work", merged=False)
        rc, out, err = self.run_cmd("--sweep")
        self.assertEqual(rc, 0, err)
        self.assertIn(f"{MINE}feat/work", self.on_origin())
        self.assertNotIn("on origin, on main", out)

    def test_a_branch_pushed_since_the_fetch_stays(self):
        # Pushed after the fetch: the fetched ref is stale (merged), origin's tip is not.
        self.push(f"{MINE}feat/moved", merged=True)
        self.git("fetch", "-q", "origin")
        self.git("checkout", "-q", "-B", "scratch", "origin/main")
        self.git("commit", "-q", "--allow-empty", "-m", "later")
        self.git("push", "-q", "origin", f"scratch:refs/heads/{MINE}feat/moved")
        rc, out, err = self.run_cmd("--sweep")
        self.assertEqual(rc, 0, err)
        self.assertIn(f"{MINE}feat/moved", self.on_origin())

    def test_a_branch_the_host_deleted_is_not_offered(self):
        # A fetch without --prune keeps the ref of a branch deleted on origin; ls-remote, not that ref, says what is there.
        self.push(f"{MINE}for/x/gone", merged=True)
        self.git("fetch", "-q", "origin")
        subprocess.run(["git", "-C", self.origin, "branch", "-q", "-D", f"{MINE}for/x/gone"], check=True, timeout=30, env=self.env())
        rc, out, err = self.run_cmd("--sweep")
        self.assertEqual(rc, 0, (out, err))
        self.assertNotIn("for/x/gone", out)

    def test_a_branch_pushed_during_the_run_stays(self):
        self.push(f"{MINE}feat/racing", merged=True)
        self.git("checkout", "-q", "-B", "later", "origin/main")
        self.git("commit", "-q", "--allow-empty", "-m", "later")
        self.git("checkout", "-q", "--detach")
        rc, out, err = self.run_cmd("--sweep", GH_RACE_REPO=self.wc)
        self.assertEqual(rc, 1, (out, err))
        self.assertIn(f"{MINE}feat/racing", self.on_origin())
        self.assertIn(f"KEPT origin/{MINE}feat/racing — the delete was refused", out)

    def test_the_default_branch_stays(self):
        # A default branch under this login's prefix, as a project whose default is named so: never offered.
        self.git("push", "-q", "origin", f"origin/main:refs/heads/{MINE}main")
        self.git("remote", "set-head", "origin", f"{MINE}main")
        self.git("fetch", "-q", "origin")
        rc, out, err = self.run_cmd("--sweep")
        self.assertIn(f"{MINE}main", self.on_origin(), (out, err))

    def test_gh_unavailable_skips_the_step(self):
        self.push(f"{MINE}for/x/done", merged=True)
        rc, out, err = self.run_cmd("--sweep", GH_FAIL="1")
        self.assertEqual(rc, 0, err)
        self.assertIn("skipped: pull requests cannot be read", out)
        self.assertIn(f"{MINE}for/x/done", self.on_origin())
        self.assertIn("session scratch:", out, "the rest of the sweep goes on")

    def test_gh_missing_skips_the_step(self):
        self.push(f"{MINE}for/x/done", merged=True)
        bare = os.path.join(self.t, "nogh")
        os.makedirs(bare)
        for tool in ("git", "python3", "env", "sh", "bash", "hostname"):
            found = shutil.which(tool, path="/usr/bin:/bin")
            if found:
                os.symlink(found, os.path.join(bare, tool))
        rc, out, err = self.run_cmd("--sweep", PATH=bare)
        self.assertEqual(rc, 0, err)
        self.assertIn("skipped: pull requests cannot be read (gh pr list: gh is not installed)", out)
        self.assertIn(f"{MINE}for/x/done", self.on_origin())

    def test_worktrees_only_deletes_nothing_on_origin(self):
        self.push(f"{MINE}for/x/done", merged=True)
        rc, out, err = self.run_cmd("--sweep", "--worktrees")
        self.assertEqual(rc, 0, err)
        self.assertIn(f"{MINE}for/x/done", self.on_origin())

    def test_a_refused_delete_is_named_and_the_rest_go_on(self):
        for n in ("a", "b", "c"):
            self.push(f"{MINE}for/x/{n}", merged=True)
        hook = os.path.join(self.origin, "hooks", "pre-receive")
        with open(hook, "w", encoding="utf-8") as fh:
            fh.write(f"#!/bin/sh\nwhile read old new ref; do [ \"$ref\" = refs/heads/{MINE}for/x/b ] && exit 1; done\nexit 0\n")
        os.chmod(hook, 0o755)
        rc, out, err = self.run_cmd("--sweep")
        self.assertEqual(rc, 1, (out, err))
        self.assertEqual(self.on_origin() - {"main"}, {f"{MINE}for/x/b"})
        self.assertIn(f"KEPT origin/{MINE}for/x/b — the delete was refused", out)
        self.assertIn(f"origin/{MINE}for/x/b not deleted", err)


if __name__ == "__main__":
    unittest.main()
