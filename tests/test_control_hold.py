#!/usr/bin/env python3
"""The fleet hold on the control plane (agent-fabric ADR-037 rule 13, ADR-029): the `hold` and `unhold` actions
(tools/fabric/control/hold.py), fabric-ctl's side of them, the `jobs` op's `hold` and tools/fabric/hold_view.py, which the job
tool, fabric-fresh and fabric-status read a hold with. The job tool's, fabric-fresh's and fabric-status's own refusals are in
test_jobs_switch.py, test_fabric_fresh_cli.py and test_fabric_status_cli.py. A scratch state directory per test, set in the
environment and removed with it."""
from __future__ import annotations

import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402

own_instance_tree()
from control import agentd, ctl, ops, sign  # noqa: E402
from control import hold as hold_mod  # noqa: E402
from control import jobs as cj  # noqa: E402
import hold_view  # noqa: E402

DECISION = "01a18d02-edd3-7bef-8fe9-965718c256b5"
OPERATOR = "h1/op"


class Scratch(unittest.TestCase):
    def setUp(self):
        self.state = tempfile.mkdtemp(prefix="control-hold-")
        self.addCleanup(shutil.rmtree, self.state, ignore_errors=True)
        saved = os.environ.get("AGENT_FABRIC_STATE_DIR")
        os.environ["AGENT_FABRIC_STATE_DIR"] = self.state
        self.addCleanup(lambda: os.environ.__setitem__("AGENT_FABRIC_STATE_DIR", saved) if saved is not None else os.environ.pop("AGENT_FABRIC_STATE_DIR", None))
        self.identity = hold_mod.identity_module()
        self.login = self.identity.current_agent()
        self.path = self.identity.hold_path()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def record(self):
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def req(self, op="hold", **args):
        return {"op": op, "id": "r1", "from": OPERATOR, **({"args": args} if args or op == "hold" else {})}


