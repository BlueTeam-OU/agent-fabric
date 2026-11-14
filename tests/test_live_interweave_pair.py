#!/usr/bin/env python3
"""The two-account live check (tests/live_interweave_two_accounts.py, not part of the suite) renders the config of
the pair it tests: a third admitted row, on this host or another, must not change a byte of it (#598 F4/F5)."""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest
import unittest.mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from gzcoord import paths  # noqa: E402
from gzcoord.carrier import roster as R  # noqa: E402

_spec = importlib.util.spec_from_file_location("live_pair_under_test", os.path.join(ROOT, "tests", "live_interweave_two_accounts.py"))
live = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(live)


def row(login: str, port: int, **more) -> dict:
    # render_config reads no signature: the rows here are already judged
    return {"agent_id": f"id-{login}", "login": login, "peer_id": f"peer-{login}", "port": port, **more}


HOSTS = {"h2": {"interweave_address": "192.0.2.7"}}


def roster(rows: list[dict], hosts: dict | None = None) -> R.Roster:
    return R.Roster("gzcoord", "gzcoord", (47100, 47199), tuple(rows), hosts or {})


class PairRender(unittest.TestCase):
    A, B = row("alpha", 47101), row("beta", 47102)

    def render(self, rows: list[dict], hosts: dict | None = None) -> str:
        r, good = live.pair_of(roster(rows, hosts), list(rows), ("alpha", "beta"))
        return R.render_config(r, good, self.A["agent_id"], own_host="h1")

    def through_judged_roster(self, rows: list[dict], hosts: dict | None = None) -> str:
        # the entry the live check calls: its own narrowing, not pair_of in isolation
        with unittest.mock.patch.object(live, "LOGIN", "alpha"), unittest.mock.patch.object(live, "PEER", "beta"), \
                unittest.mock.patch.object(R, "load", return_value=roster(rows, hosts)), \
                unittest.mock.patch.object(R, "valid_rows", return_value=(list(rows), [])), \
                unittest.mock.patch.object(R, "GitMainKeys"), unittest.mock.patch.object(paths, "operator_root", return_value="/x"):
            r, good, _ = live.judged_roster()
        return R.render_config(r, good, self.A["agent_id"], own_host="h1")

    def test_a_third_row_changes_nothing_the_pair_renders(self):
        two = self.render([self.A, self.B])
        self.assertEqual(two, self.render([self.A, self.B, row("gamma", 47103)]))
        self.assertEqual(two, self.render([row("gamma", 47103), self.A, self.B, row("delta", 47100)]))

    def test_a_third_row_on_another_host_changes_nothing_either(self):
        other = row("gamma", 47103, host="h2")
        self.assertEqual(self.render([self.A, self.B], HOSTS), self.render([self.A, self.B, other], HOSTS))
        rows = [self.A, self.B, other]
        self.assertIn("/ip4/192.0.2.7/tcp/47103", R.render_config(roster(rows, HOSTS), rows, self.A["agent_id"], own_host="h1"))

    def test_judged_roster_renders_the_pair_whatever_else_is_admitted(self):
        two = self.through_judged_roster([self.A, self.B])
        self.assertEqual(two, self.through_judged_roster([self.A, self.B, row("gamma", 47103), row("delta", 47104)]))
        self.assertEqual(two, self.through_judged_roster([self.A, self.B, row("gamma", 47103, host="h2")], HOSTS))
        self.assertIn("peer-beta", two)
        self.assertNotIn("peer-gamma", two)

    def test_positive_control_the_whole_roster_does_name_the_third(self):
        rows = [self.A, self.B, row("gamma", 47103)]
        whole = R.render_config(roster(rows), rows, self.A["agent_id"], own_host="h1")
        self.assertIn("peer-gamma", whole)
        self.assertNotIn("peer-gamma", self.render(rows))

    def test_pair_keeps_both_rows_of_the_roster_and_the_good_list(self):
        rows = [self.A, self.B, row("gamma", 47103)]
        r, good = live.pair_of(roster(rows), rows, ("alpha", "beta"))
        self.assertEqual([x["login"] for x in r.rows], ["alpha", "beta"])
        self.assertEqual([x["login"] for x in good], ["alpha", "beta"])


if __name__ == "__main__":
    unittest.main()
