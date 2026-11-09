#!/usr/bin/env python3
"""tools/fabric/github/evidence.py: a PR's file and commit lists come back whole or as Incomplete, never as a list that
may be cut (agent-fabric j119). GitHub is a fake `gh.api` / `gh.api_list`. Stdlib only; runnable as
`python3 tests/test_pr_evidence.py`.

The callers' cap cases beside these: post_review (tests/test_post_review.py, 250/249 and 3000/2999), arm's file list
(tests/test_arm_policy.py), review_checkpoint (tests/test_review_checkpoint.py), pr_counts (tests/test_pr_counts.py).
**Each case names the mutation it kills**:

  list_at_cap_is_incomplete   <- `>=` in evidence._list turned into `>`, or either cap constant changed
  below_cap_is_a_list         <- the cap test turned into an unconditional Incomplete
  unreadable_is_not_incomplete <- a non-list answer, or a non-object item, returned as a list
  has_commit                  <- a found sha refused in a cut list, or a missing one called False from a cut list
  memoised                    <- the second read made a second gh call
  polled_uses_api_list        <- polled=True reading through gh.api
  author_role_cap             <- arm.author_role reading a role from the cut list
  record_of_cap               <- pr_gate.record_of passing a cut file list to arm_rules.record_pr
  commit_rows_cap             <- pr_counts.commit_rows counting a cut commit list
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import gh  # noqa: E402
from github import arm, arm_rules, common, evidence, pr_counts, pr_gate  # noqa: E402

COMMIT_CAP, FILE_CAP = common.PR_COMMIT_LIST_CAP, common.PR_FILE_LIST_CAP


def commit(i: int, role: str = "web-dev") -> dict:
    return {"sha": f"{i:040x}", "parents": [{}], "commit": {"message": f"c{i}\n\nFabric-Role: {role}"}}


def api_of(commits: int = 0, files: int = 0):
    def api(path, **kw):
        if "/commits" in path:
            return [commit(i) for i in range(commits)]
        return [{"filename": f"docs/{i}.md"} for i in range(files)]
    return api


class Evidence(unittest.TestCase):
    def test_list_at_cap_is_incomplete(self):
        with mock.patch.object(gh, "api", api_of(COMMIT_CAP, FILE_CAP)):
            ev = evidence.PrEvidence("o/r", 7)
            self.assertEqual(ev.commits(), evidence.Incomplete("commits", COMMIT_CAP, COMMIT_CAP))
            self.assertEqual(ev.files(), evidence.Incomplete("files", FILE_CAP, FILE_CAP))
        self.assertEqual((COMMIT_CAP, FILE_CAP), (250, 3000))

    def test_below_cap_is_a_list(self):
        with mock.patch.object(gh, "api", api_of(COMMIT_CAP - 1, FILE_CAP - 1)):
            ev = evidence.PrEvidence("o/r", 7)
            self.assertEqual(len(ev.commits()), COMMIT_CAP - 1)
            self.assertEqual(len(ev.files()), FILE_CAP - 1)

    def test_unreadable_is_not_incomplete(self):
        for answer in ({"message": "Not Found"}, None, ["a"], [{"a": 1}, 3]):
            with self.subTest(answer=answer), mock.patch.object(gh, "api", lambda *a, **k: answer):
                with self.assertRaises(gh.GhError):
                    evidence.PrEvidence("o/r", 7).files()

    def test_has_commit(self):
        wanted = f"{0:040x}"
        with mock.patch.object(gh, "api", api_of(COMMIT_CAP)):
            self.assertIs(evidence.PrEvidence("o/r", 7).has_commit(wanted), True)
            self.assertIsInstance(evidence.PrEvidence("o/r", 7).has_commit("f" * 40), evidence.Incomplete)
        with mock.patch.object(gh, "api", api_of(COMMIT_CAP - 1)):
            self.assertIs(evidence.PrEvidence("o/r", 7).has_commit("f" * 40), False)

    def test_memoised(self):
        fake = mock.Mock(side_effect=api_of(3))
        with mock.patch.object(gh, "api", fake):
            ev = evidence.PrEvidence("o/r", 7)
            ev.commits(), ev.commits(), ev.has_commit("f" * 40)
        self.assertEqual(fake.call_count, 1)

    def test_polled_uses_api_list(self):
        with mock.patch.object(gh, "api", side_effect=AssertionError("paginated read")), \
                mock.patch.object(gh, "api_list", lambda path, **kw: [commit(1)]):
            self.assertEqual(len(evidence.PrEvidence("o/r", 7).commits(polled=True)), 1)
        with mock.patch.object(gh, "api_list", lambda path, **kw: [commit(i) for i in range(COMMIT_CAP)]):
            self.assertIsInstance(evidence.PrEvidence("o/r", 7).commits(polled=True), evidence.Incomplete)


class Callers(unittest.TestCase):
    def test_author_role_cap(self):
        with mock.patch.object(gh, "api", api_of(COMMIT_CAP)):
            self.assertIsNone(arm.author_role("o/r", "7"))
        with mock.patch.object(gh, "api", api_of(COMMIT_CAP - 1)):
            self.assertEqual(arm.author_role("o/r", "7"), "web-dev")

    def test_record_of_cap(self):
        seen = []

        def record_pr(listed, *rest):
            # AssertionError, not the TypeError record_of would catch: a cut list reaching the judge must be loud.
            assert isinstance(listed, list), listed
            seen.append(len(listed))
            return (True,)
        rules = ("boundary", "exempt", "rules")
        with mock.patch.object(arm_rules, "record_pr", record_pr):
            with mock.patch.object(gh, "api", api_of(files=FILE_CAP)):
                self.assertFalse(pr_gate.record_of(rules, "o/r", 7, "h" * 40))
            self.assertEqual(seen, [])
            with mock.patch.object(gh, "api", api_of(files=FILE_CAP - 1)):
                self.assertTrue(pr_gate.record_of(rules, "o/r", 7, "h" * 40))
            self.assertEqual(seen, [FILE_CAP - 1])

    def test_commit_rows_cap(self):
        pr = {"commits": {"pageInfo": {"hasNextPage": True}}}
        budget = pr_counts.Budget(60)
        with mock.patch.object(gh, "api", api_of(COMMIT_CAP)):
            with self.assertRaises(pr_counts.Unreadable) as cm:
                pr_counts.commit_rows(pr, "o/r", 7, budget)
        self.assertIn("past what GitHub lists", str(cm.exception))
        with mock.patch.object(gh, "api", api_of(COMMIT_CAP - 1)):
            rows, bodies = pr_counts.commit_rows(pr, "o/r", 7, budget)
        self.assertEqual(len(bodies), COMMIT_CAP - 1)


if __name__ == "__main__":
    unittest.main()
