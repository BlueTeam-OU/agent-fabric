#!/usr/bin/env python3
"""routing/policies/availability.json (agent-fabric ADR-055 §5 rule 7): one strategy per provider in one
syntax, judged by its schema and by lint's checks a schema cannot make. Every case works on a copy of this
checkout's routing/ in a temporary directory, the real file first, then one defect at a time."""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.dont_write_bytecode = True
from lint_rules.schema import availability_findings  # noqa: E402


class AvailabilityPolicy(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        shutil.copytree(os.path.join(HERE, "routing"), os.path.join(self.tmp, "routing"))
        self.path = os.path.join(self.tmp, "routing", "policies", "availability.json")
        with open(self.path, encoding="utf-8") as fh:
            self.doc = json.load(fh)

    def judge(self, doc: dict) -> list[str]:
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        return availability_findings(self.tmp, self.path)

    def test_the_committed_policy_is_clean(self) -> None:
        self.assertEqual(self.judge(self.doc), [])

    def test_openai_is_the_less_tolerant(self) -> None:
        oa, an = self.doc["providers"]["openai"], self.doc["providers"]["anthropic"]
        self.assertEqual((oa["on_allowance"], len(oa["seats"]), len(oa["models"]["code-review"])), ("report", 1, 1))
        self.assertEqual(an["on_allowance"], "next-seat")
        self.assertGreater(len(an["models"]["code-review"]), 1)

    def test_a_list_must_start_at_the_routed_model(self) -> None:
        d = copy.deepcopy(self.doc)
        d["providers"]["anthropic"]["models"]["code-review"] = ["claude-opus-5", "claude-opus-5-5"]
        self.assertTrue(any("routing resolves it to 'claude-opus-5-5'" in f for f in self.judge(d)))

    def test_a_review_model_must_be_review_grade(self) -> None:
        d = copy.deepcopy(self.doc)
        d["providers"]["openai"]["models"]["code-review"].append("gpt-tiny")
        self.assertTrue(any("'gpt-tiny', which is not in the review-grade set" in f for f in self.judge(d)))

    def test_next_seat_needs_a_second_seat(self) -> None:
        d = copy.deepcopy(self.doc)
        d["providers"]["openai"]["on_allowance"] = "next-seat"
        self.assertTrue(any("names only one seat" in f for f in self.judge(d)))

    def test_anthropic_seats_are_the_account_switch_pool(self) -> None:
        d = copy.deepcopy(self.doc)
        d["providers"]["anthropic"]["seats"] = ["claude-pzhuy-8alias-com", "someone-else"]
        self.assertTrue(any("not the account-switch pool" in f for f in self.judge(d)))

    def test_the_schema_refuses_an_unknown_allowance_action(self) -> None:
        d = copy.deepcopy(self.doc)
        d["providers"]["openai"]["on_allowance"] = "divert-to-claude"
        self.assertTrue(self.judge(d))


if __name__ == "__main__":
    unittest.main()
