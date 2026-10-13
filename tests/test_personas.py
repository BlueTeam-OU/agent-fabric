#!/usr/bin/env python3
"""identities/personas/ (agent-fabric ADR-056 §5 rules 3-4): lint keeps the surname list unique and
consistent with its exclusions, and the claims one surname per agent id. Fixtures only, in a temporary
directory: the committed list is the operator's data."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.dont_write_bytecode = True
from lint_rules.schema import personas_findings  # noqa: E402

A1 = "01a00bc1-4824-7ace-a01e-6e46a11f9acc"
A2 = "019bbe31-2fff-7a2f-9849-96bdf286e011"


def entry(s: str) -> dict:
    return {"surname": s, "person": f"{s} the scientist", "from": "Somewhere", "known_for": "x", "lived": "1-2"}


class Personas(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.s = os.path.join(self.tmp, "surnames.json")
        self.c = os.path.join(self.tmp, "claims.json")

    def judge(self, surnames: list, excluded: list, claims: dict) -> list[str]:
        with open(self.s, "w", encoding="utf-8") as fh:
            json.dump({"surnames": surnames, "excluded": excluded}, fh)
        claims = {k: {"surname": v, "first_name": "Ada"} if isinstance(v, str) else v for k, v in claims.items()}
        with open(self.c, "w", encoding="utf-8") as fh:
            json.dump({"claims": claims}, fh)
        return personas_findings(self.s, self.c)

    def test_a_consistent_list_and_claims_are_clean(self) -> None:
        self.assertEqual(self.judge([entry("Maxwell"), entry("Noether")], [{"surname": "Nobel", "why": "dynamite"}],
                                    {A1: "Maxwell", A2: "Noether"}), [])

    def test_a_surname_listed_twice_is_refused(self) -> None:
        self.assertTrue(any("listed more than once" in f for f in self.judge([entry("Curie"), entry("Curie")], [], {})))

    def test_a_surname_listed_and_excluded_is_refused(self) -> None:
        got = self.judge([entry("Fermi")], [{"surname": "Fermi", "why": "the bomb"}], {})
        self.assertTrue(any("both listed and excluded" in f for f in got))

    def test_an_exclusion_needs_its_reason(self) -> None:
        self.assertTrue(any("gives no reason" in f for f in self.judge([], [{"surname": "Teller", "why": ""}], {})))

    def test_an_entry_needs_its_person(self) -> None:
        self.assertTrue(any("lacks its surname, person or from" in f for f in self.judge([{"surname": "Euler"}], [], {})))

    def test_one_surname_per_agent(self) -> None:
        got = self.judge([entry("Maxwell")], [], {A1: "Maxwell", A2: "Maxwell"})
        self.assertTrue(any("is claimed by" in f for f in got))

    def test_a_claim_names_a_listed_surname(self) -> None:
        self.assertTrue(any("not on the list" in f for f in self.judge([entry("Maxwell")], [], {A1: "Oppenheimer"})))

    def test_a_claim_is_keyed_by_an_agent_id(self) -> None:
        self.assertTrue(any("not an agent id" in f for f in self.judge([entry("Maxwell")], [], {"python-dev-01": "Maxwell"})))

    def test_a_claim_needs_its_first_name(self) -> None:
        for bad in ({"surname": "Maxwell"}, {"surname": "Maxwell", "first_name": " "}, {"surname": "Maxwell", "first_name": 3}):
            self.assertTrue(any("no first_name" in f for f in self.judge([entry("Maxwell")], [], {A1: bad})), bad)

    def test_a_pronoun_is_optional_but_not_empty(self) -> None:
        ok = {"surname": "Maxwell", "first_name": "Ada", "pronoun": "it"}
        self.assertEqual(self.judge([entry("Maxwell")], [], {A1: ok}), [])
        self.assertTrue(any("empty pronoun" in f for f in self.judge([entry("Maxwell")], [], {A1: {**ok, "pronoun": ""}})))

    def test_a_bare_surname_claim_is_refused(self) -> None:
        with open(self.s, "w", encoding="utf-8") as fh:
            json.dump({"surnames": [entry("Maxwell")], "excluded": []}, fh)
        with open(self.c, "w", encoding="utf-8") as fh:
            json.dump({"claims": {A1: "Maxwell"}}, fh)
        self.assertTrue(any("not a claim object" in f for f in personas_findings(self.s, self.c)))


if __name__ == "__main__":
    unittest.main()
