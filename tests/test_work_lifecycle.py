#!/usr/bin/env python3
"""The work lifecycle as the job list lives it today, pinned against the transition table of agent-fabric ADR-037 rule 14
(A 2026-11-08, as corrected at eee64007): a characterisation, not a specification. Every case runs the real command, `bin/fabric-jobs`,
against a scratch state directory, bare origins and a fake gh (tests/work_lifecycle_world.py), so that the one model of a job that
follows (the WorkItem of wave 2) can be checked against what the paths do now. No production module is changed. The command is what is pinned; one case (R6b, `switch --needs-merged`) loads jobs.py in
process to stub the pull-request count, `branching._addable`, which has no other seam.

The table's rows, by the label the cases carry:
  R1   -> open in a role's pool            pool-add                      tests/test_work_lifecycle_pool.py
  R2   open -> claimed (the holder's)      pool-claim                    tests/test_work_lifecycle_pool.py
  R2b  -> queued (the claimant's own)      fabric-jobs pool-claim        tests/test_work_lifecycle_pool.py
  R3   -> queued                           add, intake, jobs-add         Entry here; tests/test_work_lifecycle_intake.py
  R3b  -> any state, as exported           import                        Entry
  R4   queued, paused, blocked, delivered -> active     start, switch    Working
  R5   active -> paused                    pause                         Working
  R6   queued, active, paused, blocked -> blocked       block            Blocked; tests/test_work_lifecycle_blockers.py
  R6b  queued, paused, blocked -> blocked  switch (rule 10 step 3)       Blocked
  R7   active, blocked -> delivered        deliver                       Delivered
  R8   delivered -> done                   sweep                         Delivered
  R9   active, delivered -> done           done                          Delivered, Leaving
  R10  queued, active, paused, blocked, delivered -> dropped   drop      Closed
and the terminal states: nothing reopens done or dropped (Closed). `Leaving` is rule 10 step 1, the row's "needs" asked again of the
job `switch` leaves. VerbMatrix runs every verb from every state and names the cells the table does not have; Findings holds, for
each place where today's code makes a transition outside the table, or one without what its row needs, a case with today's answer and
an expectedFailure case with the answer the table gives (F1..F8 here; F9 in the pool suite, F10 in the blockers', F11 in the intake's;
all listed in the pull request). A fix turns the second green; the change that makes it removes the decorator.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, this script's own directory
from instance_fixtures import own_instance_tree  # noqa: E402
scrub_process_env()
own_instance_tree()
import jobs_world  # noqa: E402
from work_lifecycle_world import OTHER_REPO, World  # noqa: E402

LANDED = jobs_world.LANDED
OPEN_PR = f"{jobs_world.GH_REPO}#2"
RID = "01a11a18-4728-7d8b-afd9-0edb2d30a59c"
STATES = ("queued", "active", "paused", "blocked", "delivered", "done", "dropped")
VERBS = {
    "start": ("start", "j1"),
    "pause": ("pause", "j1", "set aside"),
    "block": ("block", "j1", "owner: a review"),
    "deliver": ("deliver", "j1", OPEN_PR),
    "done": ("done", "j1"),
    "drop": ("drop", "j1", "no longer wanted"),
}


class Case(unittest.TestCase):
    def setUp(self) -> None:
        self.w = World()
        self.addCleanup(self.w.close)
        self.w.gh_says({LANDED: "MERGED", OPEN_PR: "OPEN"})

    def ok(self, *argv: str, **kw) -> subprocess.CompletedProcess:
        p = self.w.run(*argv, **kw)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p

    def refused(self, *argv: str, said: str, **kw) -> None:
        p = self.w.run(*argv, **kw)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn(said, p.stderr)

    def state(self, job_id: str = "j1") -> str:
        return self.w.job(job_id)["state"]

    def seed(self, state: str, job_id: str = "j1", **fields) -> None:
        """Force a job into a state as another writer of jobs.json could, without a verb's checks."""
        def edit(doc):
            job = next(j for j in doc["jobs"] if j["id"] == job_id)
            job["state"] = state
            for key in ("blocked_on", "waits_on", "blockers", "reason", "no_artifact"):
                job.pop(key, None)
            job.update(fields)
        self.w.put(edit)

    def working(self, title: str = "work") -> str:
        """A job taken by switch, in this session: a branch, a worktree and an active state."""
        job_id = self.w.add(title)
        p = self.w.switch()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.state(job_id), "active")
        return job_id

    def switch_needing_merged(self) -> tuple[int, str]:
        """`switch --needs-merged` in process, with an open pull request of this login that cannot take more commits: the pull
        request's arming count is a tool of its own (branching._addable), stubbed here; everything else is the command's."""
        import contextlib
        import importlib.util
        import io
        from unittest import mock
        spec = importlib.util.spec_from_file_location("jobs_in_process", os.path.join(HERE, "..", "tools", "fabric", "jobs.py"))
        with open(os.path.join(self.w.fake, "bin", "gh"), "w", encoding="utf-8") as fh:
            fh.write(FAKE_GH_WITH_PRS)
        jobs_world.touch_memory(self.w.env["HOME"], self.w.alpha)
        buf = io.StringIO()
        cwd = os.getcwd()
        with mock.patch.dict(os.environ, self.w.env, clear=True):
            jobs = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(jobs)
            branching = sys.modules["fabric_jobs"].branching
            prefix = f"{branching.identity.current_host()}/{branching.identity.current_agent()}/"
            with open(os.path.join(self.w.fake, "gh.json"), "w", encoding="utf-8") as fh:
                json.dump({"states": {}, "open_prs": [{"number": 40, "headRefName": prefix + "feat/earlier", "isDraft": False}]}, fh)
            os.chdir(self.w.alpha)
            try:
                with mock.patch.object(branching, "_addable", lambda repo, number: f"{repo}#{number} is armed"), \
                        contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    rc = jobs.main(["switch", "--needs-merged"])
            finally:
                os.chdir(cwd)
        return rc, buf.getvalue()

    def working_after(self, previous: str, title: str) -> str:
        """The job `leave(previous)` started, which is active in this session; `title` names it for the reader of a failure."""
        (job,) = [j for j in self.w.jobs() if j["state"] == "active"]
        self.assertNotEqual(job["id"], previous, title)
        return job["id"]

    def leave(self, job_id: str, then: str = "next") -> subprocess.CompletedProcess:
        """switch away from the job this session worked last, to another queued one."""
        return self.w.switch(self.w.add(then))


