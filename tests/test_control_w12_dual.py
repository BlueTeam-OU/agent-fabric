#!/usr/bin/env python3
"""W12 of the InterWeave-only cutover: the presence check (control/presence.py) and the job queue's holder
(control/queue.py) asked through this account's own agentd socket when control_carrier is "dual", so a relay
that is down does not stop an addressed send. The asker's end is a real control_link.Server over the fake
InterWeave network of test_gzcoord_carrier_control_link; the relay is a callable that refuses or answers.

control_carrier "relay" is held to today's behaviour: the second carrier is never opened and nothing is said.
"""
from __future__ import annotations

import io
import json
import os
import sys
import threading
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
import test_gzcoord_carrier_control_link as base  # noqa: E402
from control import gzcoord, presence, queue  # noqa: E402
from gzcoord.carrier import control_link as cc  # noqa: E402

ALICE, BOB = "h/alice", "h/bob"
ONLINE = {"status": "ok", "online": True, "sessions": 1, "since": "2026-11-13T07:00:00.000Z", "role": "python-dev", "project": "x"}
CFG_DUAL = {"relay_url": "http://relay.invalid", "channel": "fabric:control", "ttl_s": 30, "control_carrier": "dual"}
CFG_RELAY = {**CFG_DUAL, "control_carrier": "relay"}


def down(**kw):
    """The relay stopped: what gzcoord.api raises on a refused connection."""
    def call(path, method="GET", body=None):
        raise gzcoord.ApiError(f"{path} -> refused", connection_refused=True, **kw)
    return call


class Answering(base.Net):
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

    def bob_answers(self, data: dict, op: str, frm: str = BOB) -> threading.Thread:
        def run() -> None:
            if base.until(lambda: self.bob.requests):
                req = self.bob.requests[0][0]
                self.bob.carrier.reply(req, {"v": 1, "kind": "reply", "id": "a1", "in_reply_to": req["id"], "from": frm, "op": op,
                                             "ts": "2026-11-13T07:00:01.000Z", "ok": True, "data": data})
        t = threading.Thread(target=run, daemon=True)
        t.start()
        self.addCleanup(t.join, 5)
        return t

    def ask(self, **kw):
        return presence.ask_presence(from_=ALICE, to=[BOB], expect=[BOB], wait_ms=kw.pop("wait_ms", 4000), cfg=kw.pop("cfg", CFG_DUAL),
                                     new_id=lambda: "pq1", **kw)

    def test_presence_with_the_relay_down_is_answered_by_interweave(self):
        self.bob_answers({"presence": ONLINE}, "presence")
        self.assertEqual(self.ask(call=down()), {BOB: ONLINE})
        self.assertEqual(self.bob.requests[0][0]["op"], "presence")

    def test_a_dual_run_with_the_relay_up_takes_the_first_answer_of_either(self):
        posts = []

        def call(path, method="GET", body=None):
            if method == "POST":
                posts.append(body)
            return {"id": "s1"} if method == "POST" else {"messages": []}
        self.bob_answers({"presence": ONLINE}, "presence")
        self.assertEqual(self.ask(call=call), {BOB: ONLINE})
        self.assertEqual(len(posts), 1)   # the relay post is still the record

    def test_an_answer_whose_record_claims_another_sender_is_not_taken(self):
        self.bob_answers({"presence": ONLINE}, "presence", frm="h/alice")
        self.assertEqual(self.ask(call=down(), wait_ms=1500), {BOB: None})

    def test_the_holders_answer_over_interweave_with_the_relay_down(self):
        self.bob_answers({"pool-list": {"status": "ok", "pool": []}}, "pool-list")
        got = queue.ask_holder(call=down(), cfg=CFG_DUAL, from_=ALICE, holder=BOB, op="pool-list", args={"role": "python-dev"},
                               new_id=lambda: "qq1", wait_ms=4000)
        self.assertEqual(got, {"status": "ok", "pool": []})

    def test_a_reply_that_is_not_the_holders_is_not_the_answer(self):
        self.bob_answers({"pool-list": {"status": "ok", "pool": []}}, "pool-list", frm="h/alice")
        got = queue.ask_holder(call=down(), cfg=CFG_DUAL, from_=ALICE, holder=BOB, op="pool-list", args={}, new_id=lambda: "qq2",
                               wait_ms=1500)
        self.assertIsNone(got)


