#!/usr/bin/env python3
"""control_carrier "interweave" for the asks a login makes of the control plane: the presence check (control/presence.py)
and the job queue's holder (control/queue.py: pool-list, pool-claim, job-state) go through this account's own agentd socket
alone. The relay is a callable that records every call and refuses it, so "never asked" is `calls == []`, not a green run
that the relay happened to survive. The asker's end is a real control_link.Server over the fake InterWeave network of
test_gzcoord_carrier_control_link, as tests/test_control_w12_dual.py has it.

The config's own parse (the third word, and a typo still refused) is held here too: agentd.control_config.
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
import test_gzcoord_carrier_control_link as base  # noqa: E402
from control import agentd, gzcoord, pool, presence, queue  # noqa: E402
from gzcoord.carrier import control_link as cc  # noqa: E402
from instance_fixtures import own_instance_tree  # noqa: E402
own_instance_tree()

ALICE, BOB = "h/alice", "h/bob"
ONLINE = {"status": "ok", "online": True, "sessions": 1, "since": "2026-11-13T07:00:00.000Z", "role": "python-dev", "project": "x"}
CFG = {"relay_url": "http://relay.invalid", "channel": "fabric:control", "state_channel": "fabric:state:control", "ttl_s": 30,
       "control_carrier": "interweave"}


# A real new_id never repeats, across asks and across tests.
IDS = itertools.count(1)


class Relay:
    """Refuses every connection and records the attempt."""

    def __init__(self) -> None:
        self.calls: list = []

    def __call__(self, path, method="GET", body=None, **kw):
        self.calls.append((method, path))
        raise gzcoord.ApiError(f"{path} -> refused", connection_refused=True)


class Net(base.Net):
    """alice asks, bob answers over InterWeave; alice's agentd socket is up under XDG_RUNTIME_DIR."""

    def setUp(self) -> None:
        super().setUp()
        self.alice, self.bob = self.node("alice"), self.node("bob")
        runtime = self.scratch()
        self.server = cc.Server(os.path.join(runtime, "agent-fabric", "control.sock"), self.alice.carrier, ALICE)
        self.server.start()
        self.addCleanup(self.server.stop)
        patch = mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime})
        patch.start()
        self.addCleanup(patch.stop)
        self.relay = Relay()

    def bob_answers(self, data: dict, op: str, who: str = BOB) -> None:
        def run() -> None:
            if base.until(lambda: self.bob.requests):
                req = self.bob.requests[0][0]
                self.bob.carrier.reply(req, {"v": 1, "kind": "reply", "id": "a1", "in_reply_to": req["id"], "from": who, "op": op,
                                             "ts": "2026-11-13T07:00:01.000Z", "ok": True, "data": data})
        t = threading.Thread(target=run, daemon=True)
        t.start()
        self.addCleanup(t.join, 5)