class Entry(Case):
    """-> queued: the paths of the list itself (the pool's and the intake's are in their own suites)."""

    def test_add_queues_with_source_self_and_a_log(self):
        self.ok("add", "first  job", "--topic", "t")
        job = self.w.job("j1")
        self.assertEqual((job["state"], job["title"], job["source"], job["topic"]), ("queued", "first job", {"kind": "self"}, "t"))
        self.assertEqual([e["state"] for e in job["log"]], ["queued"])

    def test_import_keeps_every_state_and_id(self):
        # Row R3b: any state as exported, an empty list, at most one job active. The document's states are taken as written (a done
        # job needs no evidence), so what import accepts is the checks on the document, not the lifecycle's.
        self.w.add("a")
        self.w.add("b")
        self.seed("done", "j2", no_artifact="housekeeping")
        self.ok("start", "j1")
        exported = self.ok("export").stdout
        other = World()
        self.addCleanup(other.close)
        p = other.run("import", stdin=exported)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual({j["id"]: j["state"] for j in other.jobs()}, {"j1": "active", "j2": "done"})

    def test_import_refuses_a_list_that_has_a_job(self):
        self.w.add("a")
        exported = self.ok("export").stdout
        self.w.add("b")
        p = self.w.run("import", stdin=exported)
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertTrue(p.stderr.strip(), "a refusal names itself")
        self.assertEqual([j["id"] for j in self.w.jobs()], ["j1", "j2"])


