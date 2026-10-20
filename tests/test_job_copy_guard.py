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
command that commits or publishes.

Mutations each case set fails on: the agent_id test removed; `cd` or `-C` targets not collected; the prefix test made
a plain string prefix (proj-other would pass as proj); "worked the active job" counted as allowed (the switching
session); the `last` fallback used without a session id; the list read before the command is parsed; the ask on an
unreadable list replaced by an allow.
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

    def test_it_stays_fast(self):
        self.active_j7()
        for cmd in ("git commit -m x", "ls -la"):
            start = time.monotonic()
            self.run_hook(cmd, self.worktree)
            # The hook's timeout is 10 s; this bound is loose on purpose, so a loaded host does not make it red.
            self.assertLess(time.monotonic() - start, 5.0, cmd)


if __name__ == "__main__":
    sys.exit(unittest.main())
