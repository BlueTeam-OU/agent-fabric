#!/usr/bin/env python3
"""j68 (fabric-coordinator REPLY 01a11ec9-b9e8, after #170 deleted the Node control plane): an account
that cannot read its own session state says so on the wire, as the string "unreadable" where `sessions`
is always a list, and ctl's reader shows the account's state unknown with why, never "none".
tests/test_control_sessions.py (the watcher's oracle, one block changed on purpose) and
tests/test_control_ctl.py (ctl's, unchanged) hold the rest; this is the contract end to end:
the record the watcher posts, the validator, the row, the table, and what a list-only reader does
with it. Plain script: unittest."""
from __future__ import annotations

import datetime
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402

own_instance_tree()
from control import ctl, sessions as cs  # noqa: E402
import fleet  # noqa: E402

NOW = 1_800_000_000_000.0


def iso(ms: float) -> str:
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def record(sessions, frm="h/a", ts=None, **extra) -> dict:
    return {"id": "m", "content": json.dumps({"v": 1, "kind": "state", "from": frm, "ts": ts or iso(NOW - 60_000), "sessions": sessions, **extra})}


class Validator(unittest.TestCase):
    def test_unreadable_is_accepted_and_nothing_else_that_is_not_a_list(self):
        want = {"h/a"}
        self.assertIsNotNone(ctl.state_record_of(record("unreadable"), want))
        for bad in ("none", "Unreadable", " unreadable", "unreadable ", "", "x", {}, None, 7, True, ["unreadable"] if False else {"unreadable": 1}):
            self.assertIsNone(ctl.state_record_of(record(bad), want), repr(bad))
        self.assertIsNotNone(ctl.state_record_of(record([]), want), "positive control: a list still passes")

    def test_a_record_that_says_unreadable_is_still_judged_on_its_other_fields(self):
        want = {"h/a"}
        self.assertIsNone(ctl.state_record_of(record("unreadable", last_session="../../etc/x"), want))
        self.assertIsNone(ctl.state_record_of(record("unreadable", frm="h/other"), want))
        self.assertIsNone(ctl.state_record_of(record("unreadable", role=7), want))


class Row(unittest.TestCase):
    def row(self, sessions="unreadable", ts=None, **extra) -> dict:
        r = ctl.state_record_of(record(sessions, ts=ts, **extra), {"h/a"})
        return ctl.state_row("h/a", r, NOW)

    def test_the_account_is_unknown_with_why_no_sessions_and_no_since(self):
        row = self.row(role="web-dev", project="gzapp")
        self.assertEqual((row["state"], row["why"], row["sessions"], row["since"]), ("unknown", "the account cannot read its session state", [], None))
        self.assertEqual((row["role"], row["project"]), ("web-dev", "gzapp"), "what the record still says is shown")

    def test_it_is_never_none(self):
        self.assertEqual(self.row([])["state"], "none", "positive control: an empty list is none")
        self.assertNotEqual(self.row("unreadable")["state"], "none")

    def test_a_stale_record_says_it_is_stale_not_unreadable(self):
        row = self.row("unreadable", ts=iso(NOW - ctl.STATES_STALE_MS - 1000))
        self.assertEqual((row["state"], row["why"]), ("unknown", "no record for two heartbeats"))

    def test_the_resume_fields_still_ride_along(self):
        row = self.row(last_session="0f0e0d0c-1111-4222-8333-444455556666", resumable=True)
        self.assertEqual((row["last_session"], row["resumable"]), ("0f0e0d0c-1111-4222-8333-444455556666", True))

    def test_the_states_command_prints_the_unknown_row_with_its_why(self):
        out: list = []
        rc = ctl.states({"json": True, "follow": False}, [{"address": "h/a"}], call=lambda p, **kw: {"messages": [record("unreadable")]},
                        cfg={"channel": "c", "state_channel": "s", "relay_url": "x"}, out=lambda m: out.append(json.loads(m)), now=lambda: NOW)
        self.assertEqual(rc, 0)
        self.assertEqual([(r["state"], r["sessions"], r["why"]) for r in out], [("unknown", [], "the account cannot read its session state")])
        table: list = []
        ctl.states({"json": False, "follow": False}, [{"address": "h/a"}], call=lambda p, **kw: {"messages": [record("unreadable")]},
                   cfg={"channel": "c", "state_channel": "s", "relay_url": "x"}, out=table.append, now=lambda: NOW)
        self.assertTrue(any("unknown" in ln and "0 sessions" in ln and "cannot read its session state" in ln for ln in table), table)


class Wire(unittest.TestCase):
    def test_what_the_watcher_posts_the_validator_takes_and_the_row_reads(self):
        with tempfile.TemporaryDirectory() as d:
            file = os.path.join(d, "session-state.json")
            with open(file, "w") as fh:
                fh.write("{broken")
            posts: list = []
            w = cs.StateWatcher(address="h/a", post=posts.append, file=file, proc=d, now=lambda: NOW, log=lambda m: None)
            self.assertTrue(w.tick())
            posted = posts[0]
            self.assertEqual(posted["sessions"], "unreadable")
            self.assertNotIsInstance(posted["sessions"], list, "a list-only reader drops the record: the last good one stands")
            got = ctl.state_record_of({"content": json.dumps(posted)}, {"h/a"})
            self.assertEqual(ctl.state_row("h/a", got, NOW)["state"], "unknown")

    def test_the_constant_is_one_word_on_both_sides(self):
        self.assertEqual(cs.UNREADABLE, ctl.UNREADABLE)


class Board(unittest.TestCase):
    def test_the_fleet_attention_of_an_unreadable_account_is_failed_never_none(self):
        row = ctl.state_row("h/a", ctl.state_record_of(record("unreadable"), {"h/a"}), NOW)
        out = fleet.attention_data({k: v for k, v in row.items() if k != "address"}, {"jobs": {"status": "ok", "jobs": []}})
        self.assertIsInstance(out, str)
        self.assertIn("the account cannot read its session state", out)


if __name__ == "__main__":
    unittest.main()
