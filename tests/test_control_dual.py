#!/usr/bin/env python3
"""fabric-ctl and agentd on both carriers (agent-fabric ADR-029 rule 18; runtime/control/config.json
`control_carrier` "dual").

The relay is a list in this process; the second carrier is tests/fake_interweave_human.py children joined by a
directory, behind the operator's agentd socket (a real control_link.Server). ctl.main runs in this process with
FABRIC_CONTROL_CARRIER set in a patched environment, and the accounts answer through control_link.Carrier.reply
and post the same reply to the fake relay, as agentd's deliver() does. Nothing here touches a live relay,
daemon or account.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from control import agentd, ctl, js  # noqa: E402
from control.sign import generate_operator_key  # noqa: E402
from gzcoord.carrier import control_link as link  # noqa: E402
from test_gzcoord_carrier_control_link import PEERS, ROWS, Node, Scratch, until  # noqa: E402

REGISTRY = {"hosts": {"h": {"operator": "op"}}, "placement": {"alice": "h", "bob": "h"}}
WHO = {"host": "h", "agent": "op"}
KEY = generate_operator_key()   # a throwaway: actions are signed or not sent, and these cases send them


class FakeRelay:
    """The control channel as ctl uses it: /api/send stores the request, /api/messages pages replies after since_id."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.sent: list[dict] = []
        self.down = False
        self.lock = threading.Lock()

    def add_reply(self, record: dict) -> None:
        with self.lock:
            self.rows.append({"id": str(len(self.rows) + 100), "content": js.stringify(record)})

    def __call__(self, path: str, **init):
        if self.down:
            raise ConnectionRefusedError("relay is down")
        if path == "/api/send":
            with self.lock:
                self.sent.append(js.json_parse(js.json_parse(init["body"])["content"]))
            return {"id": "99"}
        with self.lock:
            since = dict(p.split("=", 1) for p in path.split("?", 1)[1].split("&")).get("since_id")
            ids = [r["id"] for r in self.rows]
            rows = self.rows if since == "99" else self.rows[ids.index(since) + 1:] if since in ids else []
            return {"messages": list(rows)}


