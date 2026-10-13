#!/usr/bin/env python3
"""tools/fabric/persona.py: a login or an agent id becomes `AI <First> <Surname>, <Role title>`. Fixtures only,
in a temporary tree read through the roots helpers' `root`."""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.dont_write_bytecode = True
import persona  # noqa: E402
import roots  # noqa: E402

IDS = {n: f"01a00bc1-47{n:02d}-7ace-a01e-6e46a11f9acc" for n in range(1, 8)}
LOGINS = {1: "user", 2: "python-dev-02", 3: "language-culture-ge", 4: "web-dev", 5: "stranger-01", 6: "p2p-network-dev-01", 7: "unclaimed"}


def write(root: str, rel: str, doc: dict) -> None:
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


class Persona(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        write(self.root, "identities/keys/lineage.json", {IDS[n]: {"login": LOGINS[n], "parent": None} for n in LOGINS})
        claims = {IDS[n]: {"surname": f"Sur{n}", "first_name": f"First{n}"} for n in range(1, 7)}
        claims[IDS[2]]["pronoun"] = "it"
        write(self.root, "identities/personas/claims.json", {"claims": claims})
        write(self.root, "identities/roles/catalog.json", {"roles": [
            {"id": "fabric-coordinator", "title": "Coordinator"}, {"id": "python-dev", "title": "Python developer"},
            {"id": "language-culture", "title": "Linguist"}, {"id": "web-dev", "title": "Web developer"},
            {"id": "p2p-network-dev", "title": "P2P developer"}]})
        write(self.root, "policies/authority.json", {"role_definitions": {"role": "fabric-coordinator", "holders": ["user"]}})
        os.makedirs(roots.locale_dir("language-culture", "ge", root=self.root))
        self.env = mock.patch.dict(os.environ, {roots.ENV_OPERATOR: self.root})
        self.env.start()
        self.addCleanup(self.env.stop)

    def run_main(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = persona.main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def test_roles_by_number_locale_alone_and_holder(self) -> None:
        got = {a["login"]: a["display"] for a in persona.agents(self.root)}
        self.assertEqual(got["user"], "AI First1 Sur1, Coordinator")
        self.assertEqual(got["python-dev-02"], "AI First2 Sur2, Python developer")
        self.assertEqual(got["language-culture-ge"], "AI First3 Sur3, Linguist")
        self.assertEqual(got["web-dev"], "AI First4 Sur4, Web developer")
        self.assertEqual(got["p2p-network-dev-01"], "AI First6 Sur6, P2P developer")

    def test_a_login_with_no_role_has_a_name_without_a_title(self) -> None:
        self.assertEqual(persona.find("stranger-01", self.root)["display"], "AI First5 Sur5")

    def test_login_and_id_answer_the_same(self) -> None:
        self.assertEqual(self.run_main("python-dev-02"), (0, "AI First2 Sur2, Python developer\n", ""))
        self.assertEqual(self.run_main(IDS[2])[1], "AI First2 Sur2, Python developer\n")

    def test_json_shape(self) -> None:
        rc, out, _ = self.run_main("--json", "user")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out), {"login": "user", "agent_id": IDS[1], "display": "AI First1 Sur1, Coordinator",
                                           "first_name": "First1", "surname": "Sur1", "role": "fabric-coordinator",
                                           "role_title": "Coordinator"})

    def test_all_is_one_line_per_claimed_agent(self) -> None:
        rc, out, _ = self.run_main("--all")
        self.assertEqual(rc, 0)
        self.assertEqual(len(out.splitlines()), 6)

    def test_an_unknown_or_unclaimed_agent_exits_2_with_one_line(self) -> None:
        for who in ("nobody", "unclaimed"):
            rc, out, err = self.run_main(who)
            self.assertEqual((rc, out, len(err.splitlines())), (2, "", 1))


if __name__ == "__main__":
    unittest.main()