class Working(Case):
    """queued / paused / blocked -> active, by start and by switch; active -> paused; one active job at a time."""

    def test_start_takes_a_queued_job(self):
        self.w.add("a")
        self.ok("start", "j1")
        self.assertEqual(self.state(), "active")
        self.assertEqual([e["state"] for e in self.w.job("j1")["log"]], ["queued", "active"])

    def test_a_second_active_job_is_refused_by_start(self):
        self.w.add("a")
        self.w.add("b")
        self.ok("start", "j1")
        self.refused("start", "j2", said="j1 is active")
        self.assertEqual(self.state("j2"), "queued")

    def test_start_resumes_a_paused_job_and_drops_its_reason(self):
        self.w.add("a")
        self.seed("paused", "j1", reason="later")
        self.ok("start", "j1")
        self.assertEqual(self.state(), "active")
        self.assertNotIn("reason", self.w.job("j1"))

    def test_start_takes_a_blocked_job_and_drops_what_it_waited_on(self):
        self.w.add("a")
        self.ok("block", "j1", "--on-request", "01a11a18-4728-7d8b-afd9-0edb2d30a59c")
        self.assertIn("waits_on", self.w.job("j1"))
        # R4 from blocked: every blocker cleared (F4). The wait is over when the cache says so; the same start refuses before.
        self.refused("start", "j1", said="is still blocked")
        self.seed("blocked", "j1", waits_on="01a11a18-4728-7d8b-afd9-0edb2d30a59c", blockers=["clock:2020-01-01T00:00:00Z"],
                  blocked_on="clock:2020-01-01T00:00:00Z")
        self.ok("start", "j1")
        job = self.w.job("j1")
        self.assertEqual(job["state"], "active")
        self.assertNotIn("waits_on", job)
        self.assertNotIn("blockers", job)

    def test_switch_takes_the_first_queued_job_on_a_new_branch(self):
        self.w.add("low", priority="low")
        self.w.add("high", priority="high")
        p = self.w.switch()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((self.state("j2"), self.state("j1")), ("active", "queued"))
        job = self.w.job("j2")
        self.assertTrue(job["branch"].endswith("/feat/j2-high") and os.path.isdir(job["worktree"]), job)
        self.assertEqual(job["working_copy"], job["worktree"])

    def test_switch_by_id_takes_a_paused_job_back_on_its_own_branch(self):
        j1 = self.working("a")
        branch = self.w.job(j1)["branch"]
        self.ok("pause", j1, "later", cwd=self.w.job(j1)["worktree"])
        subprocess.run(["git", "-C", self.w.job(j1)["worktree"], "push", "-q", "origin", branch], check=True, env=git_env())
        p = self.w.switch(j1)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((self.state(j1), self.w.job(j1)["branch"]), ("active", branch))

    def test_switch_takes_a_blocked_job_whose_blockers_all_cleared_before_anything_queued(self):
        self.w.add("queued first")
        self.w.add("blocked")
        self.ok("block", "j2", "--on", "clock:2099-01-01T00:00Z")
        self.seed("blocked", "j2", blockers=["clock:2020-01-01T00:00:00Z"], blocked_on="clock:2020-01-01T00:00:00Z")
        p = self.w.switch()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((self.state("j2"), self.state("j1")), ("active", "queued"))

    def test_switch_refuses_while_a_job_is_active(self):
        self.w.add("a")
        self.ok("start", "j1")
        self.w.add("b")
        p = self.w.switch()
        self.assertEqual(p.returncode, 1)
        self.assertIn("j1 is still active", p.stderr)

    def test_switch_by_id_takes_a_delivered_job_as_start_does(self):
        # R4 names start and switch for one set of from-states, delivered included (F4).
        self.w.add("a")
        self.seed("delivered", "j1", artifacts=[OPEN_PR])
        p = self.w.switch("j1")
        self.assertEqual((p.returncode, self.state()), (0, "active"), p.stdout + p.stderr)

    def test_start_and_switch_start_nothing_while_the_login_is_held(self):
        self.w.add("a")
        self.w.put(lambda doc: None)
        hold = os.path.join(os.path.dirname(self.w.path), "hold.json")
        with open(hold, "w", encoding="utf-8") as fh:
            json.dump({"reason": "fleet upgrade", "set_by": "h/user"}, fh)
        self.refused("start", "j1", said="this login is held")
        p = self.w.switch()
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("this login is held", p.stderr)
        self.assertEqual(self.state(), "queued")
        os.unlink(hold)
        self.ok("start", "j1")

    def test_start_refuses_a_job_of_a_project_that_has_no_working_copy_here(self):
        self.w.add("a", project="fixture-proj")
        self.w.put(lambda doc: doc["jobs"][0].update(working_copy=None))
        self.refused("start", "j1", said="has no working copy")
        self.assertEqual(self.state(), "queued")


    def test_pause_sets_the_active_job_aside_with_its_reason(self):
        j1 = self.working("a")
        self.ok("pause", j1, "  needs   a review ", cwd=self.w.job(j1)["worktree"])
        self.assertEqual((self.state(), self.w.job("j1")["reason"]), ("paused", "needs a review"))

    def test_pause_refuses_a_job_that_is_not_active_and_a_reason_that_is_empty(self):
        self.w.add("a")
        self.refused("pause", "j1", "why", said="j1 is queued; pause takes a job that is active")
        p = self.w.switch()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.refused("pause", "j1", "  ", said="pause needs a reason", cwd=self.w.job("j1")["worktree"])
        self.assertEqual(self.state(), "active")


class Blocked(Case):
    """active -> blocked, by block and by switch; the checkable forms; leaving blocked drops what it waited on."""

    def test_block_records_an_owners_decision_and_nothing_checkable(self):
        self.w.add("a")
        self.ok("start", "j1")
        self.ok("block", "j1", "owner: a review of the PR")
        job = self.w.job("j1")
        self.assertEqual((job["state"], job["blocked_on"]), ("blocked", "owner: a review of the PR"))
        self.assertNotIn("blockers", job)

    def test_block_on_a_checkable_blocker_keeps_it_in_the_list(self):
        self.w.add("a")
        self.ok("block", "j1", "--on", "pr:o/r#5", "--on", "clock:2099-01-01T00:00Z")
        job = self.w.job("j1")
        self.assertEqual(job["blockers"], ["pr:o/r#5", "clock:2099-01-01T00:00:00Z"])
        self.assertEqual(job["blocked_on"], "pr:o/r#5, clock:2099-01-01T00:00:00Z")

    def test_block_on_request_keeps_the_message_id_as_waits_on_and_a_checkable_blocker(self):
        mid = "01a11a18-4728-7d8b-afd9-0edb2d30a59c"
        self.w.add("a")
        self.ok("block", "j1", "--on-request", mid.upper())
        job = self.w.job("j1")
        self.assertEqual((job["waits_on"], job["blockers"], job["blocked_on"]), (mid, [f"request:{mid}"], f"request {mid}"))

    def test_block_refuses_a_time_already_past_and_a_block_on_nothing(self):
        self.w.add("a")
        self.refused("block", "j1", "--on", "clock:2020-01-01T00:00Z", said="has already passed")
        self.refused("block", "j1", said="block needs what the job waits on")
        self.assertEqual(self.state(), "queued")

    def test_a_new_block_replaces_the_whole_wait(self):
        self.w.add("a")
        self.ok("block", "j1", "--on", "pr:o/r#5")
        self.ok("block", "j1", "owner: words only")
        job = self.w.job("j1")
        self.assertEqual(job["blocked_on"], "owner: words only")
        self.assertNotIn("blockers", job)

    def test_switch_blocks_a_job_on_the_pull_request_that_must_merge_first(self):
        # Row R6b: the one path on which `switch` writes `blocked`, adding the pull request to the blockers, never substituting it.
        self.w.add("needs the open one merged")
        rc, said = self.switch_needing_merged()
        self.assertEqual(rc, 0, said)
        job = self.w.job("j1")
        self.assertEqual((job["state"], job["blockers"]), ("blocked", [f"pr:{jobs_world.GH_REPO}#40"]), job)
        self.assertNotIn("branch", job)


