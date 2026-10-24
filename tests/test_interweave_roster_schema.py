#!/usr/bin/env python3
"""runtime/interweave/roster.schema.json against the reader that decides
(tools/fabric/gzcoord/carrier/roster.py): the schema is the roster's shape
for a person or another tool, the reader is the authority, and the two must
not drift. Checked on the validator the fleet's pinned interpreter has
(lint_rules.schema, standard library only): the reader's own field set and
patterns are the schema's; a row the schema refuses the reader also refuses;
a row the schema admits with a bad signature the reader refuses too (the
schema cannot check a signature, which is the point of saying so)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from gzcoord.carrier import roster as R  # noqa: E402
from lint_rules.schema import validate_json  # noqa: E402

SCHEMA_PATH = os.path.join(ROOT, "runtime", "interweave", "roster.schema.json")


def _peer_id(seed: bytes) -> str:
    n, out = int.from_bytes(bytes([0x24, 0x08, 0x01, 0x12, 0x20]) + hashlib.sha256(seed).digest(), "big"), ""
    while n:
        n, r = divmod(n, 58)
        out = R._B58[r] + out
    return "1" + out      # the multihash's leading zero byte


PEER = _peer_id(b"alpha")
SHAPE_ONLY = "12D3KooW" + "1" * 44      # matches the schema's pattern; the reader decodes it and refuses
SIG = "-----BEGIN PGP SIGNATURE-----\n\nAAAA\n-----END PGP SIGNATURE-----\n"


def schema() -> dict:
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def good_row() -> dict:
    return {"agent_id": "00000000-0000-7000-8000-00000000000a", "login": "alpha", "peer_id": PEER,
            "endpoint": "gzcoord", "port": 47101, "identity_show": PEER + "\n",
            "login_signature": SIG, "countersignature": SIG}


def good_doc() -> dict:
    return {"version": 1, "profile": "gzcoord", "endpoint": "gzcoord", "port_range": [47100, 47199], "rows": [good_row()]}


def findings(doc: dict) -> list[str]:
    return validate_json(schema(), doc, "roster")


class Schema(unittest.TestCase):
    def test_positive_control_a_well_formed_roster_has_no_findings(self):
        self.assertEqual(findings(good_doc()), [])
        self.assertEqual(findings({**good_doc(), "rows": []}), [])

    def test_the_rows_fields_are_the_readers(self):
        row = schema()["$defs"]["row"]
        self.assertEqual(set(row["required"]), R.ROW_KEYS)
        self.assertEqual(set(row["properties"]), R.ROW_KEYS)
        self.assertIs(row["additionalProperties"], False)
        top = schema()
        self.assertEqual(set(top["required"]), {"version", "profile", "endpoint", "port_range", "rows"})

    def test_the_patterns_are_the_readers(self):
        props = schema()["$defs"]["row"]["properties"]
        self.assertEqual(props["agent_id"]["pattern"], f"^{R.AGENT_ID_RE.pattern}$")
        self.assertEqual(props["login"]["pattern"], f"^{R.LOGIN_RE.pattern}$")
        self.assertEqual(props["endpoint"]["pattern"], f"^{R.ENDPOINT_RE.pattern}$")
        self.assertEqual(schema()["properties"]["endpoint"]["pattern"], f"^{R.ENDPOINT_RE.pattern}$")
        self.assertEqual(schema()["properties"]["profile"]["pattern"], f"^{R.PROFILE_RE.pattern}$")
        self.assertTrue(re.fullmatch(props["peer_id"]["pattern"], PEER))
        self.assertTrue(R.peer_id_ok(PEER), "positive control: the fixture's PeerId is a real one")
        self.assertTrue(re.fullmatch(props["peer_id"]["pattern"], SHAPE_ONLY) and not R.peer_id_ok(SHAPE_ONLY),
                        "the schema's pattern is necessary, not sufficient")
        self.assertEqual(schema()["$defs"]["port"]["minimum"], 1024)
        self.assertEqual(schema()["$defs"]["port"]["maximum"], 65535)

    def test_each_malformation_is_found(self):
        def with_row(**kw):
            d = good_doc()
            d["rows"][0].update(kw)
            return d
        cases = {
            "an unknown row field": with_row(note="x"),
            "a string port": with_row(port="47101"),
            "a port below 1024": with_row(port=80),
            "a malformed PeerId": with_row(peer_id="x"),
            "a malformed agent id": with_row(agent_id="nope"),
            "an upper-case login": with_row(login="Alpha"),
            "a signature that is not armor": with_row(login_signature="abc"),
            "an empty identity_show": with_row(identity_show=""),
            "version 2": {**good_doc(), "version": 2},
            "a one-element port range": {**good_doc(), "port_range": [47100]},
            "version true": {**good_doc(), "version": True},
        }
        for name, doc in cases.items():
            with self.subTest(name):
                self.assertTrue(findings(doc), name)
        missing = good_doc()
        del missing["rows"][0]["countersignature"]
        self.assertTrue(findings(missing), "a missing countersignature")

    def test_the_top_level_is_as_tolerant_as_the_reader(self):
        # roster.load ignores a top-level key it does not know; a schema that refused it would call valid a roster the carrier uses.
        import tempfile
        doc = {**good_doc(), "extra": 1}
        self.assertEqual(findings(doc), [])
        with tempfile.TemporaryDirectory(prefix="roster-schema.") as d:
            path = os.path.join(d, "roster.json")
            with open(path, "w") as fh:
                json.dump(doc, fh)
            self.assertEqual(R.load(path).profile, "gzcoord")
            for bad in (True, 2, "1"):
                with open(path, "w") as fh:
                    json.dump({**good_doc(), "version": bad}, fh)
                with self.assertRaises(R.RosterError, msg=repr(bad)):
                    R.load(path)

    def test_what_the_schema_refuses_the_reader_refuses_too(self):
        # A malformed row is refused by valid_rows before any key is read, so this runs with no keys.
        class NoKeys:
            def lineage(self):
                return {"root": {"login": "user", "fingerprint": "A" * 40, "parent": None}}

            def public_key(self, agent_id):
                return None
        for field, value in (("port", "47101"), ("peer_id", "x"), ("agent_id", "nope"), ("login", "Alpha"), ("note", "x")):
            doc = good_doc()
            doc["rows"][0][field] = value
            self.assertTrue(findings(doc), field)
            rows = tuple(doc["rows"])
            good, bad = R.valid_rows(R.Roster("gzcoord", "gzcoord", (47100, 47199), rows), NoKeys())
            self.assertEqual((good, len(bad)), ([], 1), field)

    def test_a_row_the_schema_admits_with_a_bad_signature_is_refused_by_the_reader(self):
        # Counterfactual to the schema's claim that it cannot check signatures: shape is clean, the reader says no.
        class Keys:
            def lineage(self):
                return {"root": {"login": "user", "fingerprint": "A" * 40, "parent": None},
                        good_row()["agent_id"]: {"login": "alpha", "fingerprint": "B" * 40, "parent": "root"}}

            def public_key(self, agent_id):
                return b"not a key"
        doc = good_doc()
        self.assertEqual(findings(doc), [])
        good, bad = R.valid_rows(R.Roster("gzcoord", "gzcoord", (47100, 47199), tuple(doc["rows"])), Keys())
        self.assertEqual(good, [])
        self.assertEqual([b.reason.split(":")[0] for b in bad], ["login signature"])


if __name__ == "__main__":
    unittest.main()
