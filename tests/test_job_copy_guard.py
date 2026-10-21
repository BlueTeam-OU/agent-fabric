#!/usr/bin/env python3
"""runtime/claude-code/hooks/job-copy-guard.sh (Claude Code PreToolUse hook on Bash): a main session commits and
publishes only in its job's working copy (agent-fabric ADR-037 rule 3; j323).

Driven the way the harness drives it: the forwarder run as a program, the payload on stdin, an environment built
from nothing (tests/hook_harness.py). The job list is a file this test writes under its own XDG_STATE_HOME, in the
shape tools/fabric/jobs.py keeps; the checkouts are real repositories under a scratch directory, removed after.

Contract held: a subagent, a command that neither commits nor publishes, an unbound session and a commit inside the
active job's working copy or worktree (a clone's .claude/worktrees/ included) pass silently; a commit or publish that
acts in a directory outside them (the cwd, a `cd`, a `git -C`) is denied; a session that has worked a job which left
active is denied every commit, the session that switched included; a list that cannot be read asks, but only for a
command that commits or publishes. Git pointed elsewhere through GIT_DIR/GIT_WORK_TREE/GIT_COMMON_DIR (a prefix,
`env`, `export`) or --git-dir/--work-tree is judged like a cd; a repository named by `gh pr … -R`, `fabric-pr --repo`
or GH_REPO is inside only when it is a remote of the job copy, and a copy whose remotes cannot be read asks; only an
unquoted `<<` opens a heredoc; the git lookups stop at a budget and ask (review round 1 of #348). A heredoc body is
read as commands only when its pipeline executes it, and an unquoted one's substitutions always; a quoted body that
is only read or published (cat, a commit message, fabric-pr post-review, gh pr create --body-file -) never asks; a
pull request URL names its repository; `-c core.worktree`, `--config-env` and the GIT_CONFIG_* variables count as a
work tree (review round 2 of #348). A runner word anywhere in the command reads every body, whatever pipeline
holds it; `|&` is a pipe; a PR URL names its repository whatever its query or fragment; `-c include.path`,
`-c includeIf.<cond>.path` and HOME, XDG_CONFIG_HOME, GIT_CONFIG_NOSYSTEM, GIT_CEILING_DIRECTORIES count as a work
tree the guard cannot resolve (review round 3 of #348).

Mutations each case set fails on: the agent_id test removed; `cd` or `-C` targets not collected; the prefix test made
a plain string prefix (proj-other would pass as proj); "worked the active job" counted as allowed (the switching
session); the `last` fallback used without a session id; the list read before the command is parsed; the ask on an
unreadable list replaced by an allow; assignment words not read; the repository judgement skipped; the heredoc scan
made blind to quotes or to comments; every quoted body read as commands; source or `.` not counted as running stdin;
the executed test scoped to the line instead of the pipeline; substitutions or pipelines around a redirect not
followed; an unquoted body's substitutions left unread, or its plain text read; a `$(` inside double quotes not
reopening command text; PR URLs not read; core.worktree or the GIT_CONFIG_* variables not read; the budget never
raised; the whole-command runner fallback removed; `|&` read as the end of a pipeline; any new runner word dropped;
PR URLs read with a fullmatch again (query, fragment); include.path, includeIf or the HOME-like variables not read.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

import hook_harness  # noqa: E402
from git_env import git_env, scrub_process_env  # noqa: E402
scrub_process_env()

ENTRY = hook_harness.entry("JOB_COPY_GUARD_HOOK", "job-copy-guard.sh")
SESSION = "sess-now"
OLD = "sess-old"


def git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, env=git_env(), capture_output=True)


class Guard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = os.path.realpath(tempfile.mkdtemp(prefix="jcg-test-"))
        projects = os.path.join(cls.tmp, "projects")
        cls.proj = os.path.join(projects, "proj")
        cls.other = os.path.join(projects, "other")
        cls.lookalike = os.path.join(projects, "proj-other")    # a sibling whose name starts with the job copy's
        for repo in (cls.proj, cls.other, cls.lookalike):
            os.makedirs(repo)
            git("-C", repo, "init", "-q", "-b", "main")
            git("-C", repo, "commit", "-q", "--allow-empty", "-m", "seed")
        cls.worktree = os.path.join(projects, "proj-j7")          # the job's worktree, beside its working copy
        git("-C", cls.proj, "worktree", "add", "-q", "-b", "j7", cls.worktree)
        cls.agent_tree = os.path.join(cls.proj, ".claude", "worktrees", "agent-x")   # a subagent's, under the clone
        git("-C", cls.proj, "worktree", "add", "-q", "-b", "agent-x", cls.agent_tree)
        os.makedirs(os.path.join(cls.agent_tree, "sub"))
        # The job copy's remotes, in two of the URL shapes the guard normalises; the worktree shares them.
        git("-C", cls.proj, "remote", "add", "origin", "git@github.com:Acme/Proj.git")
        git("-C", cls.proj, "remote", "add", "mirror", "https://github.com/acme/proj-mirror")
        cls.plain = os.path.join(projects, "plain")               # a working copy that is no repository: no remotes to read
        os.makedirs(cls.plain)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="home-", dir=self.tmp)
        self.addCleanup(shutil.rmtree, self.home, True)
        self.jobs_file = os.path.join(self.home, ".state", "agent-fabric", "agents", self.login(), "jobs.json")

    @staticmethod
    def login() -> str:
        import pwd
        return pwd.getpwuid(os.geteuid()).pw_name

    # ---- the world -------------------------------------------------------------------------------------------------

    def job(self, jid: str, state: str, sessions=(), **extra) -> dict:
        log = [{"at": "2026-10-20T10:00:00Z", "state": "queued"}]
        log += [{"at": "2026-10-20T11:00:00Z", "state": "active", "session": s} for s in sessions]
        return {"id": jid, "title": f"job {jid}", "topic": None, "project": "proj", "working_copy": self.proj,
                "state": state, "source": {"kind": "self"}, "artifacts": [], "created": "2026-10-20T10:00:00Z",
                "updated": "2026-10-20T11:00:00Z", "log": log, **extra}

    def write_jobs(self, *jobs: dict, last: str | None = None) -> None:
        os.makedirs(os.path.dirname(self.jobs_file), exist_ok=True)
        doc = {"seq": len(jobs), "jobs": list(jobs), **({"last": last} if last else {})}
        with open(self.jobs_file, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

    def active_j7(self, sessions=(OLD,)) -> None:
        """j7 active in proj with its worktree; activated by another session (fabric-fresh --job j7 launched this one)."""
        self.write_jobs(self.job("j6", "done", sessions=(OLD,)),
                        self.job("j7", "active", sessions=sessions, branch="j7", worktree=self.worktree))

    # ---- the hook --------------------------------------------------------------------------------------------------

    def run_hook(self, command: str, cwd: str, *, session: str | None = SESSION, agent_id: str | None = None,
                 payload_session: str | None = None) -> hook_harness.Result:
        payload = {"tool_name": "Bash", "cwd": cwd, "tool_input": {"command": command}, "hook_event_name": "PreToolUse"}
        if agent_id:
            payload.update(agent_id=agent_id, agent_type="code-medium")
        if payload_session:
            payload["session_id"] = payload_session
        extra = {"AGENT_FABRIC_ROOT": hook_harness.ROOT}
        if session:
            extra["CLAUDE_CODE_SESSION_ID"] = session
        r = hook_harness.run(ENTRY, json.dumps(payload), hook_harness.env(self.home, **extra), cwd=cwd)
        self.assertEqual(r.rc, 0, f"exit 0 always: {r.err!r}")
        return r

    def decision(self, command: str, cwd: str, **kw) -> str:
        r = self.run_hook(command, cwd, **kw)
        if r.out == "":
            return "allow"
        self.assertEqual(len(r.out.splitlines()), 1, r.out)
        out = json.loads(r.out)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PreToolUse")
        return out["permissionDecision"]

    def reason(self, command: str, cwd: str, **kw) -> str:
        return json.loads(self.run_hook(command, cwd, **kw).out)["hookSpecificOutput"]["permissionDecisionReason"]

    # ---- the cases -------------------------------------------------------------------------------------------------

    def test_a_subagent_is_left_to_the_clone_guard(self):
        self.active_j7()
        self.assertEqual(self.decision(f"cd {self.other} && git commit -m x", self.proj, agent_id="a1"), "allow")

    def test_reading_another_working_copy_is_allowed(self):
        self.active_j7()
        for cmd in (f"cd {self.other} && git log --oneline -3", f"git -C {self.other} status", f"git -C {self.other} fetch",
                    f"cat {self.other}/README", f"grep -rn 'git commit' {self.other}", "fabric-pr gate", f"cd {self.other}; git diff"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, self.proj), "allow")

    def test_a_command_that_does_not_commit_never_reads_the_list(self):
        os.makedirs(os.path.dirname(self.jobs_file), exist_ok=True)
        with open(self.jobs_file, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertEqual(self.decision(f"cd {self.other} && git status", self.proj), "allow")

    def test_a_commit_in_the_job_s_copies_is_allowed(self):
        self.active_j7()
        self.assertEqual(self.decision("git commit -m x", self.worktree), "allow", "the job's worktree")
        self.assertEqual(self.decision("git push -u origin j7", self.worktree), "allow")
        self.assertEqual(self.decision("git commit -m x", self.proj), "allow", "the job's working copy")
        self.assertEqual(self.decision(f"git -C {self.worktree} commit -m x", self.proj), "allow")
        self.assertEqual(self.decision("cd sub && git commit -m x", self.agent_tree), "allow", "a relative cd inside")
        self.assertEqual(self.decision("gh pr create --fill", self.worktree), "allow")

    def test_a_commit_under_the_clone_s_worktrees_is_allowed(self):
        self.active_j7()
        self.assertEqual(self.decision("git commit -m x", os.path.join(self.agent_tree, "sub")), "allow")

    def test_a_cd_to_another_copy_then_a_commit_is_denied(self):
        self.active_j7()
        self.assertEqual(self.decision(f"cd {self.other} && git commit -m x", self.worktree), "deny")
        self.assertEqual(self.decision(f"pushd {self.other}; git commit -m x", self.worktree), "deny")
        self.assertEqual(self.decision("cd ../other && git commit -m x", self.proj), "deny", "relative to the cwd")
        self.assertEqual(self.decision(f"cd {self.lookalike} && git commit -m x", self.proj), "deny", "a name prefix is not a path prefix")
        self.assertEqual(self.decision("git commit -m x", self.other), "deny", "the cwd itself")
        r = self.reason(f"cd {self.other} && git commit -m x", self.worktree)
        for fact in ("j7", self.proj, self.worktree, self.other, "git commit", "ADR-037 rule 3", "fabric-jobs switch",
                     "Reading other working copies is allowed"):
            self.assertIn(fact, r)

    def test_git_dash_c_another_copy_push_is_denied(self):
        self.active_j7()
        self.assertEqual(self.decision(f"git -C {self.other} push", self.worktree), "deny")
        self.assertEqual(self.decision(f"git --no-pager -c a=b -C {self.other} rebase main", self.worktree), "deny")

    def test_over_reporting_a_cd_after_the_commit_and_one_it_cannot_resolve(self):
        self.active_j7()
        self.assertEqual(self.decision(f"git commit -m x; cd {self.other}", self.worktree), "deny", "order is not modelled")
        self.assertEqual(self.decision("cd $OTHER && git commit -m x", self.worktree), "deny", "a variable is outside")
        self.assertEqual(self.decision(f"bash -c 'cd {self.other} && git push'", self.worktree), "deny", "a shell's script")
        self.assertEqual(self.decision(f"bash <<'EOF'\ncd {self.other}\ngit commit -m x\nEOF", self.worktree), "deny", "a heredoc fed to a shell")
        self.assertEqual(self.decision(f"git commit -m 'a <<EOF'\ncd {self.other}", self.worktree), "deny", "a `<<` with no terminator is text")
        self.assertEqual(self.decision("git commit -F - <<'EOF'\nsubject, cd /elsewhere\nEOF", self.worktree), "allow", "a message body is data")

    def test_gh_pr_create_in_another_copy_is_denied(self):
        self.active_j7()
        self.assertEqual(self.decision("gh pr create --fill", self.other), "deny")
        self.assertEqual(self.decision(f"cd {self.other} && fabric-pr arm 12", self.worktree), "deny")

    def test_a_session_that_worked_a_job_now_closed_is_denied_every_commit(self):
        self.write_jobs(self.job("j6", "delivered", sessions=(SESSION,)))
        self.assertEqual(self.decision("git commit -m x", self.proj), "deny", "no job active: the incident's shape")
        r = self.reason("git commit -m x", self.proj)
        self.assertIn("worked job j6", r)
        self.assertIn("no job is active", r)
        self.assertEqual(self.decision("git status", self.proj), "allow", "reading stays allowed")

    def test_the_session_that_switched_is_not_the_next_job_s_session(self):
        # switch settled j6 and activated j7 in this session (both logs carry it), and printed fabric-fresh --job j7.
        self.write_jobs(self.job("j6", "delivered", sessions=(SESSION,)),
                        self.job("j7", "active", sessions=(SESSION,), worktree=self.worktree))
        self.assertEqual(self.decision("git commit -m x", self.worktree), "deny")
        self.assertIn("fabric-fresh --job j7", self.reason("git commit -m x", self.worktree))

    def test_the_session_that_activated_its_own_job_works_it(self):
        self.active_j7(sessions=(SESSION,))
        self.assertEqual(self.decision("git commit -m x", self.worktree), "allow")

    def test_an_unbound_session_is_allowed(self):
        self.assertEqual(self.decision(f"cd {self.other} && git commit -m x", self.proj), "allow", "no list at all")
        self.write_jobs(self.job("j6", "queued"))
        self.assertEqual(self.decision(f"cd {self.other} && git push", self.proj), "allow", "nothing active, nothing worked")

    def test_without_a_session_id_the_last_fallback_is_not_used(self):
        self.write_jobs(self.job("j6", "delivered", sessions=(OLD,)), last="j6")
        self.assertEqual(self.decision("git commit -m x", self.other, session=None), "allow")

    def test_the_payload_s_session_id_stands_in_for_the_variable(self):
        self.write_jobs(self.job("j6", "delivered", sessions=(SESSION,)))
        self.assertEqual(self.decision("git commit -m x", self.proj, session=None, payload_session=SESSION), "deny")

    def test_an_unreadable_job_list_asks(self):
        os.makedirs(os.path.dirname(self.jobs_file), exist_ok=True)
        with open(self.jobs_file, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertEqual(self.decision("git commit -m x", self.proj), "ask")
        self.assertIn("could not read this login's job list", self.reason("git commit -m x", self.proj))

    def test_a_job_module_that_cannot_be_loaded_asks(self):
        self.active_j7()
        fabric = os.path.join(self.home, "fabric")
        os.makedirs(fabric)
        payload = {"tool_name": "Bash", "cwd": self.proj, "tool_input": {"command": "git commit -m x"}}
        r = hook_harness.run(ENTRY, json.dumps(payload),
                             hook_harness.env(self.home, AGENT_FABRIC_ROOT=fabric, CLAUDE_CODE_SESSION_ID=SESSION), cwd=self.proj)
        self.assertEqual(json.loads(r.out)["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_an_active_job_without_a_working_copy_asks(self):
        self.write_jobs(self.job("j7", "active", sessions=(OLD,), working_copy=None))
        self.assertEqual(self.decision("git commit -m x", self.proj), "ask")

    def test_malformed_input_is_passed(self):
        for stdin in ("", "not json", "[]", '{"tool_name":"Bash"}', '{"tool_name":"Bash","tool_input":{"command":7}}'):
            with self.subTest(stdin=stdin):
                r = hook_harness.run(ENTRY, stdin, hook_harness.env(self.home, AGENT_FABRIC_ROOT=hook_harness.ROOT), cwd=self.proj)
                self.assertEqual((r.rc, r.out), (0, ""))

    def test_git_pointed_at_another_copy_through_the_environment_is_denied(self):
        self.active_j7()
        o, p = self.other, self.proj
        for cmd in (f"GIT_DIR={o}/.git git commit -m x", f"env -i GIT_DIR={o}/.git GIT_WORK_TREE={o} git push",
                    f"export GIT_DIR={o}/.git; git commit -m x", f"GIT_WORK_TREE={o} git commit -m x",
                    f"declare -x GIT_COMMON_DIR={o}/.git && git commit -m x", f"env -u X GIT_DIR={o}/.git git push",
                    f"export GIT_DIR={o}/.git\ncd {p}\ngit commit -m x", "GIT_DIR=$OTHER git commit -m x",
                    "export GIT_DIR; git commit -m x", f"env -C {o} git commit -m x"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, p), "deny")
        for cmd in (f"GIT_DIR={p}/.git git commit -m x", f"env -i GIT_DIR={p}/.git GIT_WORK_TREE={p} git push",
                    f"export GIT_DIR={p}/.git; git commit -m x", f"GIT_WORK_TREE={self.worktree} git commit -m x",
                    f"GIT_DIR={p}/.git; export GIT_DIR; git commit -m x"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, p), "allow")
        self.assertIn(f"{o}/.git", self.reason(f"GIT_DIR={o}/.git git commit -m x", p))

    def test_git_dir_and_work_tree_options(self):
        self.active_j7()
        for cmd in (f"git --git-dir={self.other}/.git commit -m x", f"git --git-dir {self.other}/.git push",
                    f"git --work-tree={self.other} commit -m x", f"git --work-tree {self.other} commit -m x"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, self.proj), "deny")
        self.assertEqual(self.decision(f"git --git-dir={self.proj}/.git --work-tree={self.proj} commit -m x", self.proj), "allow")

    def test_a_work_tree_set_through_git_config_is_judged(self):
        # Review round 2 of #348, P-a: core.worktree is a --work-tree by another name.
        self.active_j7()
        for cmd in (f"git -c core.worktree={self.other} commit -m x", f"git -c Core.WorkTree={self.other} push",
                    "git -c core.worktree=$W commit -m x", "git --config-env=core.worktree=W commit -m x",
                    "git --config-env core.worktree=W push", "GIT_CONFIG_PARAMETERS=\"'core.worktree'='/x'\" git commit -m x",
                    "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.worktree GIT_CONFIG_VALUE_0=/x git commit -m x",
                    "export GIT_CONFIG_GLOBAL=/tmp/cfg; git push", "export GIT_CONFIG; git commit -m x",
                    "env GIT_CONFIG_SYSTEM=/tmp/cfg git commit -m x"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, self.proj), "deny")
        for cmd in ("git -c user.name=x commit -m y", f"git -c core.worktree={self.proj} commit -m x",
                    "GIT_CONFIG_COUNT=1 git log", "git --config-env=user.name=N commit -m x"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, self.proj), "allow")

    def test_eval_and_command_substitution_are_read(self):
        self.active_j7()
        for cmd in (f"eval \"cd {self.other} && git commit -m x\"", f"echo \"$(cd {self.other} && git push)\"",
                    f"x=$(git -C {self.other} commit -m y)", f"echo `git -C {self.other} push`"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, self.proj), "deny")
        self.assertEqual(self.decision("eval \"git commit -m x\"", self.proj), "allow")
        self.assertEqual(self.decision(f"x=$(git -C {self.worktree} commit -m y)", self.proj), "allow")

    def test_a_publish_to_a_named_repository_is_judged_against_the_copy_s_remotes(self):
        self.active_j7()
        for cmd in ("gh pr merge 5 -R acme/proj", "gh pr merge 5 -Racme/proj", "gh pr create --repo Acme/Proj --fill",
                    "gh pr create --repo=github.com/acme/proj --fill", "gh pr merge -R https://github.com/acme/proj.git 5",
                    "gh pr merge --hostname github.com -R acme/proj-mirror 5", "fabric-pr --repo acme/proj arm 12",
                    "fabric-pr arm 12 --repo=ACME/proj", "fabric-pr --repo proj arm 12", "GH_REPO=acme/proj gh pr merge 5",
                    "gh pr view -R acme/other 5 && git commit -m x", "fabric-pr gate --repo acme/other"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, self.worktree), "allow")
        for cmd in ("gh pr merge 5 -R acme/other", "gh pr create --repo acme/other --fill", "fabric-pr --repo acme/other arm 12",
                    "fabric-pr arm 12 --repo=other-owner/proj", "fabric-pr --repo another-project arm 12",
                    "GH_REPO=acme/other gh pr create --fill", "export GH_REPO=acme/other; gh pr merge 3",
                    "GH_REPO=acme/other fabric-pr arm 3", "gh pr merge -R gitlab.com/acme/proj 5",
                    "GH_HOST=gitlab.com gh pr merge -R acme/proj 5", "gh pr merge -R $REPO 5", "gh pr merge -R a/b/c/d 5"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, self.worktree), "deny")
        r = self.reason("gh pr merge 5 -R acme/other", self.worktree)
        for fact in ("acme/other", "github.com/acme/proj", "gh pr merge", "j7"):
            self.assertIn(fact, r)

    def test_a_pull_request_url_names_its_repository(self):
        # Review round 2 of #348, F2: gh acts on a URL's repository whatever the cwd.
        self.active_j7()
        for cmd in ("gh pr merge https://github.com/acme/other/pull/5", "gh pr merge https://github.com/acme/other/pull/5/files",
                    "gh pr merge --squash http://github.com/acme/other/pull/5", "gh pr merge https://gitlab.com/acme/proj/pull/5",
                    "GH_REPO=acme/proj gh pr merge https://github.com/acme/other/pull/5",
                    "gh pr merge https://github.com/acme/other/pull/5#issuecomment-1",
                    "gh pr merge https://github.com/acme/other/pull/5?x=1",
                    "gh pr merge https://u@GitLab.com:8443/acme/proj/pull/5"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, self.worktree), "deny")
        for cmd in ("gh pr merge https://github.com/Acme/Proj/pull/5", "gh pr merge --squash https://github.com/acme/proj-mirror/pull/7/checks",
                    "gh pr merge https://github.com/acme/proj/pull/5#issuecomment-1",
                    "gh pr merge https://user@GitHub.com:443/acme/proj/pull/5?x=1",
                    "gh pr view https://github.com/acme/other/pull/5"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, self.worktree), "allow")
        self.assertIn("acme/other/pull/5", self.reason("gh pr merge https://github.com/acme/other/pull/5", self.worktree))

    def test_a_copy_whose_remotes_cannot_be_read_asks_for_a_named_repository(self):
        self.write_jobs(self.job("j7", "active", sessions=(OLD,), working_copy=self.plain))
        self.assertEqual(self.decision("gh pr merge 1 -R acme/proj", self.plain), "ask")
        self.assertIn("could not read the remotes", self.reason("gh pr merge 1 -R acme/proj", self.plain))
        self.assertEqual(self.decision("gh pr merge 1", self.plain), "allow", "no repository named: no remotes read")

    def test_only_an_unquoted_heredoc_operator_opens_a_heredoc(self):
        self.active_j7()
        o = self.other
        for cmd in (f"echo '<<X'\ncd {o}\ngit commit -m x\nX", f"echo \"a <<X\"\ncd {o}\ngit commit -m x\nX",
                    f"echo a \\<<X\ncd {o}\ngit commit -m x\nX", f"echo hi # <<X\ncd {o}\ngit commit -m x\nX",
                    f"echo 'two\nlines <<X'\ncd {o}\ngit commit -m x\nX"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, self.proj), "deny")
        # The hidden lines hold only the cd and the act follows the "terminator": the act-word backstop would not
        # see these, so they hold the quote-aware scan itself.
        for cmd in (f"echo '<<X'\ncd {o}\nX\ngit commit -m x", f"echo 'a <<X b'\ncd {o}\nX\ngit commit -m x",
                    f"echo hi # <<X\ncd {o}\nX\ngit commit -m x",
                    f"echo \"<<-X\"\ncd {o}\nX\ngit push"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, self.proj), "deny")

    def test_a_quoted_heredoc_body_is_data_unless_it_is_executed(self):
        # Review round 2 of #348, F5: a body that is only read or published, however much it names, never asks.
        self.active_j7()
        o = self.other
        acting = f"cd {o} && git commit -m y\ngit -C {o} push"
        for cmd in (f"git commit -F - <<'EOF'\nsubject\n\nthen git push from cd {o}\nEOF",
                    f"git commit -F /dev/stdin <<'EOF'\ngit -C {o} push\nEOF",
                    f"git commit -m \"$(cat <<'EOF'\nsubject\n\n{acting}\nEOF\n)\"",
                    f"cat <<'X'\n{acting}\nX", f"cat <<'EOF' > notes\ncd {o}\nEOF\ngit commit -m x",
                    f"fabric-pr post-review 5 <<'EOF'\nFinding: {acting}\nEOF",
                    f"gh pr create --title 'fix sh quoting' --body-file - <<'EOF'\n{acting}\nEOF",
                    f"x=$(cat <<'X'\n{acting}\nX\n)",
                    "git commit -F - <<'M'\nsubject\nM",
                    f"git add . && git commit -F - <<'M'\nsubject, git push\nM"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, self.proj), "allow")
        # Review round 3 of #348: a runner word anywhere reads every body; publishing a body beside a shell is
        # over-reported, accepted.
        self.assertEqual(self.decision(f"bash <<'S' && git commit -F - <<'M'\necho hi\nS\n{acting}\nM", self.proj), "deny")
        for cmd in (f"bash <<'X'\n{acting}\nX", f"sh -s <<'X'\n{acting}\nX", f"source /dev/stdin <<'X'\n{acting}\nX",
                    f". /dev/stdin <<'X'\n{acting}\nX", f"cat <<'X' 2>&1 | dash\n{acting}\nX",
                    f"xargs -0 <<'X'\n{acting}\nX", f"env -S'bash -s' <<'X'\n{acting}\nX",
                    f"eval \"$(cat <<'X'\n{acting}\nX\n)\"", f"bash -c \"$(cat <<'X'\n{acting}\nX\n)\"",
                    f"\"$(cat <<'X'\n{acting}\nX\n)\"",
                    # P-b: a commit message beside a body fed to source excuses only itself.
                    f"git commit -F - <<'M' && source /dev/stdin <<'S'\nsubject\nM\n{acting}\nS"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, self.proj), "deny")

    def test_a_runner_word_anywhere_reads_every_body(self):
        # Review round 3 of #348, F6: where stdin goes is not modelled; a runner word anywhere is enough.
        self.active_j7()
        o = self.other
        acting = f"cd {o} && git commit -m y\ngit -C {o} push"
        for cmd in (f"cat <<'X' |& bash\n{acting}\nX", f"{{ bash; }} <<'X'\n{acting}\nX",
                    f"while read -r l; do eval \"$l\"; done <<'X'\n{acting}\nX",
                    f"if true; then bash; fi <<'X'\n{acting}\nX", f"fish <<'X'\n{acting}\nX",
                    *(f"cat <<'X' | {shell}\n{acting}\nX" for shell in ("fish", "ash", "mksh", "csh", "tcsh", "yash")),
                    f"cat <<'X' | busybox hush\n{acting}\nX", f"true && . /dev/stdin <<'X'\n{acting}\nX",
                    f"if true; then . /dev/stdin; fi <<'X'\n{acting}\nX",
                    # Review round 4 of #348, F7: a simple command may open with assignments and redirections.
                    f"x=1 . /dev/stdin <<'X'\n{acting}\nX", f"2>/dev/null . /dev/stdin <<'X'\n{acting}\nX",
                    f"<<'X' . /dev/stdin\n{acting}\nX", f"time -p . /dev/stdin <<'X'\n{acting}\nX",
                    f"> /tmp/log . /dev/stdin <<'X'\n{acting}\nX",
                    # A command word the guard cannot read may be a shell.
                    f"cat <<'X' | $SHELL\n{acting}\nX", f"cat <<'X' | \"$0\"\n{acting}\nX",
                    # Round 5: fd duplication splits into three words; a launcher runs the word after it.
                    f"x=1 2>&1 . /dev/stdin <<'X'\n{acting}\nX", f"> /tmp/l 2>&1 . /dev/stdin <<'X'\n{acting}\nX",
                    f"x=1 0<&3 . /dev/stdin <<'X'\n{acting}\nX", f"command -p . /dev/stdin <<'X'\n{acting}\nX",
                    f"cat <<'X' | env $SHELL\n{acting}\nX"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, self.proj), "deny")
        # `.` as a path argument is no runner: the commit message every `git add .` precedes stays data.
        for cmd in (f"git add . && git commit -F - <<'M'\nsubject\n\n{acting}\nM",
                    f"git add -- . ; fabric-pr post-review 5 <<'EOF'\n{acting}\nEOF",
                    # An expansion that is plainly an argument is no runner.
                    f"[ -n \"$X\" ] && git commit -F - <<'M'\nsubject\n\n{acting}\nM",
                    f"echo \"$HOME\"; git status | tee $LOG; git commit -F - <<'M'\nsubject\n\n{acting}\nM"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, self.proj), "allow")

    def test_stdin_executed_reads_a_pipe_and_stderr_as_a_pipe(self):
        # `|&` keeps the pipeline open: the whole-command fallback hides this from decide, so the model is held here.
        guard = self.load_guard()
        text = "cat <<X |& bash"
        self.assertEqual(guard.stdin_executed(text, [len("cat <<X")]), {0})
        text = "cat x |& \"$(cat <<X)\""
        self.assertEqual(guard.stdin_executed(text, [text.index("<<X") + 3]), {0}, "a substitution after |& stands in command place")

    def test_git_reading_configuration_from_elsewhere_is_unresolvable(self):
        # Review round 3 of #348: an included file or a moved global config can set core.worktree.
        self.active_j7()
        for cmd in ("git -c include.path=/tmp/c commit -m x", "git -c includeIf.gitdir:/x/.path=/tmp/c push",
                    "git --config-env=include.path=V commit -m x", "HOME=/tmp/h git commit -m x",
                    "export XDG_CONFIG_HOME=/x; git push", "GIT_CONFIG_NOSYSTEM=1 git commit -m x",
                    "GIT_CEILING_DIRECTORIES=/x git commit -m x"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, self.proj), "deny")
        for cmd in ("git -c user.name=x commit -m y", "git -c includes.paths=x commit -m y", "HOME=/tmp/h git log"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, self.proj), "allow")

    def test_an_unquoted_heredoc_body_runs_only_its_substitutions(self):
        self.active_j7()
        o = self.other
        for cmd in ("cat <<EOF\nthen cd x; git push\nEOF", f"git commit -F - <<EOF\ncd {o}\ngit push\nEOF",
                    f"cat <<EOF\nescaped \\$(cd {o} && git push)\nEOF"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, self.proj), "allow")
        for cmd in (f"cat <<EOF > notes\n$(cd {o} && git commit -m x)\nEOF",
                    f"git commit -F - <<EOF\nsubject `git -C {o} push`\nEOF",
                    f"cat <<EOF\n$(echo \")\"; cd {o} && git push)\nEOF"):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision(cmd, self.proj), "deny")

    def load_guard(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("job_copy_guard_under_test", os.path.join(os.path.dirname(ENTRY), "job-copy-guard.py"))
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        self.addCleanup(sys.modules.pop, "fabric_jobs", None)
        self.addCleanup(sys.modules.pop, "fabric_jobs.records", None)
        return guard

    def test_the_git_lookup_budget_asks(self):
        from unittest import mock
        self.active_j7()
        guard = self.load_guard()

        def clock(step: float):
            now = [0.0]

            def tick() -> float:
                now[0] += step
                return now[0]
            return tick

        env = {"HOME": self.home, "XDG_STATE_HOME": os.path.join(self.home, ".state"), "CLAUDE_CODE_SESSION_ID": SESSION}
        payload = {"tool_name": "Bash", "cwd": self.agent_tree, "tool_input": {"command": "cd sub && git commit -m x"}}
        with mock.patch.dict(os.environ, env):
            os.environ.pop("AGENT_FABRIC_STATE_DIR", None)
            self.assertIsNone(guard.decide(payload, clock=clock(0.0)), "inside, with time to spare")
            verdict = guard.decide(payload, clock=clock(4.0))      # each lookup "takes" 4 s: the second passes 6 s
        self.assertEqual(verdict[0], "ask")
        self.assertIn("6 s budget", verdict[1])

    def test_it_stays_fast(self):
        self.active_j7()
        for cmd in ("git commit -m x", "ls -la"):
            start = time.monotonic()
            self.run_hook(cmd, self.worktree)
            # The hook's timeout is 10 s; this bound is loose on purpose, so a loaded host does not make it red.
            self.assertLess(time.monotonic() - start, 5.0, cmd)


if __name__ == "__main__":
    sys.exit(unittest.main())
