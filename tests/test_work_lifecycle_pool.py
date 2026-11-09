#!/usr/bin/env python3
"""The pool's half of the work lifecycle, pinned against agent-fabric ADR-037 rule 14 (A 2026-11-08), rows R1, R2 and R2b (rule 14 as corrected at eee64007):

  R1   -> open in a role's pool          the holder's control agent, on a signed pool-add       needs role, title, project, priority
  R2   open -> claimed there             the holder's control agent, on pool-claim              needs the claimant's reported binding to hold
                                                                                                 the role; no other claimant
  R2b  -> queued                         the claimant's own fabric-jobs pool-claim, on the      needs the pool's job, by generation and id
                                         holder's `claimed` answer (rule 1: no other writer of its list)

The holder's side is tools/fabric/control/pool.py called as agentd calls it (its own suite, tests/test_control_pool.py, holds the port's
oracle; this one holds what a job's lifecycle reads of it). The claimant's side is what `fabric-jobs pool-claim` does with the holder's
answer: the same functions, in process, writing the scratch list the CLI then reads (tests/work_lifecycle_world.py). The relay between
them is not exercised here; tests/test_jobs.py runs the verb against a fake holder.

The pool's own end is rows R2c and R2d (A 2026-11-09; finding F9 of j100): the holder's control agent closes a claim whose job the
claimant's fresh state record reports done or dropped, and opens it again a day after the claim when that record reports its claims and
holds none for it; a record that is missing, stale, unreadable or claims-less is unknown and moves nothing. The claim a closed job keeps is
refused to every claim. tools/fabric/work/claims.py is the owner; control/pool.py `reconcile` is the holder's tick."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from git_env import scrub_process_env  # noqa: E402 — tests/, this script's own directory
from instance_fixtures import own_instance_tree  # noqa: E402
scrub_process_env()
own_instance_tree()
from control import pool as cp  # noqa: E402
from control import sessions  # noqa: E402
from work_lifecycle_world import World  # noqa: E402

HOLDER = "h/user"
CLAIMANT = "h/python-dev-04"
OTHER = "h/python-dev-05"
KNOWN = {"python-dev", "web-dev"}


def roles(mapping):
    return lambda address: {"role": mapping[address]} if address in mapping else {"error": f"no state record from {address}"}


class Pool(unittest.TestCase):
    def setUp(self) -> None:
        self.w = World()
        self.addCleanup(self.w.close)
        self.file = os.path.join(self.w.tmp, "pool.json")
        self.bound = roles({CLAIMANT: "python-dev", OTHER: "python-dev"})
        self.clock = iter(f"2026-11-08T00:00:{n:02d}Z" for n in range(60))

    def add(self, **args):
        return cp.pool_add({"from": HOLDER, "to": [HOLDER], "args": {"role": "python-dev", "title": "a job", **args}},
                           me=HOLDER, holder=HOLDER, file=self.file, known=KNOWN, now=lambda: next(self.clock))

    def claim(self, pid: str, sender: str = CLAIMANT, role_of=None):
        return cp.pool_claim({"from": sender, "args": {"id": pid}}, me=HOLDER, holder=HOLDER, file=self.file,
                             role_of=role_of or self.bound, now=lambda: next(self.clock))

    def listed(self, role: str = "python-dev"):
        return cp.pool_list({"args": {"role": role}}, me=HOLDER, holder=HOLDER, file=self.file)

    def stored(self, pid: str) -> dict:
        return next(j for j in cp.read_pool(self.file)["jobs"] if j["id"] == pid)

    def on_the_claimants_list(self, answer: dict, *, again: bool = False, working_copy=None):
        """The claimant's half of pool-claim: the holder's answer, held to its shape, onto the list under the list's lock."""
        with mock.patch.dict(os.environ, self.w.env, clear=True):
            spec = importlib.util.spec_from_file_location("jobs_in_process", os.path.join(ROOT, "tools", "fabric", "jobs.py"))
            jobs = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(jobs)
            cwd = os.getcwd()
            os.chdir(self.w.alpha)
            try:
                job = jobs.claimed_job(answer, answer["job"]["id"])
                return jobs.mutate(lambda doc: jobs.pool_job(doc, job, HOLDER, again=answer.get("again") is True,
                                                             generation=jobs.claim_generation(answer),
                                                             working_copy=working_copy))
            finally:
                os.chdir(cwd)

    # ── R1 ──────────────────────────────────────────────────────────────────────────────────────────────────────────

    def test_r1_pool_add_opens_a_job_for_a_role_with_its_priority_and_no_claimant(self):
        said = self.add(title="  port   the thing ", priority="high", project="fixture-proj")
        self.assertEqual(said["status"], "added", said)
        self.assertEqual([said["job"][k] for k in ("id", "role", "title", "priority", "project")],
                         ["p1", "python-dev", "port the thing", "high", "fixture-proj"])
        self.assertIsNone(self.stored("p1")["claimed"])
        self.assertEqual([j["id"] for j in self.listed()["jobs"]], ["p1"])

    def test_r1_a_pool_add_is_the_holders_alone_and_for_a_role_of_the_catalogue(self):
        who = cp.pool_add({"from": HOLDER, "to": ["h/other"], "args": {"role": "python-dev", "title": "x"}},
                          me="h/other", holder=HOLDER, file=self.file, known=KNOWN)
        self.assertIn("this account does not hold the pool", who["reason"])
        self.assertIn("no role nobody in the catalogue", self.add(role="nobody")["reason"])
        self.assertFalse(os.path.exists(self.file), "a refused add writes nothing")

    def test_r1_the_pool_lists_a_roles_open_jobs_highest_priority_first_then_oldest(self):
        self.add(title="old normal")
        self.add(title="not mine", role="web-dev")
        self.add(title="low", priority="low")
        self.add(title="high", priority="high")
        self.assertEqual([j["title"] for j in self.listed()["jobs"]], ["high", "old normal", "low"])

    # ── R2 ──────────────────────────────────────────────────────────────────────────────────────────────────────────

    def test_r2_a_claim_marks_the_pool_job_claimed_and_leaves_the_open_list(self):
        self.add()
        said = self.claim("p1")
        self.assertEqual(said["status"], "claimed", said)
        self.assertEqual(self.stored("p1")["claimed"], {"by": CLAIMANT, "at": "2026-11-08T00:00:01Z"})
        self.assertEqual(self.listed()["jobs"], [])

    def test_r2b_the_claimant_gets_a_queued_job_with_the_pool_as_its_source(self):
        self.add(priority="high", project="fixture-proj")
        said = self.claim("p1")
        job = self.on_the_claimants_list(said)[0]
        self.assertEqual((job["state"], job["priority"], job["project"], job["working_copy"]), ("queued", "high", "fixture-proj", None))
        # R4 needs a working copy: a pool job of a project this login has no copy of cannot be started until one is named.
        self.assertEqual(self.w.run("start", job["id"]).returncode, 1)
        self.w.put(lambda doc: doc["jobs"][0].update(working_copy=self.w.alpha))
        self.assertEqual(job["source"], {"kind": "pool", "pool_id": "p1", "from": HOLDER, "generation": said["generation"]})
        # …and from here it is a job like any other: the verbs and the table take it from queued.
        self.assertEqual(self.w.run("start", job["id"]).returncode, 0)
        self.assertEqual(self.w.job(job["id"])["state"], "active")

    def test_r2b_one_claim_is_one_job_however_many_answers_reach_the_claimant(self):
        self.add()
        first = self.claim("p1")
        again = self.claim("p1")
        self.assertTrue(again["again"] and "again" not in first)
        a = self.on_the_claimants_list(first)
        b = self.on_the_claimants_list(again, again=True)
        self.assertEqual((a[1], b[1], a[0]["id"], b[0]["id"]), (True, False, "j1", "j1"))
        self.assertEqual(len(self.w.jobs()), 1)

    def test_r2_a_job_has_one_claimant(self):
        self.add()
        self.claim("p1")
        said = self.claim("p1", sender=OTHER)
        self.assertEqual(said["status"], "refused")
        self.assertIn(f"p1 is claimed by {CLAIMANT}", said["reason"])
        self.assertEqual(self.stored("p1")["claimed"]["by"], CLAIMANT)

    def test_r2_the_claimants_binding_must_hold_the_role_as_its_control_agent_reports_it(self):
        self.add()
        wrong = self.claim("p1", role_of=roles({CLAIMANT: "web-dev"}))
        self.assertIn("holds web-dev, as its control agent reports it; p1 is for python-dev", wrong["reason"])
        unknown = self.claim("p1", role_of=roles({}))
        self.assertIn("no state record from", unknown["reason"])
        self.assertIsNone(self.stored("p1")["claimed"], "a binding that is unknown or wrong claims nothing")

    def test_r2_only_the_holder_answers_and_an_unknown_job_is_refused(self):
        self.add()
        elsewhere = cp.pool_claim({"from": CLAIMANT, "args": {"id": "p1"}}, me="h/other", holder=HOLDER, file=self.file, role_of=self.bound)
        self.assertIn("this account does not hold the pool", elsewhere["reason"])
        self.assertIn("no pool job p9", self.claim("p9")["reason"])
        self.assertIn("pool-claim takes { id }", self.claim("job 1")["reason"])

    def test_r2_a_pool_that_cannot_be_read_is_never_an_empty_one(self):
        self.add()
        with open(self.file, "w", encoding="utf-8") as fh:
            fh.write("not json")
        self.assertEqual(self.claim("p1")["reason"], "the pool file is not JSON")
        self.assertEqual(self.listed()["reason"], "the pool file is not JSON")

    # ── the pool's own end (R2c, R2d) ───────────────────────────────────────────────────────────────────────────────

    DAY_LATER = "2026-11-09T00:00:30Z"          # a day and thirty seconds after the first claim of these cases (00:00:01 on the 8th)

    def finish_claimed(self, how: str) -> dict:
        self.add()
        job = self.on_the_claimants_list(self.claim("p1"))[0]
        if how == "dropped":
            self.assertEqual(self.w.run("drop", job["id"], "not for me").returncode, 0)
        else:
            self.assertEqual(self.w.run("start", job["id"]).returncode, 0)
            self.assertEqual(self.w.run("done", job["id"], "--no-artifact", "housekeeping").returncode, 0)
        return job

    def record(self, **extra) -> dict:
        """The claimant's state record as its control agent posts it, built from the real list the CLI wrote."""
        return sessions.state_record(CLAIMANT, {"sessions": [], "claims": sessions.claims(self.w.path), **extra})

    def reconcile(self, record, at: str = "2026-11-08T12:00:00Z", error: str | None = None) -> dict:
        said = {"record": record} if record is not None else {"error": error or f"no state record from {CLAIMANT} in the last 20 min"}
        return cp.reconcile(me=HOLDER, holder=HOLDER, file=self.file, state_of=lambda address: said, now=lambda: at)

    def test_f9_a_claim_whose_job_ended_is_closed_with_when_and_how(self):
        for how in ("dropped", "done"):
            with self.subTest(how):
                self.finish_claimed(how)
                claimed_at = self.stored("p1")["claimed"]["at"]
                said = self.reconcile(self.record(), at="2026-11-08T12:00:00Z")
                self.assertEqual((said["status"], said["closed"], said["reopened"]), ("ok", ["p1"], []))
                self.assertEqual(self.stored("p1")["claimed"], {"by": CLAIMANT, "at": claimed_at,
                                                                "closed": {"at": "2026-11-08T12:00:00Z", "how": how}})
                self.assertEqual(self.listed()["jobs"], [])
                os.unlink(self.file)

    def test_f9_a_closed_claim_is_refused_to_every_claim_its_claimants_included(self):
        self.finish_claimed("done")
        self.reconcile(self.record())
        for sender in (CLAIMANT, OTHER):
            said = self.claim("p1", sender=sender)
            self.assertEqual(said["status"], "refused", sender)
            self.assertIn("p1 is closed (done at 2026-11-08T12:00:00Z)", said["reason"])
        self.assertEqual(self.reconcile(self.record())["closed"], [], "closing is once; the claim is kept as it closed")
        self.assertEqual(self.stored("p1")["claimed"]["closed"]["at"], "2026-11-08T12:00:00Z")

    def test_f9_a_claim_nobody_holds_is_opened_again_a_day_after_it_was_made(self):
        # The holder recorded the claim; the claimant never listed a job (its answer was lost): the record reports claims, none is this.
        self.add()
        self.claim("p1")
        self.assertEqual(sessions.claims(self.w.path), [], "the claimant's list holds no claim, and says so")
        self.assertEqual(self.reconcile(self.record(), at="2026-11-08T23:59:59Z")["reopened"], [], "not yet a day")
        said = self.reconcile(self.record(), at=self.DAY_LATER)
        self.assertEqual((said["status"], said["reopened"], said["closed"]), ("ok", ["p1"], []))
        self.assertIsNone(self.stored("p1")["claimed"])
        self.assertEqual([j["id"] for j in self.listed()["jobs"]], ["p1"])
        first = self.claim("p1", sender=OTHER)
        self.assertEqual((first["status"], "again" in first), ("claimed", False), "another claims it afresh")
        self.assertEqual(self.claim("p1", sender=OTHER)["again"], True, "and a repeat of that claim is a repeat")

    def test_f9_a_claim_still_held_is_not_opened_again(self):
        self.add()
        job = self.on_the_claimants_list(self.claim("p1"))[0]
        self.assertEqual(self.reconcile(self.record(), at=self.DAY_LATER), {"status": "ok", "closed": [], "reopened": [], "unknown": {}})
        self.assertEqual(self.w.job(job["id"])["state"], "queued")
        self.assertEqual(self.stored("p1")["claimed"]["by"], CLAIMANT)

    def test_f9_the_claim_is_read_by_the_pools_generation_and_id(self):
        self.finish_claimed("done")
        generation = cp.read_pool(self.file)["generation"]
        other_pool = [{"generation": "0" * 32, "id": "p1", "state": "done"}, {"generation": generation, "id": "p2", "state": "done"}]
        said = self.reconcile({**self.record(), "claims": other_pool}, at=self.DAY_LATER)
        self.assertEqual((said["closed"], said["reopened"]), ([], ["p1"]), "a claim of another pool or job is not this one's")

    def test_f9_a_list_from_before_generations_might_hold_it_and_opens_nothing(self):
        self.add()
        self.claim("p1")
        legacy = {**self.record(), "claims": [{"id": "p1", "state": "active"}]}
        self.assertEqual(self.reconcile(legacy, at=self.DAY_LATER)["reopened"], [])

    def test_f9_what_is_not_known_changes_nothing(self):
        self.finish_claimed("dropped")
        before = open(self.file, encoding="utf-8").read()
        no_claims = {k: v for k, v in self.record().items() if k != "claims"}
        for label, record, error in (("no record", None, None), ("stale or unreadable stream", None, "the state stream could not be read (down)"),
                                     ("a record that reports no claims", no_claims, None),
                                     ("claims that are not a list", {**self.record(), "claims": "p1"}, None)):
            said = self.reconcile(record, at=self.DAY_LATER, error=error)
            self.assertEqual((said["status"], said["closed"], said["reopened"]), ("ok", [], []), label)
            self.assertEqual(open(self.file, encoding="utf-8").read(), before, label)
        self.assertIn("p1", self.reconcile(None, at=self.DAY_LATER)["unknown"])

    def test_f9_only_the_holder_reconciles_and_a_pool_that_cannot_be_read_is_said(self):
        self.add()
        said = cp.reconcile(me=OTHER, holder=HOLDER, file=self.file, state_of=lambda a: {"error": "x"})
        self.assertEqual(said["status"], "refused")
        with open(self.file, "w", encoding="utf-8") as fh:
            fh.write("not json")
        self.assertEqual(self.reconcile(None)["reason"], "the pool file is not JSON")

    def test_f9_the_claimants_list_says_its_claims_by_generation_and_id_with_the_state_of_each(self):
        self.finish_claimed("dropped")
        generation = cp.read_pool(self.file)["generation"]
        self.assertEqual(sessions.claims(self.w.path), [{"generation": generation, "id": "p1", "state": "dropped"}])
        self.assertEqual(self.record()["claims"], [{"generation": generation, "id": "p1", "state": "dropped"}])

    def test_f9_a_list_that_cannot_be_read_or_holds_too_many_says_nothing(self):
        os.makedirs(os.path.dirname(self.w.path), exist_ok=True)
        self.assertEqual(sessions.claims(os.path.join(self.w.tmp, "none.json")), [], "no list yet holds no claim")
        self.assertIsNone(sessions.claims(None))
        with open(self.w.path, "w", encoding="utf-8") as fh:
            fh.write("{")
        self.assertIsNone(sessions.claims(self.w.path))
        self.assertNotIn("claims", self.record(), "unknown is a record without the key, never an empty list")
        many = [{"id": f"j{n}", "state": "queued", "source": {"kind": "pool", "pool_id": f"p{n}", "generation": "a" * 32}}
                for n in range(1, sessions.CLAIMS_MAX + 2)]
        with open(self.w.path, "w", encoding="utf-8") as fh:
            json.dump({"jobs": many}, fh)
        self.assertIsNone(sessions.claims(self.w.path), "more claims held than a record carries is unknown, not the first of them")
        ended = [{**j, "state": "done"} for j in many]
        with open(self.w.path, "w", encoding="utf-8") as fh:
            json.dump({"jobs": ended}, fh)
        self.assertEqual(len(sessions.claims(self.w.path)), sessions.CLAIMS_MAX, "ended claims are cut to fit; they are closed already")

    def test_f9_a_claim_that_ended_since_the_last_tick_is_never_the_one_cut(self):
        os.makedirs(os.path.dirname(self.w.path), exist_ok=True)
        gen = "a" * 32
        jobs = [{"id": f"j{n}", "state": "done", "updated": f"2026-11-0{1 + n % 5}T00:00:00Z",
                 "source": {"kind": "pool", "pool_id": f"p{n}", "generation": gen}} for n in range(1, sessions.CLAIMS_MAX + 7)]
        jobs[-1] = {**jobs[-1], "updated": "2026-11-09T00:00:00Z"}        # the last of the list, ended last: a list-order cut takes it first
        with open(self.w.path, "w", encoding="utf-8") as fh:
            json.dump({"jobs": jobs}, fh)
        told = sessions.claims(self.w.path)
        self.assertEqual(len(told), sessions.CLAIMS_MAX)
        self.assertIn({"generation": gen, "id": f"p{sessions.CLAIMS_MAX + 6}", "state": "done"}, told, "the newest end is told, whatever its place in the list")
        self.assertTrue(all("_updated" not in r for r in told))

    def test_f9_the_stream_is_read_outside_the_pools_lock(self):
        self.finish_claimed("done")
        held = []

        def state_of(address):
            try:
                with cp._locked(self.file):         # a claim or an add arriving meanwhile takes it
                    held.append(False)
            except cp.PoolError:
                held.append(True)
            return {"record": self.record()}
        with mock.patch.object(cp, "POOL_LOCK_WAIT_S", 0.1):
            said = cp.reconcile(me=HOLDER, holder=HOLDER, file=self.file, state_of=state_of, now=lambda: "2026-11-08T12:00:00Z")
        self.assertEqual((held, said["closed"]), ([False], ["p1"]))

    def test_f9_a_job_of_the_claimants_own_is_no_claim(self):
        os.makedirs(os.path.dirname(self.w.path), exist_ok=True)
        with open(self.w.path, "w", encoding="utf-8") as fh:
            json.dump({"jobs": [{"id": "j1", "state": "queued", "source": {"kind": "self"}},
                                {"id": "j2", "state": "queued", "source": {"kind": "pool", "pool_id": "not an id"}}]}, fh)
        self.assertEqual(sessions.claims(self.w.path), [])


if __name__ == "__main__":
    unittest.main()
