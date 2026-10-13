#!/usr/bin/env python3
"""The Codex review sign-in row of the `keys` read (agent-fabric ADR-053 rule 8, step 5): each login says until when it
can run the review and from which sign-in. Only the expiry leaves: no token, account id or fingerprint.

Each case fails when its guard is removed: the login's own sign-in is read before the synced one and a bad one of its
own is not replaced by the synced one; an unreadable file is "unreadable", never "none"; the row names no secret; the
keys section ends with the row."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
import chatgpt_signin  # noqa: E402
import gateway_token  # noqa: E402
from chatgpt_fixtures import ACCOUNT, ID_TOKEN, REFRESH, fake_jwt, write_signin  # noqa: E402
from control import ops  # noqa: E402
import control.ops.keys  # noqa: E402,F401 — the package re-exports a function named keys, so the module comes from sys.modules

keys_mod = sys.modules["control.ops.keys"]
UID = os.getuid()
NOW = 1_800_000_000


class Row(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="codex-row-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")
        self.run = os.path.join(self.tmp, "run")
        os.makedirs(self.home)
        os.makedirs(os.path.join(self.run, str(UID)))

    def own(self, exp, **kw):
        write_signin(os.path.join(self.home, ".codex-chatgpt"), exp, who="OWN-SENTINEL", **kw)

    def synced(self, exp, mode=0o600, text=None):
        path = gateway_token.token_path(UID, self.run, gateway_token.SIGNIN_NAME)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text if text is not None else chatgpt_signin.synced_text(fake_jwt(exp, "SYNCED-SENTINEL"), ACCOUNT))
        os.chmod(path, mode)

    def row(self):
        return keys_mod.codex_signin(self.home, self.run, UID, NOW)

    def test_no_sign_in_at_all_is_none(self):
        self.assertEqual(self.row(), {"name": keys_mod.CODEX_ROW, "present": False})

    def test_the_synced_sign_in_says_when_it_ends_and_that_it_is_the_synced_one(self):
        self.synced(NOW + 3 * 86400)
        self.assertEqual(self.row(), {"name": keys_mod.CODEX_ROW, "present": True, "via": "synced", "state": "ok",
                                      "expires_at": "2027-01-18T08:00:00.000Z", "expired": False})

    def test_an_expired_one_is_said_expired_with_its_date(self):
        self.synced(NOW - 60)
        r = self.row()
        self.assertEqual((r["state"], r["expired"], r["expires_at"]), ("expired", True, "2027-01-15T07:59:00.000Z"))

    def test_the_login_s_own_sign_in_is_read_before_the_synced_one(self):
        self.own(NOW + 10 * 86400)
        self.synced(NOW + 3 * 86400)
        r = self.row()
        self.assertEqual((r["via"], r["expires_at"]), ("own", "2027-01-25T08:00:00.000Z"))

    def test_a_bad_sign_in_of_its_own_is_unreadable_not_replaced_by_the_synced_one(self):
        self.own(NOW + 10 * 86400, mode=0o644)
        self.synced(NOW + 3 * 86400)
        self.assertEqual(self.row(), {"name": keys_mod.CODEX_ROW, "present": True, "via": "own", "state": "unreadable"})

    def test_a_synced_file_that_is_group_readable_or_malformed_is_unreadable_never_none(self):
        for label, kw in (("group readable", {"mode": 0o640}), ("not json", {"text": "{nope"}), ("no account", {"text": json.dumps({"access_token": fake_jwt(NOW + 9999)})})):
            with self.subTest(label):
                self.synced(NOW + 3 * 86400, **kw)
                self.assertEqual(self.row()["state"], "unreadable")

    def test_the_row_carries_no_token_account_id_or_fingerprint(self):
        self.own(NOW + 10 * 86400)
        self.synced(NOW + 3 * 86400)
        text = json.dumps([self.row(), keys_mod.codex_signin(self.home, self.run, UID, NOW + 99 * 86400)])
        for secret in (fake_jwt(NOW + 10 * 86400, "OWN-SENTINEL"), fake_jwt(NOW + 3 * 86400, "SYNCED-SENTINEL"), "SENTINEL", ACCOUNT, REFRESH, ID_TOKEN):
            self.assertNotIn(secret, text)
        self.assertEqual(sorted(self.row()), ["expired", "expires_at", "name", "present", "state", "via"])

    def test_the_keys_section_ends_with_the_row_and_hands_it_the_scratch_runtime_root(self):
        self.synced(int(time.time()) + 3 * 86400)
        rows = ops.SECTIONS["keys"]({"home": self.home, "runtime_root": self.run, "run": lambda *a, **k: (_ for _ in ()).throw(OSError("no git here"))})
        codex = [r for r in rows if r["name"] == keys_mod.CODEX_ROW]
        self.assertEqual((len(codex), rows[-1]["name"], codex[0]["via"]), (1, keys_mod.CODEX_ROW, "synced"))


if __name__ == "__main__":
    unittest.main()