class Ops(Scratch):
    def test_both_are_actions_the_wire_knows_and_the_agent_answers(self):
        for op in ("hold", "unhold"):
            self.assertIn(op, ops.OPS)
            self.assertIn(op, sign.ACTION_OPS)
            self.assertNotIn(op, ops.PUBLIC_OPS)

    def test_hold_writes_the_record_with_the_signers_address_and_a_second_restates(self):
        r = hold_mod.hold(self.req(reason="release freeze", decision=DECISION))
        self.assertEqual(r["status"], "held")
        rec = self.record()
        self.assertEqual((rec["agent"], rec["reason"], rec["decision"], rec["set_by"]), (self.login, "release freeze", DECISION, OPERATOR))
        self.assertEqual(r["hold"], rec)
        r = hold_mod.hold({**self.req(reason="a new reason"), "from": "h1/other"})
        self.assertEqual(r["status"], "held")
        rec = self.record()
        self.assertEqual((rec["reason"], rec["decision"], rec["set_by"]), ("a new reason", None, "h1/other"))

    def test_hold_refuses_what_the_record_cannot_hold_and_writes_nothing(self):
        for label, args in (("no reason", {}), ("a number", {"reason": 5}), ("empty", {"reason": "  "}), ("two lines", {"reason": "a\nb"}),
                            ("too long", {"reason": "x" * 201}), ("a bad decision", {"reason": "r", "decision": "j467"}),
                            ("a decision that is not text", {"reason": "r", "decision": 5}), ("an extra key", {"reason": "r", "force": True})):
            r = hold_mod.hold(self.req(**args))
            self.assertEqual(r["status"], "refused", label)
            self.assertFalse(os.path.exists(self.path), label)
        self.assertEqual(hold_mod.hold({"op": "hold", "from": OPERATOR})["status"], "refused")   # no args at all
        self.assertEqual(hold_mod.hold({"op": "hold", "args": {"reason": "r"}})["status"], "refused")   # the signer unnamed
        # The positive control: the longest allowed reason is held.
        self.assertEqual(hold_mod.hold(self.req(reason="x" * 200))["status"], "held")

    def test_unhold_releases_a_hold_and_says_none_when_there_was_none(self):
        self.assertEqual(hold_mod.unhold(self.req("unhold")), {"status": "none"})
        hold_mod.hold(self.req(reason="r"))
        self.assertEqual(hold_mod.unhold(self.req("unhold")), {"status": "released"})
        self.assertFalse(os.path.exists(self.path))
        self.assertEqual(hold_mod.unhold(self.req("unhold")), {"status": "none"})
        self.assertEqual(hold_mod.unhold({**self.req("unhold"), "args": {"x": 1}})["status"], "refused")

    def test_unhold_lifts_a_hold_file_nobody_can_read(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertEqual(hold_mod.unhold(self.req("unhold")), {"status": "released"})
        self.assertFalse(os.path.exists(self.path))

    def test_the_daemon_dispatches_both_with_the_signers_address(self):
        ctx = {"me": {"address": f"h1/{self.login}"}, "started": "2026-10-28T00:00:00.000Z", "home": self.state, "root": HERE}
        held = agentd.answer({"op": "hold", "id": "r1", "from": OPERATOR, "args": {"reason": "freeze"}}, ctx)
        self.assertEqual(held["data"]["hold"]["status"], "held", held)
        self.assertEqual(self.record()["set_by"], OPERATOR)
        self.assertEqual(agentd.answer({"op": "unhold", "id": "r2", "from": OPERATOR}, ctx)["data"]["unhold"]["status"], "released")
        self.assertEqual(agentd.answer({"op": "hold", "id": "r3", "from": OPERATOR}, ctx)["data"]["hold"]["status"], "refused")


class View(Scratch):
    def test_read_and_words(self):
        self.assertIsNone(hold_view.read(self.identity))
        self.identity.set_hold("release freeze", set_by=OPERATOR, decision=DECISION)
        rec = hold_view.read(self.identity)
        self.assertEqual(rec["reason"], "release freeze")
        then = datetime.datetime.fromisoformat(rec["set_at"].replace("Z", "+00:00"))
        self.assertEqual(hold_view.words(rec, then + datetime.timedelta(hours=3)),
                         f"release freeze (decision {DECISION}, set by {OPERATOR}, 3 h ago)")
        self.assertEqual(hold_view.words({"reason": "bare"}), "bare")

    def test_a_hold_file_that_cannot_be_read_is_a_hold_never_none(self):
        for body in ("{not json", "[1]", '{"reason": 5}', '{"reason": "r", "agent": "someone-else"}'):
            with open(self.path, "w", encoding="utf-8") as fh:
                fh.write(body)
            rec = hold_view.read(self.identity)
            self.assertIsNotNone(rec, body)
            self.assertIn("unreadable", rec, body)
            self.assertTrue(hold_view.words(rec).startswith("hold unreadable: "), body)
        os.remove(self.path)
        self.assertIsNone(hold_view.read(self.identity))    # the positive control: no file is no hold


class JobsOp(Scratch):
    LISTED = json.dumps([{"id": "j1", "state": "queued", "title": "a"}])

    @staticmethod
    def run(argv, **kw):
        return SimpleNamespace(stdout=JobsOp.LISTED, stderr="", returncode=0)

    def test_the_answer_carries_the_hold_or_null_and_a_corrupt_file_counts(self):
        self.assertIsNone(cj.jobs(run=self.run)["hold"])
        self.identity.set_hold("release freeze", set_by=OPERATOR, decision=DECISION)
        got = cj.jobs(run=self.run)
        self.assertEqual((got["hold"]["reason"], got["hold"]["set_by"], len(got["jobs"])), ("release freeze", OPERATOR, 1))
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertIn("unreadable", cj.jobs(run=self.run)["hold"])


class Ctl(Scratch):
    def test_parse_hold_needs_a_reason_and_allows_all(self):
        a = ctl.parse_args(["all", "hold", "--reason", "release freeze", "--decision", DECISION])
        self.assertEqual((a["op"], a["targets"], a["reason"], a["decision"]), ("hold", ["all"], "release freeze", DECISION))
        self.assertEqual(ctl.parse_args(["all", "hold", "--reason=why"])["reason"], "why")
        self.assertEqual(ctl.parse_args(["all", "unhold"])["op"], "unhold")
        for argv, why in ((["all", "hold"], "--reason"), (["all", "hold", "--reason"], "--reason"), (["all", "hold", "--reason", "a\nb"], "one non-empty line"),
                           (["all", "hold", "--reason", "x" * 201], "200"), (["all", "hold", "--reason", "r", "--decision", "j467"], "MESSAGE-ID"),
                           (["all", "hold", "--reason", "r", "--decision"], "MESSAGE-ID"), (["all", "unhold", "--reason", "r"], "hold only"),
                           (["all", "status", "--decision", DECISION], "hold only")):
            with self.assertRaisesRegex(ctl.CtlError, why, msg=argv):
                ctl.parse_args(argv)
        with self.assertRaisesRegex(ctl.CtlError, "one login"):    # the positive control: jobs-add still refuses all
            ctl.parse_args(["all", "jobs-add", "a title"])

    def test_the_request_carries_the_reason_and_decision_only(self):
        cfg = {"ttl_s": 60}
        a = ctl.parse_args(["all", "hold", "--reason", "r", "--decision", DECISION])
        r = ctl.build_request(a, id="i", from_=OPERATOR, to="*", cfg=cfg)
        self.assertEqual((r["op"], r["args"]), ("hold", {"reason": "r", "decision": DECISION}))
        r = ctl.build_request(ctl.parse_args(["all", "hold", "--reason", "r"]), id="i", from_=OPERATOR, to="*", cfg=cfg)
        self.assertEqual(r["args"], {"reason": "r"})
        self.assertNotIn("args", ctl.build_request(ctl.parse_args(["all", "unhold"]), id="i", from_=OPERATOR, to="*", cfg=cfg))

    def fleet(self, silent=("c",)):
        """Three placed accounts, each with a state directory of its own; `silent` ones never answer. Returns run(argv)."""
        reg = os.path.join(self.state, "registry.json")
        with open(reg, "w", encoding="utf-8") as fh:
            json.dump({"hosts": {"h1": {"operator": "op"}}, "placement": {"a": "h1", "b": "h1", "c": "h1"}}, fh)
        real = self.identity
        states = {}

        class Account:
            """This account's view of identity.py: its login's state directory, as its control agent's would be."""
            def __init__(self, login):
                self.login = login

            def set_hold(self, reason, set_by, decision=None):
                return real.set_hold(reason, set_by=set_by, decision=decision, agent=self.login)

            def clear_hold(self):
                return real.clear_hold(agent=self.login)
        self.accounts = {l: Account(l) for l in ("a", "b", "c")}
        sent: list[dict] = []

        def call(path, method="GET", body=None, **_kw):
            if path.startswith("/api/send"):
                req = json.loads(json.loads(body)["content"])
                sent.append(req)
                states.clear()
                for login, acct in self.accounts.items():
                    if login in silent:
                        continue
                    states[login] = {"v": 1, "kind": "reply", "id": f"r-{login}", "in_reply_to": req["id"], "from": f"h1/{login}", "op": req["op"], "ok": True,
                                     "data": {req["op"]: getattr(hold_mod, req["op"])({**req, "from": req["from"]}, identity=acct)}}
                return {"id": "m1"}
            return {"messages": [{"id": f"x-{l}", "content": json.dumps(r)} for l, r in states.items()]}
        keep = (ctl.signing_key, ctl.sign_request)
        ctl.signing_key, ctl.sign_request = (lambda *a, **k: {"key": "k"}), (lambda r, k: r)
        self.addCleanup(lambda: setattr(ctl, "signing_key", keep[0]) or setattr(ctl, "sign_request", keep[1]))

        def run(argv):
            out, err = [], []
            rc = ctl.main([*argv, "--timeout", "5"], registry=reg, call=call, out=out.append, err=err.append, sleep=lambda s: None,
                          who={"host": "h1", "agent": "op", "project": None}, token="tok")
            return rc, "\n".join(out), "\n".join(err), sent
        return run

    def hold_of(self, login):
        return self.identity.read_hold(login)

    def test_hold_all_then_unhold_round_trips_and_names_the_account_that_did_not_answer(self):
        run = self.fleet()
        rc, out, err, sent = run(["all", "hold", "--reason", "release freeze", "--decision", DECISION])
        self.assertEqual(rc, 1, "an account that did not confirm fails the run")
        self.assertEqual((sent[-1]["op"], sent[-1]["args"]), ("hold", {"reason": "release freeze", "decision": DECISION}))
        lines = {l.split()[0]: l for l in out.splitlines() if l.strip()}
        self.assertIn("held", lines["a"])
        self.assertIn("held", lines["b"])
        self.assertIn("no answer", lines["c"])
        for login in ("a", "b"):
            self.assertEqual(self.hold_of(login)["set_by"], "h1/op", login)
        self.assertIsNone(self.hold_of("c"), "the silent account is not held")
        rc, out, err, sent = run(["all", "unhold"])
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"(?m)^c\s+no answer")
        self.assertRegex(out, r"(?m)^a\s+released")
        self.assertEqual((self.hold_of("a"), self.hold_of("b")), (None, None))
        rc, out, err, sent = run(["a", "b", "unhold"])
        self.assertEqual(rc, 0, "none is a good answer")
        self.assertRegex(out, r"(?m)^a\s+none")

    def test_an_all_fleet_that_answers_is_a_clean_run(self):
        run = self.fleet(silent=())
        self.assertEqual(run(["all", "hold", "--reason", "r"])[0], 0)
        self.assertEqual(run(["all", "unhold"])[0], 0)

    def test_a_refusal_by_an_account_fails_the_run_and_says_why(self):
        self.assertEqual(ctl.ACTION_OK["hold"], ["held"])
        self.assertEqual(ctl.ACTION_OK["unhold"], ["released", "none"])
        rows = ctl.rows([{"login": "a", "host": "h1", "address": "h1/a"}],
                        [{"kind": "reply", "from": "h1/a", "op": "hold", "data": {"hold": {"status": "refused", "reason": "nope"}}}])
        self.assertRegex(ctl.table("hold", rows), r"refused\s+nope")

    def test_the_jobs_table_says_held_beside_a_held_account_and_only_that_one(self):
        def jobs_row(login, hold):
            return {"kind": "reply", "from": f"h1/{login}", "op": "jobs", "data": {"jobs": {"status": "ok", "jobs": [], "hold": hold}}}
        expected = [{"login": l, "host": "h1", "address": f"h1/{l}"} for l in ("a", "b", "c")]
        rec = {"reason": "release freeze", "decision": DECISION, "set_by": OPERATOR, "set_at": "2026-10-30T10:00:00Z"}
        table = ctl.table("jobs", ctl.rows(expected, [jobs_row("a", rec), jobs_row("b", None), jobs_row("c", {"unreadable": "x is not valid JSON"})]))
        self.assertRegex(table, r"(?m)^a\s+HELD\s+release freeze \(decision " + DECISION)
        self.assertRegex(table, r"(?m)^c\s+HELD\s+hold unreadable: x is not valid JSON")
        self.assertNotRegex(table, r"(?m)^b\s+HELD")
        self.assertRegex(table, r"(?m)^b\s+no open jobs")


if __name__ == "__main__":
    unittest.main()
