#!/usr/bin/env python3
"""tools/fabric/gateway_token.py with name=SIGNIN_NAME (agent-fabric ADR-053 rule 8): the Codex review's synced ChatGPT
sign-in is a second file in the gateway's directory, written, replaced and removed exactly as the Claude token is
and independent of it. test_gateway_token.py, unchanged, holds the Claude token's own cases.

Each case fails when `name` is ignored (both files would be one), when a write of one touches the other, or when
the replacement is not by a new 0600 file."""
from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
import chatgpt_signin  # noqa: E402
import gateway_token as g  # noqa: E402
from chatgpt_fixtures import ACCOUNT, fake_jwt  # noqa: E402

UID = os.getuid()
CLAUDE = "sk-ant-oat01-" + "a" * 60
SIGNIN = chatgpt_signin.synced_text(fake_jwt(1_800_000_000), ACCOUNT)


class SigninFile(unittest.TestCase):
    def setUp(self):
        base = tempfile.mkdtemp(prefix="gwt-signin-")
        self.addCleanup(shutil.rmtree, base, True)
        self.root = os.path.join(base, "run-user")
        os.makedirs(os.path.join(self.root, str(UID)), mode=0o700)
        os.chmod(self.root, 0o755)

    def write(self, text, name=g.SIGNIN_NAME):
        return g.write(text, UID, self.root, lambda p: "tmpfs", self.root, name=name)

    def test_the_path_is_beside_the_claude_token_and_not_it(self):
        a, b = g.token_path(UID, self.root), g.token_path(UID, self.root, g.SIGNIN_NAME)
        self.assertEqual((os.path.dirname(a), os.path.basename(b)), (os.path.dirname(b), "chatgpt-signin.json"))
        self.assertNotEqual(a, b)

    def test_it_is_written_0600_by_a_new_file_and_the_same_text_again_is_unchanged(self):
        self.assertEqual(self.write(SIGNIN), "written")
        path = g.token_path(UID, self.root, g.SIGNIN_NAME)
        st = os.stat(path)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), SIGNIN)
        self.assertEqual((stat.S_IMODE(st.st_mode), st.st_uid), (0o600, UID))
        self.assertEqual(self.write(SIGNIN), "unchanged")
        self.assertEqual(os.stat(path).st_ino, st.st_ino)
        self.assertEqual(self.write(chatgpt_signin.synced_text(fake_jwt(1_800_000_001), ACCOUNT)), "written")
        self.assertNotEqual(os.stat(path).st_ino, st.st_ino, "a changed text is a new inode")
        self.assertEqual(os.listdir(os.path.dirname(path)), [g.SIGNIN_NAME], "nothing else is left")

    def test_the_two_files_are_independent(self):
        self.write(CLAUDE, g.NAME)
        self.write(SIGNIN)
        d = os.path.dirname(g.token_path(UID, self.root))
        self.assertEqual(sorted(os.listdir(d)), sorted([g.NAME, g.SIGNIN_NAME]))
        self.assertEqual(g.remove(UID, self.root, g.SIGNIN_NAME), "removed")
        self.assertEqual(os.listdir(d), [g.NAME], "the Claude token stays")
        self.assertEqual(g.remove(UID, self.root, g.SIGNIN_NAME), "absent")
        self.assertEqual(g.remove(UID, self.root), "removed")
        self.assertEqual(os.listdir(d), [])

    def test_the_text_must_be_a_header_safe_run_like_a_token(self):
        with self.assertRaises(g.TokenFileError):
            self.write('{"access_token": "x y"}')
        self.assertFalse(os.path.exists(g.token_path(UID, self.root, g.SIGNIN_NAME)))


if __name__ == "__main__":
    unittest.main()
