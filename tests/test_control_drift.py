#!/usr/bin/env python3
"""The control agent's `drift` (a read): tools/fabric/control/ops/account_drift.py over tools/fabric/account_drift.py,
the daemon's cache and beside-the-loop wiring, and fabric-ctl's side (argv, timeout, row, table). The check's own classes
are tests/test_account_drift.py's; here a scratch record, a scratch home and a stand-in bootstrap.py (its dry-run lines
chosen by the case) show what reaches a reply and what reaches a terminal."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402

own_instance_tree()
from control import agentd, ctl, ops  # noqa: E402

STUB = "import os, sys\nsys.stdout.write(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dry.txt')).read())\n"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class Scratch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="control-drift-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.home = os.path.join(self.dir, "home")
        self.state = os.path.join(self.dir, "state")
        self.root = os.path.join(self.dir, "root")
        fab = os.path.join(self.root, "tools", "fabric")
        for d in (self.home, self.state, fab):
            os.makedirs(d)
        with open(os.path.join(fab, "bootstrap.py"), "w") as f:
            f.write(STUB)
        self.dry("")
        self.a = os.path.join(self.home, "a.md")
        with open(self.a, "w") as f:
            f.write("a")
        self.record({self.a: sha(b"a")})

    def dry(self, text: str) -> None:
        with open(os.path.join(self.root, "tools", "fabric", "dry.txt"), "w") as f:
            f.write(text)

    def record(self, doc: dict) -> None:
        with open(os.path.join(self.state, "fabric-written.json"), "w") as f:
            json.dump(doc, f)

    def ctx(self, **more) -> dict:
        return {"home": self.home, "root": self.root, "drift_opts": {"state": self.state}, **more}


class Op(Scratch):
    def test_a_clean_account_is_ok_with_whole_counts(self):
        self.assertEqual(ops.collect("drift", self.ctx()),
                         {"drift": {"status": "ok", "counts": {"ok": 1, "edited": 0, "missing": 0, "unreadable": 0, "stale": 0}, "findings": []}})

    def test_drift_is_said_with_the_findings(self):
        with open(self.a, "w") as f:
            f.write("changed")
        self.dry(f"  +  {self.home}/new (would write)\n")
        got = ops.collect("drift", self.ctx())["drift"]
        self.assertEqual((got["status"], got["counts"]["edited"], got["counts"]["stale"]), ("drift", 1, 1))
        self.assertEqual([(f["kind"], f["path"]) for f in got["findings"]], [("edited", self.a), ("stale", f"{self.home}/new")])

    def test_a_check_that_cannot_be_made_is_failed_with_its_reason_never_ok(self):
        os.unlink(os.path.join(self.state, "fabric-written.json"))
        got = ops.collect("drift", self.ctx())["drift"]
        self.assertEqual(got["status"], "failed")
        self.assertIn("no record at", got["reason"])
        self.assertNotIn("counts", got)

    def test_the_findings_are_capped_and_the_counts_stay_whole(self):
        self.dry("".join(f"  +  {self.home}/n{i} (would write)\n" for i in range(ops.FINDINGS_MAX + 50)))
        got = ops.collect("drift", self.ctx())["drift"]
        self.assertEqual((len(got["findings"]), got["findings_total"], got["truncated"], got["counts"]["stale"]),
                         (ops.FINDINGS_MAX, ops.FINDINGS_MAX + 50, True, ops.FINDINGS_MAX + 50))

    def test_no_hash_or_content_is_in_the_reply(self):
        with open(self.a, "w") as f:
            f.write("a secret body")
        text = json.dumps(ops.collect("drift", self.ctx()))
        self.assertNotIn("secret body", text)
        self.assertNotIn(sha(b"a"), text)
        self.assertNotIn(sha(b"a secret body"), text)

    def test_the_daemons_cached_read_answers_when_it_has_one(self):
        seen = []
        got = ops.collect("drift", self.ctx(drift_cached=lambda: seen.append(1) or {"status": "ok", "counts": {}, "findings": []}))
        self.assertEqual((seen, got["drift"]["status"]), ([1], "ok"))

    def test_the_daemon_runs_it_beside_the_loop_and_answers_it_as_an_unsigned_read(self):
        self.assertIn("drift", agentd.BESIDE_LOOP_OPS)
        reply = agentd.answer({"op": "drift", "id": "r1"}, self.ctx(me={"address": "h/a"}, started="2026-10-10T00:00:00.000Z"))
        self.assertEqual(reply["data"]["drift"]["status"], "ok")
        self.assertEqual(reply["op"], "drift")


class Ctl(Scratch):
    def test_argv_timeout_and_the_closed_sets(self):
        a = ctl.parse_args(["all", "drift"])
        self.assertEqual((a["op"], a["timeout"]), ("drift", 90))
        self.assertIn("drift", ops.OPS)
        self.assertNotIn("drift", ops.PUBLIC_OPS)
        self.assertNotIn("drift", ctl.ACTION_OPS)
        with self.assertRaises(ctl.CtlError):
            ctl.parse_args(["all", "drift", "--sweep"])

    def rows(self, data: dict) -> list:
        return ctl.rows([{"login": "a", "host": "h", "address": "h/a"}],
                        [{"kind": "reply", "from": "h/a", "op": "drift", "latency_ms": 3, "data": {"drift": data}}])

    def test_the_table_has_the_counts_then_a_line_per_finding(self):
        with open(self.a, "w") as f:
            f.write("changed")
        self.dry(f"  +  {self.home}/new (would write)\n")
        text = ctl.table("drift", self.rows(ops.collect("drift", self.ctx())["drift"]))
        head, counts, *found = text.splitlines()
        self.assertIn("stale", head)
        self.assertEqual(counts.split(), ["a", "drift", "0", "1", "0", "0", "1"])
        self.assertEqual([ln.split()[0] for ln in found], ["edited", "stale"])
        self.assertIn(self.a, found[0])

    def test_what_an_account_sent_reaches_the_terminal_escaped(self):
        hostile = "/h/\x1b[31mred\x07\nnext"
        text = ctl.table("drift", self.rows({"status": "drift", "counts": {"ok": 0, "edited": 1, "missing": 0, "unreadable": 0, "stale": 0},
                                             "findings": [{"kind": "edited", "path": hostile, "detail": "\x1b]0;x\x07"}]}))
        for bad in ("\x1b", "\x07"):
            self.assertNotIn(bad, text)
        self.assertEqual(len(text.splitlines()), 3, "a newline in a path does not make a line")

    def test_failed_truncated_and_unanswered_rows_say_so(self):
        failed = ctl.table("drift", self.rows({"status": "failed", "reason": "no record at /x"}))
        self.assertIn("failed", failed.splitlines()[1])
        self.assertIn("no record at /x", failed.splitlines()[1])
        cut = ctl.table("drift", self.rows({"status": "drift", "counts": {"ok": 0, "edited": 0, "missing": 0, "unreadable": 0, "stale": 150},
                                            "findings": [{"kind": "stale", "path": "/p"}], "findings_total": 150, "truncated": True}))
        self.assertIn("150 findings in all", cut)
        none = ctl.table("drift", ctl.rows([{"login": "a", "host": "h", "address": "h/a"}], []))
        self.assertIn("no answer", none)


if __name__ == "__main__":
    unittest.main()