FAKE_GH_WITH_PRS = """#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
doc = json.load(open(os.path.join(os.environ["FAKE_DIR"], "gh.json")))
if a[:2] == ["pr", "view"] and "--repo" in a:
    key = a[a.index("--repo") + 1] + "#" + a[2]
    if key in doc["states"]:
        print(json.dumps({"state": doc["states"][key]}))
        sys.exit(0)
    sys.stderr.write("GraphQL: Could not resolve to a PullRequest (HTTP 404)\\n")
    sys.exit(1)
if a[:2] == ["pr", "list"]:
    print(json.dumps([] if "merged" in a else doc.get("open_prs", [])))
    sys.exit(0)
sys.stderr.write("fake gh: unsupported: " + " ".join(a) + "\\n")
sys.exit(2)
"""


class Delivered(Case):
    """active -> delivered, by deliver; delivered -> done by sweep and by done; what each takes as evidence."""

    def test_deliver_names_artifacts_and_a_second_deliver_adds_without_duplicating(self):
        self.w.add("a")
        self.ok("start", "j1")
        second = f"{jobs_world.GH_REPO}#3"
        self.w.gh_says({LANDED: "MERGED", OPEN_PR: "OPEN", second: "OPEN"})
        self.ok("deliver", "j1", OPEN_PR, "abc1234")
        self.ok("deliver", "j1", "abc1234", second)
        job = self.w.job("j1")
        self.assertEqual((job["state"], job["artifacts"]), ("delivered", [OPEN_PR, "abc1234", second]))
        # Evidence added to a delivered job is no transition: one `delivered` entry in the log.
        self.assertEqual([e["state"] for e in job["log"] if "state" in e], ["queued", "active", "delivered"])

    def test_deliver_refuses_a_dropped_job_and_adds_evidence_to_a_done_one_without_reopening_it(self):
        self.w.add("a")
        self.seed("done", "j1", no_artifact="housekeeping")
        self.ok("deliver", "j1", LANDED)
        self.assertEqual((self.state(), self.w.job("j1")["artifacts"]), ("done", [LANDED]))
        self.w.add("b")
        self.ok("drop", "j2", "x")
        self.refused("deliver", "j2", LANDED, said="a closed job is not reopened")

    def test_sweep_closes_a_delivered_job_whose_pull_request_merged(self):
        self.w.add("a")
        self.seed("delivered", "j1", artifacts=[LANDED])
        p = self.ok("sweep", "--dry-run")
        self.assertIn("would close", p.stdout)
        self.assertEqual(self.state(), "delivered")
        p = self.ok("sweep")
        self.assertIn("closed (", p.stdout)
        job = self.w.job("j1")
        self.assertEqual(job["state"], "done")
        self.assertTrue(job["log"][-1]["note"].startswith("swept: "), job["log"])

    def test_sweep_keeps_a_job_whose_pull_request_is_open_or_cannot_be_read(self):
        self.w.add("open")
        self.w.add("unreadable")
        self.w.add("no repository")
        self.seed("delivered", "j1", artifacts=[OPEN_PR])
        self.seed("delivered", "j2", artifacts=[f"{jobs_world.GH_REPO}#99"])
        self.seed("delivered", "j3", artifacts=["#3"])
        out = self.ok("sweep").stdout
        self.assertEqual([self.state(j) for j in ("j1", "j2", "j3")], ["delivered"] * 3, out)
        self.assertIn("names no repository", out)

    def test_sweep_touches_no_other_state_and_a_second_run_changes_nothing(self):
        self.w.add("delivered")
        self.w.add("queued")
        self.w.add("paused")
        self.seed("delivered", "j1", artifacts=[LANDED])
        self.seed("paused", "j3", reason="x")
        # Evidence that has landed on the jobs that are not delivered: only the state decides what sweep may close.
        self.w.put(lambda doc: [doc["jobs"][i].update(artifacts=[LANDED]) for i in (1, 2)])
        self.ok("sweep")
        before = self.w.jobs()
        self.ok("sweep")
        self.assertEqual(self.w.jobs(), before)
        self.assertEqual([j["state"] for j in before], ["done", "queued", "paused"])

    def test_done_records_a_reason_when_the_work_leaves_no_artifact(self):
        self.w.add("a")
        self.ok("start", "j1")
        self.ok("done", "j1", "--no-artifact", " moved   a   file ")
        self.assertEqual((self.state(), self.w.job("j1")["no_artifact"]), ("done", "moved a file"))
        self.ok("done", "j1", "--no-artifact", "replaced reason")
        self.assertEqual(self.w.job("j1")["no_artifact"], "replaced reason")
        self.refused("done", "j1", said="a closed job is not reopened")

    def test_done_refuses_an_empty_reason(self):
        self.w.add("a")
        self.refused("done", "j1", "--no-artifact", "  ", said="--no-artifact needs a reason")
        self.assertEqual(self.state(), "queued")


