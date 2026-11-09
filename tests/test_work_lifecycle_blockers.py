#!/usr/bin/env python3
"""The blockers' half of the work lifecycle, pinned against agent-fabric ADR-037 rule 14 (A 2026-11-08), rows R4 (from `blocked` by
`switch`, every blocker cleared) and R6 (`block` needs a blocker: checkable, rule 8, or a named owner's decision) with rule 8's cache:
<state dir>/jobs-blockers.json, a blocker checked at most every ten minutes, a cleared one never again.

The cache is a second place that says whether a job may move: the job stays `blocked` in jobs.json whatever the cache says, and
the cache's `cleared` is read by `list`, `switch` and the control agent's state record. These cases hold the three readings
together: the list's state, the cache's flag and what the control agent publishes (tools/fabric/control/sessions.py waits_on).
The `job:<login>/j<n>` blocker reads a peer's board through fabric-ctl and the `request:` blocker the journal; neither is
reachable without a relay, so their cache entries are seeded (the checks themselves are tests/test_jobs_blockers.py's). Run as
the command against the world of tests/work_lifecycle_world.py."""
from __future__ import annotations

import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from git_env import scrub_process_env  # noqa: E402 — tests/, this script's own directory
from instance_fixtures import own_instance_tree  # noqa: E402
scrub_process_env()
own_instance_tree()
from control import sessions  # noqa: E402
from work_lifecycle_world import World  # noqa: E402

RID = "01a11a18-4728-7d8b-afd9-0edb2d30a59c"
PR = "o/r#5"


