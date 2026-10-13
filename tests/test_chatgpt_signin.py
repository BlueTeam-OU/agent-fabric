#!/usr/bin/env python3
"""tools/fabric/chatgpt_signin.py (agent-fabric ADR-053 rule 8): the access token, the account id and the exp of a
ChatGPT sign-in, and nothing else. Each case fails when its guard is removed: the link, mode and size refusals of
read_owned (a sign-in is the login's alone); jwt_exp's shape checks; the account id and header-safe checks; the
refresh and id tokens never returned or echoed (a sentinel value proves it); the synced file's compact text."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
import chatgpt_signin as cs  # noqa: E402
from chatgpt_fixtures import ACCOUNT, ID_TOKEN, REFRESH, b64, fake_jwt, write_signin  # noqa: E402

EXP = 1_800_000_000


class SignIn(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="chatgpt-signin-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_a_sign_in_gives_the_access_token_the_account_and_the_exp_and_nothing_else(self):
        write_signin(self.tmp, EXP)
        got = cs.read_signin(self.tmp)
        self.assertEqual(got, (fake_jwt(EXP), ACCOUNT, EXP))
        self.assertNotIn(REFRESH, repr(got))
        self.assertNotIn(ID_TOKEN, repr(got))

    def test_a_missing_file_is_missing_and_another_auth_mode_is_not_a_sign_in(self):
        with self.assertRaises(cs.Missing):
            cs.read_signin(self.tmp)
        with open(os.path.join(self.tmp, "auth.json"), "w", encoding="utf-8") as fh:
            json.dump({"auth_mode": "apikey", "OPENAI_API_KEY": "sk-fake"}, fh)
        os.chmod(os.path.join(self.tmp, "auth.json"), 0o600)
        with self.assertRaises(cs.NotSignIn) as ctx:
            cs.read_signin(self.tmp)
        self.assertNotIn("sk-fake", str(ctx.exception))
        # Another auth_mode that nevertheless holds well-formed tokens is still not a ChatGPT sign-in.
        path = write_signin(self.tmp, EXP)
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        doc["auth_mode"] = "apikey"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        with self.assertRaises(cs.NotSignIn):
            cs.read_signin(self.tmp)

    def test_a_file_that_is_not_this_logins_is_refused_whatever_its_mode(self):
        write_signin(self.tmp, EXP)
        cs.read_signin(self.tmp)          # the control: it is this login's
        with mock.patch("os.getuid", return_value=os.getuid() + 1):
            with self.assertRaisesRegex(cs.Refused, "not this login's"):
                cs.read_signin(self.tmp)

    def test_a_file_anyone_else_can_read_is_refused_before_it_is_parsed(self):
        path = write_signin(self.tmp, EXP, mode=0o640)
        with self.assertRaisesRegex(cs.Refused, "readable by another user"):
            cs.read_signin(self.tmp)
        os.chmod(path, 0o600)
        cs.read_signin(self.tmp)          # the control: the same file at 0600 is read

    def test_a_link_in_the_files_place_is_refused(self):
        real = write_signin(os.path.join(self.tmp, "real"), EXP)
        os.makedirs(os.path.join(self.tmp, "home"))
        os.symlink(real, os.path.join(self.tmp, "home", "auth.json"))
        with self.assertRaisesRegex(cs.Refused, "cannot be opened"):
            cs.read_signin(os.path.join(self.tmp, "home"))

    def test_a_directory_and_an_oversized_file_are_refused(self):
        os.makedirs(os.path.join(self.tmp, "auth.json"))
        with self.assertRaisesRegex(cs.Refused, "not a regular file"):
            cs.read_signin(self.tmp)
        shutil.rmtree(os.path.join(self.tmp, "auth.json"))
        fd = os.open(os.path.join(self.tmp, "auth.json"), os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(b" " * (cs.MAX_AUTH_BYTES + 1))
        with self.assertRaisesRegex(cs.Refused, "not a sign-in"):
            cs.read_signin(self.tmp)

    def test_the_account_id_and_the_token_must_be_what_the_backend_takes(self):
        for label, account, access in (("an account id that is not a uuid", "acct-1", fake_jwt(EXP)),
                                       ("an account id that is missing", None, fake_jwt(EXP)),
                                       ("a token with a space", ACCOUNT, "a b.c.d"),
                                       ("a token that is not a jwt", ACCOUNT, "plain-token")):
            with self.subTest(label):
                write_signin(self.tmp, EXP, account=ACCOUNT)
                path = os.path.join(self.tmp, "auth.json")
                with open(path, encoding="utf-8") as fh:
                    doc = json.load(fh)
                doc["tokens"]["account_id"], doc["tokens"]["access_token"] = account, access
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(doc, fh)
                with self.assertRaises(cs.Refused) as ctx:
                    cs.read_signin(self.tmp)
                self.assertNotIn(access, str(ctx.exception), "a refusal never holds the token")

    def test_jwt_exp_reads_an_integer_exp_and_nothing_else(self):
        self.assertEqual(cs.jwt_exp(fake_jwt(EXP + 5)), EXP + 5)
        for label, tok in (("two parts", "a.b"), ("a payload that is not JSON", "a.bm90IGpzb24.c"), ("no exp", f"a.{b64({'sub': 'x'})}.c"),
                           ("an exp that is a string", f"a.{b64({'exp': '1'})}.c"), ("an exp that is a bool", f"a.{b64({'exp': True})}.c"),
                           ("an exp that is a float", f"a.{b64({'exp': 1.5})}.c"),
                           ("an exp past year 9999", f"a.{b64({'exp': 10 ** 12})}.c"), ("an exp past 2106", f"a.{b64({'exp': 2 ** 32})}.c"),
                           ("a negative exp", f"a.{b64({'exp': -5})}.c"), ("an exp of zero", f"a.{b64({'exp': 0})}.c")):
            with self.subTest(label):
                with self.assertRaises(ValueError) as ctx:
                    cs.jwt_exp(tok)
                self.assertNotIn(tok, str(ctx.exception))

    def test_a_fifo_in_the_files_place_is_refused_at_once_not_waited_on(self):
        import threading
        os.mkfifo(os.path.join(self.tmp, "auth.json"), 0o600)
        done = []

        def read():
            try:
                cs.read_signin(self.tmp)
            except cs.Refused as e:
                done.append(str(e))
        th = threading.Thread(target=read, daemon=True)
        th.start()
        th.join(5)
        self.assertFalse(th.is_alive(), "open() on a FIFO must not block")
        self.assertIn("not a regular file", done[0])

    def test_the_synced_file_is_compact_header_safe_text_that_reads_back(self):
        text = cs.synced_text(fake_jwt(EXP), ACCOUNT)
        self.assertNotIn(" ", text)
        self.assertTrue(all(0x21 <= ord(c) <= 0x7E for c in text), "printable ASCII: gateway_token.write admits it as a token")
        path = os.path.join(self.tmp, "synced.json")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        self.assertEqual(cs.read_synced(path), (fake_jwt(EXP), ACCOUNT, EXP))
        with self.assertRaises(cs.Missing):
            cs.read_synced(os.path.join(self.tmp, "absent.json"))
        for bad in ("[]", "not json", json.dumps({"access_token": fake_jwt(EXP)}), json.dumps({"account_id": ACCOUNT})):
            with self.subTest(bad=bad):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(bad)
                with self.assertRaises(cs.Refused):
                    cs.read_synced(path)


if __name__ == "__main__":
    unittest.main()