class Closed(Case):
    """-> dropped, and the terminal states: no verb reopens a closed job."""

    def test_drop_keeps_its_reason_in_the_record_and_the_log(self):
        self.w.add("a")
        self.ok("drop", "j1", "superseded")
        job = self.w.job("j1")
        self.assertEqual((job["state"], job["reason"], job["log"][-1]["note"]), ("dropped", "superseded", "superseded"))

    def test_a_closed_job_leaves_the_queue_and_cannot_be_reprioritised(self):
        self.w.add("a")
        self.ok("drop", "j1", "x")
        self.refused("prio", "j1", "high", said="a closed job has no place in the queue")
        self.assertEqual(self.ok("list").stdout.strip(), "no open jobs")

    def test_project_repointing_is_refused_on_a_closed_job(self):
        self.w.add("a")
        self.ok("drop", "j1", "x")
        self.refused("project", "j1", "fixture-proj", said="a closed job is not re-pointed")


class VerbMatrix(Case):
    """Every verb on a job in every state against rule 14's table. A cell is True when the verb is accepted (exit 0). Each cell is
    given what its row needs where the table's state lets it (a pushed branch for pause, a landed artifact for done), so the matrix
    reads the from-states of the table and nothing else; the needs have cases of their own (Findings, Leaving)."""

    ACCEPTED = {
        "start":   {"queued": True,  "active": False, "paused": True,  "blocked": True,  "delivered": True,  "done": False, "dropped": False},
        "pause":   {"queued": False, "active": True,  "paused": False, "blocked": False, "delivered": False, "done": False, "dropped": False},
        "block":   {"queued": True,  "active": True,  "paused": True,  "blocked": True,  "delivered": False, "done": False, "dropped": False},
        "deliver": {"queued": False, "active": True,  "paused": False, "blocked": True,  "delivered": True,  "done": True,  "dropped": False},
        "done":    {"queued": False, "active": True,  "paused": False, "blocked": False, "delivered": True,  "done": False, "dropped": False},
        "drop":    {"queued": True,  "active": True,  "paused": True,  "blocked": True,  "delivered": True,  "done": False, "dropped": False},
    }
    # Rule 14's "from" column per verb. `deliver` on a delivered or a done job adds evidence and is no transition (the rule says
    # so for a closed job), so it is not a cell of the table either way.
    TABLE = {
        "start":   {"queued", "paused", "blocked", "delivered"},
        "pause":   {"active"},
        "block":   {"queued", "active", "paused", "blocked"},
        "deliver": {"active", "blocked"},
        "done":    {"active", "delivered"},
        "drop":    {"queued", "active", "paused", "blocked", "delivered"},
    }
    RESULT = {"start": "active", "pause": "paused", "block": "blocked", "deliver": "delivered", "done": "done", "drop": "dropped"}
    GIVEN = {"pause": {"branch": "main"}, "done": {"artifacts": [LANDED]}}

    def test_the_verbs_against_the_states(self):
        self.w.add("subject")
        got: dict[str, dict[str, bool]] = {verb: {} for verb in VERBS}
        for state in STATES:
            for verb, argv in VERBS.items():
                self.seed(state, **self.GIVEN.get(verb, {}))
                p = self.w.run(*argv)
                got[verb][state] = p.returncode == 0
                if p.returncode == 0:
                    # An accepted verb lands in its own state, except `deliver` on a job already delivered or done, which only adds
                    # evidence.
                    want = state if (verb, state) in (("deliver", "done"), ("deliver", "delivered")) else self.RESULT[verb]
                    self.assertEqual(self.state(), want, (verb, state, p.stderr))
                else:
                    self.assertEqual(self.state(), state, (verb, state, p.stderr))
        self.assertEqual(got, self.ACCEPTED)

    def test_the_cells_accepted_are_exactly_the_tables(self):
        accepted = {(verb, state) for verb, row in self.ACCEPTED.items() for state, yes in row.items() if yes}
        in_table = {(verb, state) for verb, states in self.TABLE.items() for state in states}
        self.assertEqual(accepted - in_table - {("deliver", "done"), ("deliver", "delivered")}, set(), "a cell outside the table")
        self.assertEqual(in_table - accepted, set(), "a row of the table that no verb makes")

    def test_a_closed_job_is_reopened_by_no_verb(self):
        # Against the other reading of the code, that `start` takes a job from any state: the terminal states are refused.
        self.w.add("subject")
        for state in ("done", "dropped"):
            for verb in ("start", "pause", "block", "drop"):
                self.seed(state)
                p = self.w.run(*VERBS[verb])
                self.assertEqual(p.returncode, 1, (state, verb, p.stdout))
                self.assertIn("a closed job is not reopened", p.stderr)
                self.assertEqual(self.state(), state)