class SocketAbsent(unittest.TestCase):
    def setUp(self) -> None:
        patch = mock.patch.dict(os.environ)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("XDG_RUNTIME_DIR", None)

    def test_presence_with_no_socket_and_no_relay_says_both_and_keeps_the_relays_status(self):
        with self.assertRaises(cc.Down) as cm:
            presence.ask_presence(from_=ALICE, to=[BOB], expect=[BOB], wait_ms=200, cfg=CFG_DUAL, new_id=lambda: "p", call=down())
        self.assertIn("XDG_RUNTIME_DIR is not set", str(cm.exception))
        self.assertTrue(cm.exception.connection_refused)

    def test_presence_with_no_socket_and_the_relay_up_says_so_once_and_the_relay_answers(self):
        said = []

        def call(path, method="GET", body=None):
            if method == "POST":
                return {"id": "s1"}
            req = json.loads(json.loads(posted[0])["content"])
            return {"messages": [{"id": "r1", "content": json.dumps({"kind": "reply", "in_reply_to": req["id"], "from": BOB,
                                                                     "data": {"presence": ONLINE}})}]}
        posted = []
        inner = call

        def recording(path, method="GET", body=None):
            if method == "POST":
                posted.append(body)
            return inner(path, method, body)
        got = presence.ask_presence(from_=ALICE, to=[BOB], expect=[BOB], wait_ms=500, cfg=CFG_DUAL, new_id=lambda: "p",
                                    call=recording, say=said.append)
        self.assertEqual(got, {BOB: ONLINE})
        self.assertEqual(len(said), 1)
        self.assertIn("XDG_RUNTIME_DIR is not set", said[0])

    def test_the_holder_ask_with_no_socket_and_no_relay_is_still_certainly_unsent(self):
        with self.assertRaises(cc.Down) as cm:
            queue.ask_holder(call=down(), cfg=CFG_DUAL, from_=ALICE, holder=BOB, op="pool-list", args={}, new_id=lambda: "q", wait_ms=200)
        self.assertTrue(queue.unsent(cm.exception))
        self.assertIn("XDG_RUNTIME_DIR is not set", queue.relay_error(cm.exception, CFG_DUAL))

    def test_a_socket_that_took_the_request_and_then_failed_leaves_the_post_unknown(self):
        def handed(request, to, wait_s):
            raise cc.LegFailed("the operator's agentd did not finish the sends in time", handed=True)
        with self.assertRaises(cc.Down) as cm:
            queue.ask_holder(call=down(), cfg=CFG_DUAL, from_=ALICE, holder=BOB, op="pool-list", args={}, new_id=lambda: "q",
                             wait_ms=200, open_leg=handed)
        self.assertFalse(queue.unsent(cm.exception))

    def test_the_account_that_holds_the_pool_asks_itself_by_the_relay_alone(self):
        def never(*a):
            raise AssertionError("no InterWeave path to oneself")
        with self.assertRaises(gzcoord.ApiError):
            queue.ask_holder(call=down(), cfg=CFG_DUAL, from_=ALICE, holder=ALICE, op="pool-list", args={}, new_id=lambda: "q",
                             wait_ms=200, open_leg=never)

    def test_the_presence_cli_says_it_in_its_one_line_answer(self):
        agentd = mock.Mock(read_registry=lambda _x: None, account_addresses=lambda: [BOB], operator_addresses=lambda: [],
                           control_config=lambda: CFG_DUAL, new_id=lambda: "p")
        out = io.StringIO()
        real = presence.ask_presence
        with mock.patch.object(presence, "ask_presence", lambda **kw: real(**kw, call=down())):
            rc = presence.cli(["check"], stdin=io.StringIO(json.dumps({"metadata": {"TO": BOB}, "from": ALICE, "token": "t"})),
                              agentd=agentd, out=out)
        self.assertEqual(rc, 6)
        self.assertIn("XDG_RUNTIME_DIR is not set", json.loads(out.getvalue())["error"])


class RelayCarrierIsToday(unittest.TestCase):
    """control_carrier relay: the post, the page reads and the sleep, and nothing of the second carrier."""

    def never(self, *a, **k):
        raise AssertionError("the second carrier is not opened under control_carrier relay")

    def test_presence_never_opens_the_socket_and_a_failed_post_raises_the_relays_own_error(self):
        with self.assertRaises(gzcoord.ApiError):
            presence.ask_presence(from_=ALICE, to=[BOB], expect=[BOB], wait_ms=200, cfg=CFG_RELAY, new_id=lambda: "p", call=down(),
                                  open_leg=self.never, say=self.never)

    def test_a_config_without_the_key_is_the_relay_too(self):
        cfg = {k: v for k, v in CFG_RELAY.items() if k != "control_carrier"}
        with self.assertRaises(gzcoord.ApiError):
            queue.ask_holder(call=down(), cfg=cfg, from_=ALICE, holder=BOB, op="pool-list", args={}, new_id=lambda: "q", wait_ms=200,
                             open_leg=self.never, say=self.never)

    def test_a_page_that_fails_after_the_post_is_marked_sent_and_raised(self):
        def call(path, method="GET", body=None):
            if method == "POST":
                return {"id": "s"}
            raise gzcoord.ApiError("page", status=502)
        with self.assertRaises(gzcoord.ApiError) as cm:
            queue.ask_holder(call=call, cfg=CFG_RELAY, from_=ALICE, holder=BOB, op="pool-list", args={}, new_id=lambda: "q",
                             wait_ms=2000, open_leg=self.never, say=self.never)
        self.assertIs(cm.exception.sent, True)


if __name__ == "__main__":
    unittest.main()