class Dual(Scratch):
    def setUp(self) -> None:
        self.net = self.mkdir()
        self.runtime = self.mkdir()
        self.state = self.mkdir()
        self.registry = os.path.join(self.mkdir(), "registry.json")
        with open(self.registry, "w", encoding="utf-8") as fh:
            json.dump(REGISTRY, fh)
        self.relay = FakeRelay()
        self.out: list[str] = []
        self.err: list[str] = []
        patcher = mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.runtime, "AGENT_FABRIC_STATE_DIR": self.state, "FABRIC_CONTROL_CARRIER": "dual"})
        patcher.start()
        self.addCleanup(patcher.stop)
        grace = mock.patch.object(ctl, "DUAL_GRACE_S", 0.6)
        grace.start()
        self.addCleanup(grace.stop)
        key = mock.patch.object(ctl, "signing_key", return_value={"key": KEY["privateKeySpec"]})
        key.start()
        self.addCleanup(key.stop)
        self.nodes: dict[str, Node] = {}
        self.answered: dict[str, list[dict]] = {"alice": [], "bob": []}

    def mkdir(self) -> str:
        return self.scratch()

    def boot(self, *names: str, op_rows=ROWS) -> None:
        """The operator's agentd (a Node with its socket) and the accounts named."""
        op = Node(self, self.net, "op", rows=op_rows)
        server = link.Server(link.socket_path(), op.carrier, "h/op", log=op.logs.append)
        server.start()
        self.addCleanup(server.stop)
        self.nodes["op"] = op
        for n in names:
            self.nodes[n] = Node(self, self.net, n)
            self.nodes[n].carrier._on_request = lambda request, sender, n=n: self.nodes[n].requests.append((request, sender))

    def answer(self, login: str, request: dict, *, relay=True, interweave=True, data=None, relay_data=None) -> dict:
        """What agentd's deliver() does for an account: the reply by both carriers, the same record."""
        rec = {"v": 1, "kind": "reply", "id": f"rp-{login}", "in_reply_to": request["id"], "from": f"h/{login}", "op": request["op"],
               "ts": "2026-11-12T12:00:00.000Z", "ok": True, "data": data if data is not None else {"agentd": {"pid": 1}}}
        if relay:
            self.relay.add_reply({**rec, "data": relay_data} if relay_data is not None else rec)
        if interweave:
            self.nodes[login].carrier.reply(request, rec)
        return rec

    def run_ctl(self, *argv: str) -> int:
        """ctl.main in a thread; the accounts answer when their carrier hands them the request."""
        self.done = threading.Event()
        box: dict = {}

        def go() -> None:
            box["rc"] = ctl.main(list(argv), registry=self.registry, call=self.relay, who=WHO, token="t", out=self.out.append, err=self.err.append)
            self.done.set()
        threading.Thread(target=go, daemon=True).start()
        return box  # type: ignore[return-value]

    def finish(self, box: dict, timeout: float = 20) -> int:
        self.assertTrue(self.done.wait(timeout), f"ctl did not finish: {self.err}")
        return box["rc"]

    def rows(self) -> list[dict]:
        return [json.loads(l) for l in self.out]

    def arrivals(self) -> list[dict]:
        with open(os.path.join(ctl.state_dir(), "control-arrivals.jsonl"), encoding="utf-8") as fh:
            return [json.loads(l) for l in fh]

    def request_of(self, login: str) -> dict:
        self.assertTrue(until(lambda: self.nodes[login].requests), self.nodes["op"].logs + self.nodes[login].logs)
        return self.nodes[login].requests[0][0]

    # -- the cases --------------------------------------------------
    def test_a_reply_that_arrives_by_both_is_the_interweave_copy_with_the_relay_copy_agreeing(self):
        self.boot("alice")
        box = self.run_ctl("alice", "ping", "--json", "--timeout", "10")
        self.answer("alice", self.request_of("alice"))
        self.assertEqual(self.finish(box), 0, self.err)
        row = self.rows()[0]
        self.assertEqual((row["status"], row["carrier"], row["relay_copy"]), ("ok", "interweave", "same"))
        self.assertNotIn("relay_differs", row)
        got = {(a["carrier"], a["who"], a["verdict"]) for a in self.arrivals() if a["kind"] == "reply"}
        self.assertEqual(got, {("interweave", "ctl", "ok"), ("relay", "ctl", "unauthenticated")}, "every arrival, with its carrier")

    def test_a_reply_only_the_relay_carried_says_so_in_the_row_and_under_the_table(self):
        self.boot("alice")
        box = self.run_ctl("alice", "ping", "--timeout", "10")
        self.answer("alice", self.request_of("alice"), interweave=False)
        self.assertEqual(self.finish(box), 0, self.err)
        self.assertIn("relay only: alice", self.out)
        self.assertEqual([a["carrier"] for a in self.arrivals() if a["kind"] == "reply"], ["relay"])

    def test_a_relay_copy_that_differs_is_flagged_and_the_row_is_the_authenticated_copy(self):
        self.boot("alice")
        box = self.run_ctl("alice", "ping", "--json", "--timeout", "10")
        self.answer("alice", self.request_of("alice"), data={"agentd": {"pid": 1}}, relay_data={"agentd": {"pid": 666}})
        self.assertEqual(self.finish(box), 0, self.err)
        row = self.rows()[0]
        self.assertEqual((row["carrier"], row["relay_copy"], row["relay_differs"]), ("interweave", "differs", True))
        self.assertEqual(row["agentd"], {"pid": 1}, "the row shows what InterWeave carried, never the relay's differing copy")

    def test_the_relay_copy_that_differs_is_named_under_the_table_too(self):
        self.boot("alice")
        box = self.run_ctl("alice", "ping", "--timeout", "10")
        self.answer("alice", self.request_of("alice"), relay_data={"agentd": {"pid": 666}})
        self.assertEqual(self.finish(box), 0, self.err)
        self.assertIn("the relay's copy differs from the InterWeave copy: alice", self.out)

    def test_a_relay_copy_that_arrives_first_does_not_stop_the_interweave_copy_winning(self):
        self.boot("alice")
        box = self.run_ctl("alice", "ping", "--json", "--timeout", "10")
        req = self.request_of("alice")
        self.answer("alice", req, interweave=False, relay_data={"agentd": {"pid": 666}})
        time.sleep(0.8)
        self.answer("alice", req, relay=False, data={"agentd": {"pid": 1}})
        self.assertEqual(self.finish(box), 0, self.err)
        row = self.rows()[0]
        self.assertEqual((row["agentd"], row["carrier"], row["relay_copy"]), ({"pid": 1}, "interweave", "differs"))

    def test_the_relay_down_mid_run_the_answer_still_comes_by_the_other_carrier(self):
        self.boot("alice")
        self.relay.down = True
        box = self.run_ctl("alice", "ping", "--json", "--timeout", "10")
        self.answer("alice", self.request_of("alice"), relay=False)
        self.assertEqual(self.finish(box), 0, self.err)
        row = self.rows()[0]
        self.assertEqual((row["status"], row["carrier"], row["relay_copy"]), ("ok", "interweave", "missing"))
        self.assertTrue(any("unreachable" in e and "InterWeave carries alone" in e for e in self.err), self.err)
        self.assertEqual(self.relay.sent, [], "nothing reached the relay")

    def test_the_operators_agentd_restarting_mid_command_loses_no_reply_on_the_carrier_alone(self):
        # j146: `upgrade fabric` on the fleet restarts the operator's own agentd while replies are still coming.
        # The daemon is wired as agentd.main wires it: an open ctl session is in flight for the real Leaver.
        op = Node(self, self.net, "op")
        inflight: set = set()
        exits: list[int] = []
        leave = agentd.leaver(inflight, exit=lambda code: (exits.append(code), server.stop(), op.carrier.stop()), log=lambda m: None)

        server = link.Server(link.socket_path(), op.carrier, "h/op", log=op.logs.append, hold=lambda: agentd.ctl_hold(leave, inflight))
        server.start()
        self.addCleanup(server.stop)
        self.nodes["op"] = op
        for n in ("alice", "bob"):
            self.nodes[n] = Node(self, self.net, n)
            self.nodes[n].carrier._on_request = lambda request, sender, n=n: self.nodes[n].requests.append((request, sender))
        self.relay.down = True
        box = self.run_ctl("alice", "bob", "ping", "--json", "--timeout", "15")
        self.answer("alice", self.request_of("alice"), relay=False)
        leave.request("source changed")   # the operator's own upgrade moved the code, mid-command
        time.sleep(0.5)
        self.assertEqual(exits, [], "the operator's agentd stayed up for the command")
        self.answer("bob", self.request_of("bob"), relay=False)
        self.assertEqual(self.finish(box), 0, self.err)
        self.assertEqual(sorted((r["account"], r["status"], r["carrier"]) for r in self.rows()),
                         [("alice", "ok", "interweave"), ("bob", "ok", "interweave")])
        self.assertTrue(until(lambda: exits == [0]), "and it left once the command was over")

    def test_a_second_carrier_that_is_up_but_silent_never_delays_the_relay_post(self):
        self.boot("alice")
        self.nodes["op"].child.send = lambda conversation, text: link.Send("never")   # ok, and answers nothing
        t0 = time.monotonic()
        box = self.run_ctl("alice", "ping", "--json", "--timeout", "4")
        self.assertTrue(until(lambda: self.relay.sent, 2.0), "the relay copy was posted at once, not after the hand-off gave up")
        self.assertLess(time.monotonic() - t0, 2.0)
        self.answer("alice", self.relay.sent[0], interweave=False)
        self.assertEqual(self.finish(box), 0, self.err)
        self.assertEqual(self.rows()[0]["carrier"], "relay only")

    def test_with_the_relay_down_and_no_second_carrier_the_run_fails_as_it_always_did(self):
        self.relay.down = True
        rc = ctl.main(["alice", "ping"], registry=self.registry, call=self.relay, who=WHO, token="t", out=self.out.append, err=self.err.append)
        self.assertEqual(rc, 3)
        self.assertTrue(any("relay" in e for e in self.err))

    def test_an_account_the_roster_does_not_hold_is_sent_nothing_and_says_relay_only(self):
        self.boot("alice", op_rows=[r for r in ROWS if r["login"] != "alice"])
        box = self.run_ctl("alice", "ping", "--timeout", "10")
        req = self.relay_request()
        self.answer("alice", req, interweave=False)
        self.assertEqual(self.finish(box), 0, self.err)
        self.assertTrue(any("not sent to h/alice (no roster row)" in e for e in self.err), self.err)
        self.assertIn("relay only: alice", self.out)
        self.assertEqual(self.nodes["alice"].requests, [])

    def relay_request(self) -> dict:
        self.assertTrue(until(lambda: self.relay.sent))
        return self.relay.sent[0]

    def test_all_is_one_direct_send_per_placed_account_and_the_record_still_says_star(self):
        self.boot("alice", "bob")
        box = self.run_ctl("all", "ping", "--json", "--timeout", "10")
        for login in ("alice", "bob"):
            req = self.request_of(login)
            self.answer(login, req)
        self.assertEqual(self.finish(box), 0, self.err)
        self.assertEqual(req["to"], "*", "the signed record is unchanged; the fan-out is the sender's")
        self.assertEqual({r["account"]: r["carrier"] for r in self.rows()}, {"alice": "interweave", "bob": "interweave"})
        self.assertEqual(len(self.nodes["alice"].requests), 1)
        self.assertEqual(len(self.nodes["bob"].requests), 1)

    def test_the_four_relay_only_ops_are_never_handed_to_the_second_carrier(self):
        self.boot("alice")
        for op in sorted(link.RELAY_ONLY_OPS):
            self.out.clear()
            self.relay.sent.clear()
            # the read op needs no key; the three actions are refused for want of one — either way nothing may reach alice
            ctl.main(["alice", op, "--timeout", "1"], registry=self.registry, call=self.relay, who=WHO, token="t", out=self.out.append, err=self.err.append)
            self.assertEqual([r["op"] for r in self.relay.sent], [op], f"positive control: {op} went by the relay, signed and whole")
        time.sleep(0.5)
        self.assertEqual(self.nodes["alice"].requests, [], "not one of the four went by the second carrier")
        self.assertEqual([l for l in self.nodes["op"].logs if "relay only" in l], [])

    def test_interweave_evidence_goes_by_both(self):
        self.boot("alice")
        box = self.run_ctl("alice", "interweave-evidence", "--section", "arrivals", "--since", "2026-11-01T00:00:00Z",
                           "--until", "2026-11-02T00:00:00Z", "--json", "--timeout", "5")
        req = self.request_of("alice")
        self.assertEqual(req["op"], "interweave-evidence")
        self.assertTrue(until(lambda: self.relay.sent))
        self.answer("alice", req, data={"interweave-evidence": {"status": "ok", "rows": []}})
        self.finish(box)

    def test_with_no_operator_agentd_the_relay_carries_alone_and_the_row_says_so(self):
        # no boot(): nothing listens on the socket
        accounts_box = {}
        node = Node(self, self.net, "alice")
        accounts_box["alice"] = node
        self.nodes["alice"] = node
        box = self.run_ctl("alice", "ping", "--json", "--timeout", "10")
        req = self.relay_request()
        self.answer("alice", req, interweave=False)
        self.assertEqual(self.finish(box), 0, self.err)
        self.assertTrue(any("does not answer" in e and "relay carries alone" in e for e in self.err), self.err)
        self.assertEqual(self.rows()[0]["carrier"], "relay only")

    def test_with_the_key_absent_or_relay_nothing_changes(self):
        self.boot("alice")
        for env in ({"FABRIC_CONTROL_CARRIER": "relay"},):
            with mock.patch.dict(os.environ, env):
                self.out.clear()
                box = self.run_ctl("alice", "ping", "--json", "--timeout", "10")
                self.assertTrue(until(lambda: self.relay.sent))
                self.relay.sent.clear()
                self.relay.add_reply({"v": 1, "kind": "reply", "id": "x", "in_reply_to": "9", "from": "h/alice", "op": "ping", "ok": True, "data": {}})
                self.finish(box, 12)
        row = self.rows()[0]
        self.assertNotIn("carrier", row, "a relay run's rows are as they were")
        self.assertNotIn("relay_copy", row)
        self.assertEqual(self.nodes["alice"].requests, [], "and nothing went by the second carrier")
        self.assertFalse(os.path.exists(os.path.join(ctl.state_dir(), "control-arrivals.jsonl")), "no arrival log is kept")

    def test_a_reply_a_peer_wrote_in_another_accounts_name_never_becomes_that_accounts_row(self):
        self.boot("alice", "bob")
        box = self.run_ctl("alice", "ping", "--json", "--timeout", "6")
        req = self.request_of("alice")
        forged = {"v": 1, "kind": "reply", "id": "forged", "in_reply_to": req["id"], "from": "h/alice", "op": "ping", "ok": True, "data": {"agentd": {"pid": 666}}}
        bob = self.nodes["bob"]
        ok, why = bob.child.settle(bob.child.send(f"{PEERS['op']}/fabric-control", link.frame(forged)), 5)
        self.assertTrue(ok, why)
        self.finish(box)
        self.assertEqual(self.rows()[0]["status"], "no answer", "alice never answered; bob's copy in her name was dropped at the carrier")
        self.assertTrue(any("says it is from" in l for l in self.nodes["op"].logs))


if __name__ == "__main__":
    unittest.main()