class Leaving(Case):
    """The evidence `switch` asks of the job it leaves, by the state it is left in (rule 10 step 1): the row's needs asked again. The
    verbs now ask them when the state is entered (Findings), so a job in a state its row would not have let it into is forced here,
    as another writer of jobs.json could: one case per state; the positive control of a refusal is the sibling case that leaves the same
    state."""

    def left(self, job_id: str) -> subprocess.CompletedProcess:
        return self.leave(job_id)

    def delivered_then_merged(self, job_id: str, pr: str = LANDED) -> None:
        """A pull request delivered while it was open and merged since: the road to `done` the table has."""
        self.w.gh_says({pr: "OPEN"})
        self.ok("deliver", job_id, pr)
        self.w.gh_says({pr: "MERGED"})

    def test_done_is_left_on_a_merged_pull_request_and_refused_with_none(self):
        j1 = self.working("landed")
        self.delivered_then_merged(j1)
        self.ok("done", j1)
        p = self.left(j1)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn(f"left {j1}: done: {LANDED} merged", p.stdout)

    def test_done_with_no_evidence_is_refused_when_it_is_left(self):
        j1 = self.working("nothing to show")
        self.refused("done", j1, said="done needs evidence it landed")
        self.seed("done", j1)
        p = self.left(j1)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("done needs evidence it landed", p.stderr)
        self.assertEqual(self.state(j1), "done")

    def test_done_with_a_reason_is_left_as_housekeeping_but_not_when_it_names_an_unlanded_artifact(self):
        j1 = self.working("housekeeping")
        self.ok("done", j1, "--no-artifact", "moved a file")
        p = self.left(j1)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("no artifact: moved a file", p.stdout)
        j2 = self.working_after(j1, "named an artifact")
        closed = f"{jobs_world.GH_REPO}#7"
        self.w.gh_says({closed: "CLOSED"})
        self.seed("active", j2, artifacts=[closed])
        self.refused("done", j2, "--no-artifact", "a reason does not stand in for it", said="did not land on the default branch")
        self.seed("done", j2, artifacts=[closed], no_artifact="a reason does not stand in for it")
        p = self.leave(j2)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("did not land on the default branch", p.stderr)

    def test_done_on_an_open_pull_request_is_not_done(self):
        j1 = self.working("still open")
        self.ok("deliver", j1, OPEN_PR)
        self.refused("done", j1, said="is still open: the job is delivered, not done")
        self.seed("done", j1, artifacts=[OPEN_PR])
        p = self.left(j1)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("is still open: the job is delivered, not done", p.stderr)

    def test_delivered_is_left_on_an_open_pull_request_and_refused_once_it_merged(self):
        j1 = self.working("in review")
        self.ok("deliver", j1, OPEN_PR)
        p = self.left(j1)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn(f"left {j1}: delivered: {OPEN_PR} open", p.stdout)

    def test_delivered_on_a_merged_pull_request_is_refused_as_done(self):
        j1 = self.working("merged already")
        self.refused("deliver", j1, LANDED, said=f"{LANDED} is merged: the job is done, not delivered")
        self.seed("delivered", j1, artifacts=[LANDED])
        p = self.left(j1)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn(f"{LANDED} is merged: the job is done, not delivered", p.stderr)

    def test_blocked_is_left_on_a_checkable_blocker_and_on_an_owner_decision_not_on_free_text(self):
        j1 = self.working("waiting")
        self.ok("block", j1, "--on", "clock:2099-01-01T00:00Z")
        p = self.left(j1)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("blocked on clock:2099-01-01T00:00:00Z", p.stdout)

    def test_blocked_on_free_text_is_refused_and_an_owner_decision_is_not(self):
        j1 = self.working("words")
        self.refused("block", j1, "someone to look", said="is blocked on free text")
        self.seed("blocked", j1, blocked_on="someone to look")
        p = self.left(j1)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("is blocked on free text", p.stderr)
        self.seed("blocked", j1, blocked_on="owner: which of the two")
        p = self.w.switch(self.w.add("another"))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("blocked on owner: which of the two", p.stdout)

    def test_blocked_whose_blockers_all_cleared_is_refused_as_not_blocked(self):
        j1 = self.working("over")
        self.ok("block", j1, "--on", "clock:2099-01-01T00:00Z")
        self.seed("blocked", j1, blockers=["clock:2020-01-01T00:00:00Z"], blocked_on="clock:2020-01-01T00:00:00Z")
        p = self.left(j1)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("has cleared", p.stderr)

    def test_paused_is_left_with_its_branch_pushed_and_refused_without(self):
        j1 = self.working("set aside")
        wt = self.w.job(j1)["worktree"]
        # A commit of its own: a branch the default branch already holds is landed, which is evidence by itself.
        subprocess.run(["git", "-C", wt, "commit", "-q", "--allow-empty", "-m", "work"], check=True, env=git_env())
        self.refused("pause", j1, "later", cwd=wt, said="is not on origin: push it")
        self.seed("paused", j1, reason="later")
        p = self.left(j1)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("is not on origin: push it", p.stderr)
        subprocess.run(["git", "-C", wt, "push", "-q", "origin", self.w.job(j1)["branch"]], check=True, env=git_env())
        p = self.w.switch(self.w.jobs()[-1]["id"])
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("pushed", p.stdout)

    def test_dropped_is_left_with_a_reason(self):
        j1 = self.working("not wanted")
        self.ok("drop", j1, "superseded")
        p = self.left(j1)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn(f"left {j1}: dropped: dropped: superseded", p.stdout)

    def test_an_active_job_is_not_left_by_switch(self):
        j1 = self.working("still going")
        p = self.left(j1)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn(f"{j1} is still active", p.stderr)

    def test_an_uncommitted_copy_keeps_a_finished_job(self):
        j1 = self.working("dirty")
        self.ok("deliver", j1, OPEN_PR)
        with open(os.path.join(self.w.job(j1)["worktree"], "scratch.txt"), "w", encoding="utf-8") as fh:
            fh.write("x")
        p = self.left(j1)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("has uncommitted changes", p.stderr)


