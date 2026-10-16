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
from lint_rules.schema import personas_findings, validate_json  # noqa: E402

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
        self.l = os.path.join(self.tmp, "lineage.json")
        with open(self.l, "w", encoding="utf-8") as fh:
            json.dump({A1: {"login": "one"}, A2: {"login": "two"}}, fh)

    def judge(self, surnames: list, excluded: list, claims: dict) -> list[str]:
        with open(self.s, "w", encoding="utf-8") as fh:
            json.dump({"surnames": surnames, "excluded": excluded}, fh)
        claims = {k: {"surname": v, "first_name": "Ada"} if isinstance(v, str) else v for k, v in claims.items()}
        with open(self.c, "w", encoding="utf-8") as fh:
            json.dump({"claims": claims}, fh)
        return personas_findings(self.s, self.c, self.l)

    def test_a_consistent_list_and_claims_are_clean(self) -> None:
        self.assertEqual(self.judge([{**entry("Maxwell"), "taken_by": {"agent": A1, "login": "one"}},
                                     {**entry("Noether"), "taken_by": {"agent": A2, "login": "two"}}],
                                    [{"surname": "Nobel", "why": "dynamite"}],
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

    def test_a_first_name_null_is_not_chosen_yet(self) -> None:
        # Provisioning claims the surname; the agent chooses its first name later (ADR-056 A 2026-10-15).
        self.assertEqual(self.judge([{**entry("Maxwell"), "taken_by": {"agent": A1, "login": "one"}}], [], {A1: {"surname": "Maxwell", "first_name": None}}), [])

    def test_a_first_name_is_never_recorded_before_its_sex(self) -> None:
        # The sex first, then a first name of that sex (ADR-056 rules 5-6, A 2026-10-15). The sex lives in the agent's
        # profile, never in claims.json; the profile's schema, which `secret_store settings put` holds a profile to,
        # takes no first name without a sex beside it.
        with open(os.path.join(HERE, "identities", "schemas", "persona-profile.schema.json"), encoding="utf-8") as fh:
            schema = json.load(fh)
        profile = {"version": 1, "agent_id": A1, "first_name": "Ada", "surname": "Maxwell", "sex": "F",
                   "avatar": {"file": "settings/avatar.png", "candidate": 1, "sha256": "0" * 64}, "accepted": "2026-10-15"}
        self.assertEqual(validate_json(schema, profile, "profile.json"), [], "the control: with its sex, it stands")
        no_sex = {k: v for k, v in profile.items() if k != "sex"}
        self.assertTrue(any("sex" in f for f in validate_json(schema, no_sex, "profile.json")))
        self.assertTrue(any("sex" in f for f in validate_json(schema, {**profile, "sex": None}, "profile.json")))

    def test_a_pronoun_is_optional_but_not_empty(self) -> None:
        ok = {"surname": "Maxwell", "first_name": "Ada", "pronoun": "it"}
        self.assertEqual(self.judge([{**entry("Maxwell"), "taken_by": {"agent": A1, "login": "one"}}], [], {A1: ok}), [])
        self.assertTrue(any("empty pronoun" in f for f in self.judge([entry("Maxwell")], [], {A1: {**ok, "pronoun": ""}})))

    def test_a_claim_with_an_unknown_key_is_refused(self) -> None:
        bad = {"surname": "Maxwell", "first_name": "Ada", "pronouns": "it"}
        self.assertTrue(any("unknown key 'pronouns'" in f for f in self.judge([entry("Maxwell")], [], {A1: bad})))

    def test_a_surname_that_is_not_a_string_is_a_finding_not_a_crash(self) -> None:
        for bad in (["Maxwell"], {"a": 1}, 3, None):
            got = self.judge([entry("Maxwell")], [], {A1: {"surname": bad, "first_name": "Ada"}})
            self.assertTrue(any("no surname" in f for f in got), bad)

    def test_a_bare_surname_claim_is_refused(self) -> None:
        with open(self.s, "w", encoding="utf-8") as fh:
            json.dump({"surnames": [entry("Maxwell")], "excluded": []}, fh)
        with open(self.c, "w", encoding="utf-8") as fh:
            json.dump({"claims": {A1: "Maxwell"}}, fh)
        self.assertTrue(any("not a claim object" in f for f in personas_findings(self.s, self.c)))

    def test_taken_by_matches_claims_or_is_a_finding(self) -> None:
        def taken(s: str, agent: str, login: str) -> dict:
            return {**entry(s), "taken_by": {"agent": agent, "login": login}}
        claims = {A1: "Maxwell"}
        self.assertEqual(self.judge([taken("Maxwell", A1, "one"), entry("Noether")], [], claims), [], "the control")
        ghost = "01a00bc1-0000-7000-8000-000000000000"
        cases = (
            ("has no taken_by", [entry("Maxwell")], claims),
            ("has no claim on it", [taken("Maxwell", A1, "one"), taken("Noether", A2, "two")], claims),
            ("is not its claimant", [taken("Maxwell", A2, "two")], claims),
            ("is not " + A1 + "'s login", [taken("Maxwell", A1, "two")], claims),
            ("does not list", [taken("Maxwell", ghost, "x")], {ghost: "Maxwell"}),
            ("malformed taken_by", [{**entry("Maxwell"), "taken_by": "one"}], claims),
            ("malformed taken_by", [{**entry("Maxwell"), "taken_by": {"agent": A1}}], claims),
            ("malformed taken_by", [{**entry("Maxwell"), "taken_by": {"agent": A1, "login": "one", "x": 1}}], claims),
            ("malformed taken_by", [{**entry("Maxwell"), "taken_by": {"agent": A1, "login": ""}}], claims),
        )
        for said, surnames, cl in cases:
            self.assertTrue(any(said in f for f in self.judge(surnames, [], cl)), said)

    def test_the_committed_tree_marks_every_claim(self) -> None:
        got = personas_findings(os.path.join(HERE, "identities", "personas", "surnames.json"),
                                os.path.join(HERE, "identities", "personas", "claims.json"),
                                os.path.join(HERE, "identities", "keys", "lineage.json"))
        self.assertEqual(got, [])


if __name__ == "__main__":
    unittest.main()
