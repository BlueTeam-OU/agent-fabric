#!/usr/bin/env python3
"""tools/fabric/review_gateway.py synced_path (agent-fabric ADR-053 rule 8): the gateway looks for the synced sign-in
where its writer (gateway_token, behind `fabric-secrets sync`) and the keys read put and find it, whatever
XDG_RUNTIME_DIR says. Each case fails when synced_path goes back to following XDG_RUNTIME_DIR, or ignores the root a
test names."""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
import gateway_token  # noqa: E402
import review_gateway  # noqa: E402

UID = os.getuid()


class Path(unittest.TestCase):
    def test_it_is_the_writers_path_whatever_xdg_runtime_dir_is(self):
        want = gateway_token.token_path(UID, gateway_token.RUNTIME_ROOT, gateway_token.SIGNIN_NAME)
        for env in ({}, {"XDG_RUNTIME_DIR": "/var/tmp/xdg-elsewhere"}, {"XDG_RUNTIME_DIR": ""}):
            with self.subTest(env=env):
                self.assertEqual(review_gateway.synced_path(env), want)
        self.assertEqual(want, f"/run/user/{UID}/agent-fabric/gateway/chatgpt-signin.json")

    def test_a_relative_runtime_root_is_refused_not_resolved_against_the_cwd(self):
        with self.assertRaisesRegex(review_gateway.Refused, "not an absolute path"):
            review_gateway.synced_path({"AGENT_FABRIC_RUNTIME_ROOT": "rt"})

    def test_a_runtime_root_named_to_it_is_the_root_of_the_same_path(self):
        self.assertEqual(review_gateway.synced_path({"AGENT_FABRIC_RUNTIME_ROOT": "/scratch/rt"}),
                         gateway_token.token_path(UID, "/scratch/rt", gateway_token.SIGNIN_NAME))


if __name__ == "__main__":
    unittest.main()
