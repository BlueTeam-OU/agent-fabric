#!/usr/bin/env python3
"""routing/policies/availability.json (agent-fabric ADR-055 §5 rule 7): one strategy per provider in one
syntax, judged by its schema and by lint's checks a schema cannot make. The policy and its two sibling
policies are this file's own fixtures in a temporary directory (routing/policies is instance data, ADR-045):
a valid strategy first, then one defect at a time. The engine's capabilities.json, review_codex.py and
routing.py are read from the checkout, as lint reads them."""
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

with open(os.path.join(HERE, "routing", "capabilities.json"), encoding="utf-8") as _fh:
    ROUTED = {p: v["models"] for p, v in json.load(_fh)["providers"].items()}

POLICY = {
    "version": 1,
    "description": "a fixture",
    "providers": {
        "anthropic": {"retry_after_s": [10, 20, 60], "seats": ["seat-a", "seat-b"], "on_allowance": "next-seat",
                      "models": {"code-review": [ROUTED["anthropic"]["code-review"], "claude-opus-5"]}},
        "openai": {"retry_after_s": [10, 20, 60], "seats": ["seat-o"], "on_allowance": "report",
                   "models": {"code-review": [ROUTED["openai"]["code-review"]]}},
        "openrouter": {"retry_after_s": [10, 20, 60], "seats": ["seat-r"], "on_allowance": "report",
                       "models": {"code-review": [ROUTED["openrouter"]["code-review"]]}},
    },
}
GRADE = {"models": [f"anthropic/{ROUTED['anthropic']['code-review']}", "anthropic/claude-opus-5",
                    f"openai/{ROUTED['openai']['code-review']}", ROUTED["openrouter"]["code-review"]]}
SWITCH = {"pool": {"accounts": ["seat-a", "seat-b"]}}


class AvailabilityPolicy(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.siblings = {}
        for name, doc in (("review-grade.json", GRADE), ("account-switch.json", SWITCH)):
            path = os.path.join(self.tmp, name)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
            self.siblings[name] = path
        self.path = os.path.join(self.tmp, "availability.json")

    def judge(self, doc: dict) -> list[str]:
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        return availability_findings(HERE, self.path, self.siblings)

    def test_a_valid_policy_is_clean(self) -> None:
        self.assertEqual(self.judge(POLICY), [])

    def test_the_committed_policy_keeps_openai_the_less_tolerant(self) -> None:
        live_path = os.path.join(HERE, "routing", "policies", "availability.json")
        if not os.path.exists(live_path):
            self.skipTest("no committed policy here (a stripped copy: routing/policies is instance data)")
        with open(live_path, encoding="utf-8") as fh:
            live = json.load(fh)["providers"]
        oa = live["openai"]
        self.assertEqual((oa["on_allowance"], len(oa["seats"]), len(oa["models"]["code-review"])), ("report", 1, 1))
        self.assertEqual(live["anthropic"]["on_allowance"], "next-seat")

    def test_a_list_must_start_at_the_routed_model(self) -> None:
        d = copy.deepcopy(POLICY)
        d["providers"]["anthropic"]["models"]["code-review"].reverse()
        self.assertTrue(any("but routing resolves it to" in f for f in self.judge(d)))

    def test_a_review_model_must_be_review_grade(self) -> None:
        d = copy.deepcopy(POLICY)
        d["providers"]["openai"]["models"]["code-review"].append("gpt-tiny")
        self.assertTrue(any("'gpt-tiny', which is not in the review-grade set" in f for f in self.judge(d)))

    def test_openrouter_ids_are_judged_unprefixed(self) -> None:
        self.assertFalse(any("openrouter" in f for f in self.judge(POLICY)))

    def test_an_unknown_provider_is_refused(self) -> None:
        d = copy.deepcopy(POLICY)
        d["providers"]["anthropc"] = d["providers"].pop("openrouter")
        self.assertTrue(any("'anthropc' is not a provider routing knows" in f for f in self.judge(d)))

    def test_a_capability_routing_does_not_route_is_refused(self) -> None:
        d = copy.deepcopy(POLICY)
        d["providers"]["anthropic"]["models"]["code-reveiw"] = ["claude-opus-5"]
        self.assertTrue(any("'code-reveiw', which routing does not route" in f for f in self.judge(d)))

    def test_next_seat_needs_a_second_seat(self) -> None:
        d = copy.deepcopy(POLICY)
        d["providers"]["openai"]["on_allowance"] = "next-seat"
        self.assertTrue(any("names only one seat" in f for f in self.judge(d)))

    def test_anthropic_seats_are_the_account_switch_pool(self) -> None:
        d = copy.deepcopy(POLICY)
        d["providers"]["anthropic"]["seats"] = ["seat-a", "someone-else"]
        self.assertTrue(any("not the account-switch pool" in f for f in self.judge(d)))

    def test_openai_waits_are_the_review_engines(self) -> None:
        d = copy.deepcopy(POLICY)
        d["providers"]["openai"]["retry_after_s"] = [5, 5]
        self.assertTrue(any("is not what review_codex.py waits" in f for f in self.judge(d)))

    def test_the_schema_refuses_an_unknown_allowance_action(self) -> None:
        d = copy.deepcopy(POLICY)
        d["providers"]["openai"]["on_allowance"] = "divert-to-claude"
        self.assertTrue(self.judge(d))


if __name__ == "__main__":
    unittest.main()
