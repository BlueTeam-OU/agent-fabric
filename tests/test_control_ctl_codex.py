#!/usr/bin/env python3
"""The Codex review column of `fabric-ctl all keys` (agent-fabric ADR-053 rule 8, step 5): each login shows until when
it can run the review and from which sign-in, so the coordinator can tell when every login holds one.

Each case fails when its guard is removed: the cell for an ok, an expired, an unreadable and an absent sign-in; a
login that sent no row shows a dash; the row is not counted among the keys held nor listed among the absent ones; a
table of replies without the row prints exactly as it always did (the frozen wire)."""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
from control import ctl  # noqa: E402
import control.ops.keys  # noqa: E402,F401 — the package re-exports a function named keys, so the module comes from sys.modules
from test_control_ctl import placed, reply  # noqa: E402

keys_mod = sys.modules["control.ops.keys"]


class Table(unittest.TestCase):
    def keys(self, *extra):
        return [{"name": "GH_TOKEN", "present": True}, {"name": "OPENAI_API_KEY", "present": False},
                {"name": "signing key secret", "present": True}, {"name": "store commits verified", "present": True}, *extra]

    def table(self, *rows):
        return ctl.table("keys", ctl.rows(placed(*(f"a{i}" for i in range(len(rows)))),
                                          [reply(f"a{i}", "keys", {"keys": r}) for i, r in enumerate(rows)])).split("\n")

    def test_with_the_row_each_login_shows_until_when_and_from_which_sign_in(self):
        ok = {"name": keys_mod.CODEX_ROW, "present": True, "via": "synced", "state": "ok", "expires_at": "2026-10-20T14:03:00.000Z", "expired": False}
        gone = {"name": keys_mod.CODEX_ROW, "present": True, "via": "synced", "state": "expired", "expires_at": "2026-10-10T01:00:00.000Z", "expired": True}
        bad = {"name": keys_mod.CODEX_ROW, "present": True, "via": "own", "state": "unreadable"}
        none = {"name": keys_mod.CODEX_ROW, "present": False}
        t = self.table(self.keys(ok), self.keys(gone), self.keys(bad), self.keys(none), self.keys())
        self.assertRegex(t[0], r"^account\s+status\s+keys\s+signing\s+codex review\s+store$")
        self.assertRegex(t[1], r"^a0\s+ok\s+1/2\s+yes\s+2026-10-20 14:03 \(synced\)\s+verified$")
        self.assertIn("EXPIRED 2026-10-10 01:00 (synced)", t[3])
        self.assertIn("unreadable (own)", t[5])
        self.assertRegex(t[7], r"^a3\s+ok\s+1/2\s+yes\s+none\s+verified$")
        self.assertRegex(t[9], r"^a4\s+ok\s+1/2\s+yes\s+-\s+verified$", "a login that sent no row: a dash, not none")

    def test_the_row_is_not_a_key_held_nor_an_absent_key(self):
        none = {"name": keys_mod.CODEX_ROW, "present": False}
        t = self.table(self.keys(none))
        self.assertRegex(t[1], r"1/2\s+yes", "1 of the 2 keys, as before")
        self.assertEqual(t[2].strip(), "absent: OPENAI_API_KEY", "the sign-in is not listed among the absent keys")

    def test_replies_without_the_row_print_the_table_as_it_always_did(self):
        t = self.table(self.keys())
        self.assertRegex(t[0], r"^account\s+status\s+keys\s+signing\s+store$")
        self.assertNotIn("codex", "\n".join(t))


if __name__ == "__main__":
    unittest.main()
