#!/usr/bin/env python3
"""tools/fabric/memory_horizons.py (ADR-050 rule 8): the review horizons a drain lists, the state file it keeps beside the
memory server's logs, and the wiring in the drain report. Every case builds its own corpus and state in a scratch directory."""
from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
import memory_horizons as mh  # noqa: E402

STAMP = "2026-10-11"


def rd(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def slice_text(klass: str, sections: dict[str, str | None]) -> str:
    body = "".join(f"## {h}\n\nText of {h}.\n\n" + (f"*Observed {d} (python-dev)*\n\n" if d else "") for h, d in sections.items())
    return f'---\nrole: "python-dev"\nclass: {klass}\ntopic: "t"\ndescription: "d"\ntier: 2\nknowledge_scope: full\n---\n\n{body}'


class Scratch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="horizons-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def corpus(self, files: dict[str, str]) -> str:
        root = os.path.join(self.tmp, "memory")
        for rel, text in files.items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        return root

    @staticmethod
    def key_of(rel: str) -> str:
        return "memory/" + rel


class Horizons(Scratch):
    def rows(self):
        root = self.corpus({
            "python-dev/solution/s.md": slice_text("solution", {"Old solution": "2026-09-01", "Fresh solution": "2026-10-05", "Edge solution": "2026-09-11"}),
            "python-dev/workflow/w.md": slice_text("workflow", {"Old workflow": "2026-07-01", "Edge workflow": "2026-07-13"}),
            "python-dev/domain/d.md": slice_text("domain", {"Ancient domain": "2020-01-01", "Undated": None}),
        })
        return root, mh.rows_of({"f": root}, {"f": self.key_of})

    def test_a_solution_is_aged_after_30_days_and_a_workflow_after_90_and_a_domain_never(self):
        _root, rows = self.rows()
        out = mh.horizons(rows, {"since": "2026-01-01", "reads": {}}, STAMP)
        aged = {a["key"].partition("#")[2]: a for a in out["aged"]}
        self.assertEqual(sorted(aged), ["Old solution", "Old workflow"])      # 30 days exactly (Sep 11) and 90 (Jul 13) are not older
        self.assertEqual((aged["Old solution"]["days"], aged["Old solution"]["horizon_days"]), (40, 30))
        self.assertEqual(aged["Old workflow"]["horizon_days"], 90)

    def test_a_confirmation_re_dates_the_tail_and_the_section_leaves_the_list(self):
        root, rows = self.rows()
        with open(os.path.join(root, "python-dev/solution/s.md"), encoding="utf-8") as fh:
            text = fh.read().replace("2026-09-01", "2026-10-09")
        with open(os.path.join(root, "python-dev/solution/s.md"), "w", encoding="utf-8") as fh:
            fh.write(text)
        out = mh.horizons(mh.rows_of({"f": root}, {"f": self.key_of}), {"since": "2026-01-01", "reads": {}}, STAMP)
        self.assertNotIn("Old solution", [a["key"].partition("#")[2] for a in out["aged"]])

    def test_a_section_with_no_read_in_8_weeks_is_unread_once_the_state_has_watched_that_long(self):
        _root, rows = self.rows()
        keys = {r["key"].partition("#")[2]: r["key"] for r in rows}
        state = {"since": "2026-08-01", "reads": {keys["Old solution"]: "2026-10-01", keys["Fresh solution"]: "2026-08-16", keys["Edge solution"]: "2026-08-15"}}
        out = mh.horizons(rows, state, STAMP)
        names = {u["key"].partition("#")[2]: u["last_read"] for u in out["unread"]}
        self.assertNotIn("Old solution", names)                    # read 10 days ago
        self.assertNotIn("Fresh solution", names)                  # 56 days ago exactly: not past 8 weeks
        self.assertEqual(names["Edge solution"], "2026-08-15")     # 57 days
        self.assertIsNone(names["Ancient domain"])                 # never read, and the state has watched since August
        self.assertIsNone(out["unread_from"])

    def test_before_the_state_has_watched_8_weeks_nothing_is_unread_and_the_day_it_can_begin_is_said(self):
        _root, rows = self.rows()
        out = mh.horizons(rows, {"since": "2026-10-01", "reads": {}}, STAMP)
        self.assertEqual(out["unread"], [])
        self.assertEqual(out["unread_from"], "2026-11-26")
        out = mh.horizons(rows, {"since": "2026-08-16", "reads": {}}, STAMP)      # 56 days: it has watched long enough
        self.assertTrue(out["unread"])

    def test_an_unreadable_slice_is_not_a_row(self):
        root = self.corpus({"python-dev/solution/s.md": slice_text("solution", {"A": "2026-10-01"})})
        os.chmod(os.path.join(root, "python-dev/solution"), 0o000)
        self.addCleanup(os.chmod, os.path.join(root, "python-dev/solution"), 0o755)
        if os.access(os.path.join(root, "python-dev/solution"), os.R_OK):
            self.skipTest("the process reads through file modes")
        self.assertEqual(mh.rows_of({"f": root}, {"f": self.key_of}), [])


class Reads(Scratch):
    def corpora(self):
        root = self.corpus({"python-dev/solution/s.md": slice_text("solution", {"One": "2026-10-01", "Two": "2026-10-01"})})
        return {"f": root}

    def test_an_id_credits_the_heading_at_its_position_and_ids_that_name_no_section_are_ignored(self):
        state = {"since": "2026-01-01", "reads": {}}
        ids = {"f:python-dev/solution/s#2": 3, "f:python-dev/solution/s#9": 1, "f:../etc/x#1": 1, "p:python-dev/solution/s#1": 1, "junk": 1}
        mh.record_reads(state, ids, self.corpora(), STAMP, {"f": self.key_of})
        self.assertEqual(state["reads"], {"memory/python-dev/solution/s.md#Two": STAMP})

    def test_a_later_read_date_is_never_replaced_by_an_earlier_stamp(self):
        state = {"since": "2026-01-01", "reads": {"memory/python-dev/solution/s.md#Two": "2026-10-12"}}
        mh.record_reads(state, {"f:python-dev/solution/s#2": 1}, self.corpora(), STAMP, {"f": self.key_of})
        self.assertEqual(state["reads"]["memory/python-dev/solution/s.md#Two"], "2026-10-12")


class State(Scratch):
    def test_no_file_starts_at_the_stamp_and_a_file_that_is_no_state_starts_over_and_says_so(self):
        path = os.path.join(self.tmp, "state", mh.STATE_FILE)
        self.assertEqual(mh.reads_state(path, STAMP), ({"since": STAMP, "reads": {}}, "new"))
        os.makedirs(os.path.dirname(path))
        for bad in ("{not json", "[]", '{"since": "yesterday", "reads": {}}', '{"since": "2026-01-01", "reads": []}'):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(bad)
            self.assertEqual(mh.reads_state(path, STAMP), ({"since": STAMP, "reads": {}}, "unreadable"), bad)

    def test_the_state_is_written_atomically_private_and_without_the_keys_of_sections_that_are_gone(self):
        path = os.path.join(self.tmp, "state", mh.STATE_FILE)
        state = {"since": "2026-08-01", "reads": {"memory/a.md#A": "2026-10-01", "memory/gone.md#G": "2026-09-01", "memory/b.md#B": "2026-10-02"}}
        mh.save_reads(path, state, {"memory/a.md#A", "memory/b.md#B"})
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(os.listdir(os.path.dirname(path)), [mh.STATE_FILE])
        back, status = mh.reads_state(path, STAMP)
        self.assertEqual((status, back["since"], sorted(back["reads"])), ("ok", "2026-08-01", ["memory/a.md#A", "memory/b.md#B"]))

    def test_a_write_that_fails_leaves_the_old_state_and_no_temporary_file(self):
        path = os.path.join(self.tmp, "state", mh.STATE_FILE)
        mh.save_reads(path, {"since": "2026-08-01", "reads": {"k#h": "2026-10-01"}}, {"k#h"})
        before = rd(path)
        with self.assertRaises(TypeError):
            mh.save_reads(path, {"since": "2026-08-01", "reads": {"k#h": object()}}, {"k#h"})
        self.assertEqual((rd(path), os.listdir(os.path.dirname(path))), (before, [mh.STATE_FILE]))


if __name__ == "__main__":
    unittest.main()