class Findings(Case):
    """Where the code made a transition outside rule 14's table, or one without what the row needs (F1..F8 of j100; F9 in the pool
    suite, F10 in the blockers', F11 in the intake's). j100 pinned each as a case holding the answer of the day and an expectedFailure
    case holding the table's; the owner (tools/fabric/work, tools/fabric/jobsparts/needs.py) makes the second green, and the first is
    gone with the behaviour it pinned."""

    # F1 ── R9: done from active or delivered, on the done test or a recorded --no-artifact reason.
    def test_f1_done_without_an_artifact_or_a_reason_is_refused(self):
        j1 = self.working("never delivered")
        self.refused("done", j1, said="done needs evidence it landed")
        self.assertEqual(self.state(j1), "active")

    def test_f1_done_is_taken_from_active_and_delivered_only(self):
        self.w.add("a")
        self.refused("done", "j1", "--no-artifact", "x", said="j1 is queued; done takes a job that is active or delivered")
        self.assertEqual(self.state(), "queued")

    # F2 ── R7: deliver from active or blocked, with "an artifact that is open".
    def test_f2_deliver_is_taken_from_active_and_blocked_only(self):
        self.w.add("a")
        self.refused("deliver", "j1", OPEN_PR, said="j1 is queued; deliver takes a job that is active or blocked")
        self.assertEqual(self.w.job("j1")["artifacts"], [])

    def test_f2_deliver_needs_an_artifact_that_is_open_not_one_already_merged(self):
        self.w.add("a")
        self.ok("start", "j1")
        self.refused("deliver", "j1", LANDED, said="is merged: the job is done, not delivered")
        self.refused("deliver", "j1", "not-an-artifact", said="delivered needs an artifact that is open")
        self.assertEqual((self.state(), self.w.job("j1")["artifacts"]), ("active", []))
        self.ok("deliver", "j1", OPEN_PR)         # the positive control: the same job with an open one
        self.assertEqual(self.state(), "delivered")

    # F3 ── R6: block from queued, active, paused or blocked, on "a checkable blocker or a named owner's decision".
    def test_f3_block_does_not_take_a_delivered_job(self):
        self.w.add("a")
        self.seed("delivered", "j1", artifacts=[OPEN_PR])
        self.refused("block", "j1", "owner: which of the two", said="j1 is delivered; block takes a job that is")
        self.assertEqual(self.state(), "delivered")

    def test_f3_block_on_free_text_is_refused_where_leaving_would_refuse_it(self):
        self.w.add("a")
        self.refused("block", "j1", "someone to look", said="is blocked on free text")
        self.assertEqual(self.state(), "queued")
        self.ok("block", "j1", "owner: someone to look")    # the positive control: a named owner's decision
        self.assertEqual(self.state(), "blocked")

    # F4 ── R4: into active from queued, paused, blocked or delivered, "from blocked by switch, every blocker cleared".
    def test_f4_start_does_not_take_a_job_whose_checkable_blocker_still_waits(self):
        self.w.add("a")
        self.ok("block", "j1", "--on", "clock:2099-01-01T00:00Z")
        self.refused("start", "j1", said="is still blocked")
        self.assertEqual(self.state(), "blocked")

    def test_f4_switch_by_id_does_not_take_a_job_whose_checkable_blocker_still_waits(self):
        self.w.add("a")
        self.ok("block", "j1", "--on", "clock:2099-01-01T00:00Z")
        p = self.w.switch("j1")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("is still blocked", p.stderr)
        self.assertEqual(self.state(), "blocked")

    def over(self) -> None:
        self.w.add("a")
        self.seed("blocked", "j1", blockers=["clock:2020-01-01T00:00:00Z"], blocked_on="clock:2020-01-01T00:00:00Z")

    def test_f4_a_wait_that_is_over_is_taken_by_start(self):
        self.over()
        self.ok("start", "j1")
        self.assertEqual(self.state(), "active")

    def test_f4_a_wait_that_is_over_is_taken_by_switch_by_id(self):
        self.over()
        p = self.w.switch("j1")
        self.assertEqual((p.returncode, self.state()), (0, "active"), p.stdout + p.stderr)

    def test_f4_start_and_switch_by_id_agree_on_a_delivered_job(self):
        self.w.add("a")
        self.seed("delivered", "j1", artifacts=[OPEN_PR])
        by_switch = self.w.switch("j1").returncode
        self.assertEqual(by_switch, 0)
        self.seed("delivered", "j1", artifacts=[OPEN_PR])
        self.assertEqual(self.w.run("start", "j1").returncode, by_switch)

    def test_f4_start_is_not_taken_from_active(self):
        self.w.add("a")
        self.ok("start", "j1")
        self.refused("start", "j1", said="j1 is active; start takes a job that is queued, paused, blocked or delivered")
        self.assertEqual([e["state"] for e in self.w.job("j1")["log"]], ["queued", "active"])

    # F5 ── R5: pause "the branch pushed".
    def test_f5_pause_needs_the_branch_pushed(self):
        j1 = self.working("unpushed")
        wt = self.w.job(j1)["worktree"]
        # A commit of its own: a branch the default branch already holds is landed, which settle counts as pushed.
        subprocess.run(["git", "-C", wt, "commit", "-q", "--allow-empty", "-m", "work"], check=True, env=git_env())
        self.refused("pause", j1, "later", cwd=wt, said="is not on origin: push it")
        self.assertEqual(self.state(j1), "active")
        subprocess.run(["git", "-C", wt, "push", "-q", "origin", self.w.job(j1)["branch"]], check=True, env=git_env())
        self.ok("pause", j1, "later", cwd=wt)         # the positive control: the same branch, pushed
        self.assertEqual(self.state(j1), "paused")

    def test_f5_pause_needs_a_branch_to_be_pushed(self):
        self.w.add("no branch")
        self.ok("start", "j1")
        self.refused("pause", "j1", "later", said="a paused job names the branch holding its work")
        self.assertEqual(self.state(), "active")

    # F6 ── R10: drop "a reason; a REQUEST it came from answered".
    def test_f6_drop_needs_a_reason(self):
        self.w.add("a")
        self.refused("drop", "j1", "   ", said="drop needs a reason")
        self.assertEqual(self.state(), "queued")

    def from_a_request(self, title: str = "from a request") -> None:
        self.w.add(title)
        self.w.put(lambda doc: doc["jobs"][-1].update(source={"kind": "request", "message_id": RID, "from": "h/u", "seq": 1}))

    def test_f6_drop_needs_the_request_it_came_from_answered(self):
        self.from_a_request()
        self.refused("drop", "j1", "no longer needed", said=f"REQUEST {RID}, which this login has not answered")
        self.assertEqual(self.state(), "queued")
        self.w.answer(RID)
        self.ok("drop", "j1", "no longer needed")     # the positive control: the same drop once the REQUEST is answered
        self.assertEqual(self.state(), "dropped")

    # F7 ── R8 and R9 both name "rule 10's done test", which sweep and settle each implemented. A bare commit sha: settle took it as
    # landed evidence, sweep never read it (a sha counted only in an artifact that named the job's own project).
    def sha_world(self) -> str:
        sha = subprocess.run(["git", "-C", self.w.alpha, "rev-parse", "HEAD"], check=True, capture_output=True, text=True,
                             env=git_env()).stdout.strip()
        j1 = self.working("sha")
        self.seed("delivered", j1, artifacts=[sha])
        return j1

    def test_f7_sweep_closes_a_job_whose_bare_sha_settle_accepts_as_landed(self):
        j1 = self.sha_world()
        self.ok("sweep")
        self.assertEqual(self.state(j1), "done")

    def test_f7_a_bare_sha_that_is_no_commit_here_closes_nothing(self):
        j1 = self.working("sha")
        self.seed("delivered", j1, artifacts=["deadbee"])
        self.assertIn("no artifact names a pull request, a commit or a branch it can resolve", self.ok("sweep").stdout)
        self.assertEqual(self.state(j1), "delivered")

    # F8 ── "<project> #N": sweep resolved it through the registry to that project's repository; settle read the #N in the job's own
    # repository. A job sweep closed on landed evidence then could not be left by switch.
    def project_pr_world(self) -> str:
        self.w.gh_says({f"{OTHER_REPO}#4": "OPEN"})
        j1 = self.working("other project's pull request")
        self.ok("deliver", j1, "other-proj #4")
        self.w.gh_says({f"{OTHER_REPO}#4": "MERGED"})
        return j1

    def test_f8_a_job_sweep_closed_on_landed_evidence_can_be_left(self):
        j1 = self.project_pr_world()
        self.assertIn(f"closed ({OTHER_REPO}#4 merged)", self.ok("sweep").stdout)
        p = self.leave(j1)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_f8_done_and_sweep_read_the_project_reference_alike(self):
        j1 = self.project_pr_world()
        self.ok("done", j1)
        p = self.leave(j1)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn(f"{OTHER_REPO}#4 merged", p.stdout)


if __name__ == "__main__":
    unittest.main()