class Presence(Net):
    def ask(self, **kw):
        # A mode reader that fails the test: under interweave the relay is off whatever the mode file says.
        def never_read():
            raise AssertionError("the transport mode file is not read under interweave")
        return presence.ask_presence(from_=ALICE, to=[BOB], expect=[BOB], wait_ms=kw.pop("wait_ms", 4000), cfg=CFG, new_id=lambda: "pq1",
                                     call=self.relay, read_mode=never_read, **kw)

    def test_presence_is_answered_by_the_carrier_and_the_relay_is_never_asked(self):
        self.bob_answers({"presence": ONLINE}, "presence")
        self.assertEqual(self.ask(), {BOB: ONLINE})
        self.assertEqual(self.relay.calls, [])
        self.assertEqual(self.bob.requests[0][0]["op"], "presence")

    def test_no_answer_is_unknown_never_offline_and_still_no_relay_call(self):
        self.assertEqual(self.ask(wait_ms=300), {BOB: None})
        self.assertEqual(self.relay.calls, [])

    def test_the_senders_own_address_is_asked_through_the_loop_back(self):
        targets: list = []

        def open_leg(request, to, wait_s):
            targets.extend(to)
            return mock.Mock(lost=False, replies=lambda t: [(a, {"kind": "reply", "in_reply_to": request["id"], "from": a, "data": {"presence": ONLINE}}) for a in to])
        got = presence.ask_presence(from_=ALICE, to="*", expect=[ALICE, BOB], wait_ms=1500, cfg=CFG, new_id=lambda: "o1", call=self.relay,
                                    open_leg=open_leg, read_mode=lambda: "relay-record")
        self.assertEqual((targets, got, self.relay.calls), ([ALICE, BOB], {ALICE: ONLINE, BOB: ONLINE}, []))

    def test_a_socket_that_is_not_there_is_said_and_the_relay_is_still_not_asked(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("XDG_RUNTIME_DIR")
            with self.assertRaises(cc.Down) as cm:
                self.ask(wait_ms=200)
        self.assertIn("interweave:", str(cm.exception))
        self.assertIn("XDG_RUNTIME_DIR is not set", str(cm.exception))
        self.assertEqual(self.relay.calls, [])

    def test_a_reply_claiming_another_sender_is_not_taken(self):
        self.bob_answers({"presence": ONLINE}, "presence", who=ALICE)
        self.assertEqual(self.ask(wait_ms=1500), {BOB: None})

    def test_relay_mode_still_posts_to_the_relay_the_positive_control(self):
        with self.assertRaises(gzcoord.ApiError):
            presence.ask_presence(from_=ALICE, to=[BOB], expect=[BOB], wait_ms=200, cfg={**CFG, "control_carrier": "relay"}, new_id=lambda: "r",
                                  call=self.relay, read_mode=lambda: "relay-record")
        self.assertEqual(self.relay.calls[0][0], "POST")


class Holder(Net):
    def test_a_pool_list_is_answered_by_the_carrier_with_the_relay_refusing(self):
        self.bob_answers({"pool-list": {"status": "ok", "pool": []}}, "pool-list")
        got = queue.ask_holder(call=self.relay, cfg=CFG, from_=ALICE, holder=BOB, op="pool-list", args={"role": "python-dev"}, new_id=lambda: "qq1", wait_ms=4000)
        self.assertEqual((got, self.relay.calls), ({"status": "ok", "pool": []}, []))

    def test_the_account_that_holds_the_pool_is_asked_through_the_loop_back_not_the_relay(self):
        targets: list = []

        def open_leg(request, to, wait_s):
            targets.extend(to)
            return mock.Mock(lost=False, replies=lambda t: [(ALICE, {"kind": "reply", "in_reply_to": request["id"], "from": ALICE, "data": {"pool-list": {"status": "ok"}}})])
        got = queue.ask_holder(call=self.relay, cfg=CFG, from_=ALICE, holder=ALICE, op="pool-list", args={}, new_id=lambda: "q", wait_ms=500, open_leg=open_leg)
        self.assertEqual((got, targets, self.relay.calls), ({"status": "ok"}, [ALICE], []))

    def test_no_answer_is_none_and_a_reply_of_another_sender_is_not_the_answer(self):
        self.bob_answers({"pool-list": {"status": "ok"}}, "pool-list", who=ALICE)
        self.assertIsNone(queue.ask_holder(call=self.relay, cfg=CFG, from_=ALICE, holder=BOB, op="pool-list", args={}, new_id=lambda: "q2", wait_ms=1500))
        self.assertEqual(self.relay.calls, [])

    def test_with_no_socket_the_ask_fails_whole_and_certainly_unsent(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("XDG_RUNTIME_DIR")
            with self.assertRaises(cc.Down) as cm:
                queue.ask_holder(call=self.relay, cfg=CFG, from_=ALICE, holder=BOB, op="pool-claim", args={"id": "p1"}, new_id=lambda: "q", wait_ms=200)
        self.assertEqual(self.relay.calls, [], "no relay post to make it up")
        self.assertTrue(queue.unsent(cm.exception), "the socket was never handed the request: certainly unsent")
        self.assertIn("interweave:", str(cm.exception))
        self.assertEqual(queue.relay_error(cm.exception, CFG), str(cm.exception))

    def test_a_handed_request_that_then_failed_is_not_said_to_be_unsent(self):
        def handed(request, to, wait_s):
            raise cc.LegFailed("the operator's agentd did not finish the sends in time", handed=True)
        with self.assertRaises(cc.Down) as cm:
            queue.ask_holder(call=self.relay, cfg=CFG, from_=ALICE, holder=BOB, op="pool-list", args={}, new_id=lambda: "q", wait_ms=200, open_leg=handed)
        self.assertFalse(queue.unsent(cm.exception), "handed: it may have left")


class Cli(Net):
    """queue.py's own commands, end to end in this process: the relay refuses every connection and the holder answers by InterWeave."""

    def run_cli(self, argv, *, token="tok", wait_ms=4000):
        d = self.scratch()
        reg = os.path.join(d, "registry.json")
        with open(reg, "w", encoding="utf-8") as fh:
            json.dump({"hosts": {"h": {"operator": "user"}}, "placement": {"alice": "h", "bob": "h", "user": "h"}}, fh)
        agentd_stub = SimpleNamespace(control_config=lambda: CFG, new_id=lambda: f"q{next(IDS)}", state_dir=lambda: d, operator_addresses=lambda registry=None: ["h/user"])
        lines: list[str] = []
        env = {"HOME": d, "AGENT_FABRIC_ROOT": os.path.join(d, "ws", "fabric")}
        if token:
            env["CLAUDE_BRIDGE_AUTH_TOKEN"] = token
        with mock.patch.dict(os.environ, env), mock.patch.object(gzcoord, "synced_token", lambda: None):
            if not token:
                os.environ.pop("CLAUDE_BRIDGE_AUTH_TOKEN", None)
            cwd = os.getcwd()
            os.chdir(d)
            try:
                rc = queue.cli(argv, out=lines.append, err=lambda m: None, agentd=agentd_stub, call=self.relay, registry=reg, wait_ms=wait_ms,
                               who={"agent": "alice", "host": "h", "role": "python-dev", "project": None})
            finally:
                os.chdir(cwd)
        return rc, [json.loads(x) for x in lines]

    def holder_is_bob(self):
        return mock.patch.object(queue, "pool_holder", lambda cfg, registry=None: BOB)

    def test_pool_list_pool_claim_and_job_state_succeed_with_the_relay_refusing_every_connection(self):
        for argv, op, answer in ((["pool-list"], "pool-list", {"status": "ok", "pool": []}),
                                 (["pool-claim", "p1"], "pool-claim", {"status": "claimed", "job": {"id": "p1"}}),
                                 (["job-state", "bob", "j7"], "job-state", {"status": "ok", "job": {"id": "j7"}})):
            self.bob.requests.clear()
            self.bob_answers({op: answer}, op)
            with self.holder_is_bob():
                rc, out = self.run_cli(argv)
            self.assertEqual(rc, 0, (argv, out))
            self.assertEqual(out[0]["answer"], answer)
            self.assertEqual(self.relay.calls, [], argv)

    def test_without_a_token_the_asks_still_go_and_waits_names_the_missing_token(self):
        self.bob_answers({"pool-list": {"status": "ok", "pool": []}}, "pool-list")
        with self.holder_is_bob():
            rc, out = self.run_cli(["pool-list"], token=None)
        self.assertEqual((rc, out[0]["answer"]), (0, {"status": "ok", "pool": []}))
        # The state stream is asked of the accounts (the `state` op), so waits needs neither the relay nor a token; an account that
        # does not answer is unknown, said, never a board that reads as no claims.
        # With none of them answering there is nothing to rank by: exit 3, every account named, not a board of no waits.
        rc, out = self.run_cli(["waits"], token=None)
        self.assertEqual(rc, 3)
        self.assertIn("no account gave a state record", out[0]["error"])
        for who in ("h/alice", "h/bob", "h/user"):
            self.assertIn(who, out[0]["error"])
        self.assertEqual(self.relay.calls, [])

    def test_waits_with_the_relay_down_reads_the_op_and_says_who_did_not_answer(self):
        self.bob_answers({"state": {"address": "h/bob", "state": {"kind": "state", "v": 1, "from": "h/bob", "ts": "2026-11-13T07:00:00.000Z"}}}, "state")
        rc, out = self.run_cli(["waits"])
        self.assertEqual(rc, 0)
        self.assertEqual(out[0]["accounts"], 1)   # bob's record is the one that was given
        self.assertIn("was not asked", out[0]["unknown"]["h/user"])
        self.assertNotIn("h/bob", out[0]["unknown"])
        self.assertEqual(self.relay.calls, [])

    def test_a_holder_that_does_not_answer_is_exit_3_sent_true(self):
        with self.holder_is_bob():
            rc, out = self.run_cli(["pool-list"], wait_ms=300)
        self.assertEqual(rc, 3)
        self.assertIs(out[0]["sent"], True)
        self.assertEqual(self.relay.calls, [])


class Readers(unittest.TestCase):
    """Relay mode reads the relay's state stream: a reader that cannot read it says unknown, never an account with no sessions
    or an empty board. Under the second carrier alone the readers ask the accounts instead (test_control_state_op)."""

    def test_the_pool_claim_reader_of_a_refused_stream_is_an_error_and_not_a_record(self):
        got = pool.state_reader(call=Relay(), cfg=CFG)(ALICE)
        self.assertEqual(list(got), ["error"])
        self.assertIn("state stream could not be read", got["error"])

    def test_fabric_ctl_states_with_the_relay_refusing_asks_the_accounts_and_never_the_relay(self):
        from control import ctl
        calls = []
        with tempfile.TemporaryDirectory() as d:
            reg = os.path.join(d, "registry.json")
            with open(reg, "w", encoding="utf-8") as fh:
                json.dump({"hosts": {"h": {"operator": "op"}}, "placement": {"alice": "h"}}, fh)
            out, err = [], []
            with mock.patch.dict(os.environ, {"FABRIC_CONTROL_CARRIER": "interweave", "XDG_RUNTIME_DIR": d}):
                rc = ctl.main(["alice", "states"], registry=reg, call=lambda p, **kw: calls.append(p),
                              who={"host": "h", "agent": "op"}, token="t", out=out.append, err=err.append)
        self.assertEqual(calls, [])
        self.assertEqual(rc, 1, (out, err))
        self.assertIn("unknown", out[0])


class Config(unittest.TestCase):
    def read(self, value):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "config.json")
            with open(f, "w", encoding="utf-8") as fh:
                json.dump({"control_carrier": value} if value is not None else {}, fh)
            with mock.patch.dict(os.environ):
                os.environ.pop("FABRIC_CONTROL_CARRIER", None)
                return agentd.control_config(file=f)["control_carrier"]

    def test_interweave_is_the_third_word_and_the_others_are_as_they_were(self):
        self.assertEqual([self.read(v) for v in ("relay", "dual", "interweave", None)], ["relay", "dual", "interweave", "relay"])

    def test_the_environment_names_it_too_and_a_typo_is_refused(self):
        with mock.patch.dict(os.environ, {"FABRIC_CONTROL_CARRIER": "interweave"}):
            self.assertEqual(agentd.control_config(file="/nonexistent")["control_carrier"], "interweave")
        with self.assertRaisesRegex(RuntimeError, "'interwave' is not one of 'relay', 'dual', 'interweave'"):
            self.read("interwave")


if __name__ == "__main__":
    unittest.main()