class Blockers(unittest.TestCase):
    def setUp(self) -> None:
        self.w = World()
        self.addCleanup(self.w.close)

    def ok(self, *argv: str, **kw):
        p = self.w.run(*argv, **kw)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p

    @property
    def cache_file(self) -> str:
        return os.path.join(os.path.dirname(self.w.path), "jobs-blockers.json")

    def cache(self) -> dict:
        with open(self.cache_file, encoding="utf-8") as fh:
            return json.load(fh)

    def seed_cache(self, spec: str, state: str, detail: str = "") -> None:
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        try:
            doc = self.cache()
        except OSError:
            doc = {}
        doc[spec] = {"state": state, "detail": detail, "checked_at": time.time()}
        with open(self.cache_file, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

    def listed(self, *flags: str) -> dict:
        return {j["id"]: j for j in json.loads(self.ok("list", "--json", *flags).stdout)}

    # ── R6: block, and what it records ──────────────────────────────────────────────────────────────────────────────

    def test_r6_a_pull_request_blocker_is_waiting_while_open_cleared_once_merged_and_unknown_when_gh_cannot_say(self):
        self.w.add("a")
        for gh, want in (({PR: "OPEN"}, "waiting"), ({PR: "MERGED"}, "cleared"), ({PR: "CLOSED"}, "cleared"), ({}, "unknown")):
            with self.subTest(gh):
                self.w.gh_says(gh)
                self.ok("block", "j1", "--on", f"pr:{PR}")        # blocking again forgets the answer a former wait left
                (job,) = self.listed().values()
                self.assertEqual([b["state"] for b in job["blockers"]], [want], job)
                self.assertEqual(job["cleared"], {"cleared": True, "waiting": False, "unknown": None}[want])

    def test_r6_a_cleared_blocker_is_never_checked_again(self):
        self.w.add("a")
        self.w.gh_says({PR: "MERGED"})
        self.ok("block", "j1", "--on", f"pr:{PR}")
        self.w.gh_says({PR: "OPEN"})
        # Past the ten minutes a waiting blocker would be asked again: only `cleared` keeps it from being.
        doc = self.cache()
        doc[f"pr:{PR}"]["checked_at"] = time.time() - 3600
        with open(self.cache_file, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        self.assertEqual(self.listed()["j1"]["cleared"], True)

    def test_r6_a_waiting_blocker_is_not_asked_again_inside_ten_minutes(self):
        self.w.add("a")
        self.w.gh_says({PR: "OPEN"})
        self.ok("block", "j1", "--on", f"pr:{PR}")
        self.w.gh_says({PR: "MERGED"})
        self.assertEqual(self.listed()["j1"]["cleared"], False, "inside the cache's ten minutes")
        self.assertEqual(self.listed("--stored")["j1"]["cleared"], False, "--stored and --cached read the cache and check nothing")

    def test_r6_every_blocker_must_clear_one_still_waiting_keeps_the_job_blocked(self):
        self.w.add("a")
        self.w.gh_says({PR: "MERGED"})
        self.ok("block", "j1", "--on", f"pr:{PR}", "--on", "clock:2099-01-01T00:00Z")
        job = self.listed()["j1"]
        self.assertEqual(([b["state"] for b in job["blockers"]], job["cleared"]), (["cleared", "waiting"], False))

    # ── R4 from blocked: who moves a job whose wait is over ─────────────────────────────────────────────────────────

    def cleared_job(self) -> None:
        self.w.add("a")
        self.ok("block", "j1", "--on", "clock:2099-01-01T00:00Z")
        self.w.put(lambda doc: doc["jobs"][0].update(blockers=["clock:2020-01-01T00:00:00Z"], blocked_on="clock:2020-01-01T00:00:00Z"))

    def test_r4_a_job_whose_blockers_cleared_stays_blocked_until_start_or_switch_moves_it(self):
        self.cleared_job()
        job = self.listed()["j1"]
        self.assertEqual((job["state"], job["cleared"]), ("blocked", True))
        for quiet in (("sweep",), ("list",), ("tidy", "--dry-run")):
            self.ok(*quiet)
        self.assertEqual(self.w.job("j1")["state"], "blocked")
        self.assertIn("blocker cleared", self.ok("list").stdout)

    def test_r4_the_clock_is_evaluated_on_every_look_even_when_nothing_is_checked(self):
        self.w.add("a")
        self.ok("block", "j1", "--on", "clock:2099-01-01T00:00Z")
        self.w.put(lambda doc: doc["jobs"][0].update(blockers=["clock:2020-01-01T00:00:00Z"]))
        self.assertEqual(self.listed("--cached")["j1"]["cleared"], True)
        self.assertEqual(self.listed("--stored")["j1"]["cleared"], True)

    def test_r4_a_job_whose_blocker_is_unknown_is_not_taken_by_next(self):
        self.w.add("a")
        self.w.gh_says({})
        self.ok("block", "j1", "--on", f"pr:{PR}")
        p = self.w.switch()
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertEqual(self.w.job("j1")["state"], "blocked")

    # ── what the control agent publishes of a wait (rule 8) ────────────────────────────────────────────────────────

    def test_r6_a_blocked_job_waiting_on_a_request_is_published_in_the_state_record(self):
        self.w.add("a")
        self.ok("block", "j1", "--on-request", RID)
        self.assertEqual(sessions.waits_on(self.w.path), [RID])
        self.ok("drop", "j1", "no longer needed")
        self.assertEqual(sessions.waits_on(self.w.path), [], "leaving blocked drops the wait")
        self.assertNotIn("waits_on", self.w.job("j1"))

    def waiting_on_an_answered_request(self) -> None:
        self.w.add("a")
        self.ok("block", "j1", "--on-request", RID)
        self.seed_cache(f"request:{RID}", "cleared", "answered")

    def test_f10_a_wait_that_cleared_is_no_longer_published(self):
        # rule 8: the job that request asked for ranks blocking *while* this one waits; the cache says the wait is over, and the
        # state record is read from jobs.json alone, so it used to go on saying so until a start or switch took the job.
        self.waiting_on_an_answered_request()
        self.assertEqual(sessions.waits_on(self.w.path), [])
        job = self.listed("--cached")["j1"]
        self.assertEqual((job["state"], job["cleared"], job["waits_on"]), ("blocked", True, RID), "the job itself stays blocked until moved on")

    def test_f10_a_wait_the_cache_does_not_know_over_is_published(self):
        self.w.add("a")
        self.ok("block", "j1", "--on-request", RID)
        self.assertEqual(sessions.waits_on(self.w.path), [RID], "the cache says waiting")
        self.seed_cache(f"request:{RID}", "unknown", "journal unreadable")
        self.assertEqual(sessions.waits_on(self.w.path), [RID], "unknown is not cleared")
        os.unlink(self.cache_file)
        self.assertEqual(sessions.waits_on(self.w.path), [RID], "no cache is not a cleared wait")


if __name__ == "__main__":
    unittest.main()
