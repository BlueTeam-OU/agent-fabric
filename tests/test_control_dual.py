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
import socket
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
        self.calls: list[str] = []   # every call, down or not: what a run never asked of the relay is `calls == []`
        self.lock = threading.Lock()

    def add_reply(self, record: dict) -> None:
        with self.lock:
            self.rows.append({"id": str(len(self.rows) + 100), "content": js.stringify(record)})

    def __call__(self, path: str, **init):
        self.calls.append(path)
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


class Harness(Scratch):
    """No cases: the operator's agentd, the accounts and ctl.main in this process, with the carrier a subclass names."""
    carrier = "dual"

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
        patcher = mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.runtime, "AGENT_FABRIC_STATE_DIR": self.state, "FABRIC_CONTROL_CARRIER": self.carrier})
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
        op = Node(self, self.net, "op", rows=op_rows, relay_off=self.carrier == "interweave")
        server = link.Server(link.socket_path(), op.carrier, "h/op", log=op.logs.append, refused_ops=op.carrier.refused_ops)
        server.start()
        self.addCleanup(server.stop)
        self.nodes["op"] = op
        for n in names:
            self.nodes[n] = Node(self, self.net, n, relay_off=self.carrier == "interweave")
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

    def relay_arrived(self) -> bool:
        try:
            return any(a["carrier"] == "relay" and a["kind"] == "reply" for a in self.arrivals())
        except FileNotFoundError:
            return False

    def request_of(self, login: str) -> dict:
        self.assertTrue(until(lambda: self.nodes[login].requests), self.nodes["op"].logs + self.nodes[login].logs)
        return self.nodes[login].requests[0][0]


class Dual(Harness):
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

    def test_the_request_is_logged_with_its_addressees_for_the_parity_computation(self):
        self.boot("alice")
        box = self.run_ctl("alice", "ping", "--json", "--timeout", "10")
        request = self.request_of("alice")
        self.answer("alice", request)
        self.assertEqual(self.finish(box), 0, self.err)
        lines = [a for a in self.arrivals() if a["kind"] == "request"]
        self.assertEqual([(a["who"], a["id"], a["verdict"], a["to"]) for a in lines], [("ctl", request["id"], "sent", ["h/alice"])])

    def test_a_request_to_all_is_logged_with_the_addresses_it_expanded_to_and_not_the_wildcard(self):
        self.boot("alice")
        box = self.run_ctl("all", "ping", "--json", "--timeout", "10")
        request = self.request_of("alice")
        self.assertEqual(request["to"], "*")
        self.answer("alice", request)
        self.finish(box)   # bob is placed and silent: the run's status is not what is asked here
        lines = [a for a in self.arrivals() if a["kind"] == "request"]
        self.assertEqual(len(lines), 1)
        self.assertIn("h/alice", lines[0]["to"])
        self.assertTrue(all(isinstance(x, str) and x != "*" for x in lines[0]["to"]), lines[0]["to"])

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
        # ctl has read the relay copy (it logs the arrival) before the other one comes
        self.assertTrue(until(lambda: self.relay_arrived()), self.err)
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

        server = link.Server(link.socket_path(), op.carrier, "h/op", log=op.logs.append, refused_ops=op.carrier.refused_ops, hold=lambda: agentd.ctl_hold(leave, inflight))
        server.start()
        self.addCleanup(server.stop)
        self.nodes["op"] = op
        for n in ("alice", "bob"):
            self.nodes[n] = Node(self, self.net, n, relay_off=self.carrier == "interweave")
            self.nodes[n].carrier._on_request = lambda request, sender, n=n: self.nodes[n].requests.append((request, sender))
        self.relay.down = True
        box = self.run_ctl("alice", "bob", "ping", "--json", "--timeout", "15")
        self.answer("alice", self.request_of("alice"), relay=False)
        self.assertFalse(leave.request("source changed"))   # the operator's own upgrade moved the code, mid-command; decided before it returns
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

    def place_operator(self) -> None:
        """The live registry places the operator's own account too, so `all` names it (the fixture's does not)."""
        with open(self.registry, "w", encoding="utf-8") as fh:
            json.dump({**REGISTRY, "placement": {"alice": "h", "op": "h"}}, fh)

    def test_the_operators_own_row_comes_with_the_relay_at_a_closed_port(self):
        # j245: this account was never sent to by InterWeave ("the relay carries it"), so with the relay gone its row was lost.
        self.place_operator()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            closed = probe.getsockname()[1]
        env = mock.patch.dict(os.environ, {"CLAUDE_BRIDGE_URL": f"http://127.0.0.1:{closed}"})
        env.start()
        self.addCleanup(env.stop)
        self.boot("alice")
        box: dict = {}
        self.done = threading.Event()

        def go() -> None:   # no `call=`: the real api, refused at the closed port
            box["rc"] = ctl.main(["all", "ping", "--json", "--timeout", "10"], registry=self.registry, who=WHO, token="t",
                                 out=self.out.append, err=self.err.append)
            self.done.set()
        threading.Thread(target=go, daemon=True).start()
        for login in ("op", "alice"):
            self.answer(login, self.request_of(login), relay=False)
        self.assertEqual(self.finish(box), 0, self.err)
        self.assertEqual({r["account"]: (r["status"], r["carrier"]) for r in self.rows()},
                         {"op": ("ok", "interweave"), "alice": ("ok", "interweave")})
        self.assertTrue(any("InterWeave carries alone" in e for e in self.err), self.err)
        self.assertTrue(any(str(closed) in e for e in self.err), "the line names the closed port the relay was asked at")

    def test_agentds_window_ending_before_the_wait_does_not_say_agentd_went_away(self):
        # j249: agentd's window starts when it writes sent-all, --timeout (t0) after the hand-off has read it, so agentd's ends first.
        self.boot("alice")
        self.done = threading.Event()
        box: dict = {}

        def go() -> None:
            box["rc"] = ctl.main(["all", "ping", "--json", "--timeout", "3"], registry=self.registry, call=self.relay, who=WHO, token="t",
                                 out=self.out.append, err=self.err.append)
            self.done.set()
        threading.Thread(target=go, daemon=True).start()
        self.request_of("alice")   # handed over by the second carrier; never answered
        self.assertEqual(self.finish(box, 30), 1, self.err)   # nobody answered: the rows say so
        self.assertEqual([e for e in self.err if "agentd" in e], [], self.err)

    def test_the_operators_own_row_by_both_carriers_is_the_interweave_copy_and_others_are_unchanged(self):
        self.place_operator()
        self.boot("alice")
        box = self.run_ctl("all", "ping", "--json", "--timeout", "10")
        for login in ("op", "alice"):
            self.answer(login, self.request_of(login))
        self.assertEqual(self.finish(box), 0, self.err)
        self.assertEqual({r["account"]: (r["carrier"], r["relay_copy"]) for r in self.rows()},
                         {"op": ("interweave", "same"), "alice": ("interweave", "same")})
        self.assertEqual(len(self.nodes["op"].requests), 1, "handed to the handler once")

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
            box = self.run_ctl("alice", op, "--timeout", "10")
            self.assertTrue(until(lambda: self.relay.sent))
            self.assertEqual([r["op"] for r in self.relay.sent], [op], f"positive control: {op} went by the relay, signed and whole")
            self.relay.add_reply({"v": 1, "kind": "reply", "id": f"rp-{op}", "in_reply_to": self.relay.sent[0]["id"], "from": "h/alice", "op": op,
                                  "ok": True, "data": {}})   # answered, so ctl ends at once and not at its timeout
            self.finish(box)
        # A ping by the same route is the positive control and the bound: the second carrier's directory is read in order, so
        # the four would have come before it.
        box = self.run_ctl("alice", "ping", "--json", "--timeout", "5")
        self.request_of("alice")
        self.assertEqual([r["op"] for r, _ in self.nodes["alice"].requests], ["ping"], "not one of the four went by the second carrier")
        self.answer("alice", self.nodes["alice"].requests[0][0])
        self.assertEqual(self.finish(box), 0, self.err)
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
                rid = self.relay.sent[0]["id"]
                self.relay.sent.clear()
                self.relay.add_reply({"v": 1, "kind": "reply", "id": "x", "in_reply_to": rid, "from": "h/alice", "op": "ping", "ok": True, "data": {}})
                self.assertEqual(self.finish(box, 12), 0, self.err)
        row = self.rows()[0]
        self.assertEqual(row["status"], "ok", "positive control: the reply was taken, not waited out")
        self.assertNotIn("carrier", row, "a relay run's rows are as they were")
        self.assertNotIn("relay_copy", row)
        self.assertEqual(self.nodes["alice"].requests, [], "and nothing went by the second carrier")
        self.assertFalse(os.path.exists(os.path.join(ctl.state_dir(), "control-arrivals.jsonl")), "no arrival log is kept")

    def test_a_reply_a_peer_wrote_in_another_accounts_name_never_becomes_that_accounts_row(self):
        self.boot("alice", "bob")
        box = self.run_ctl("alice", "ping", "--json", "--timeout", "3")
        req = self.request_of("alice")
        forged = {"v": 1, "kind": "reply", "id": "forged", "in_reply_to": req["id"], "from": "h/alice", "op": "ping", "ok": True, "data": {"agentd": {"pid": 666}}}
        bob = self.nodes["bob"]
        ok, why = bob.child.settle(bob.child.send(f"{PEERS['op']}/fabric-control", link.frame(forged)), 5)
        self.assertTrue(ok, why)
        # dropped, and said so, while ctl is still waiting: the "no answer" below is the drop's and not a timeout that came first
        self.assertTrue(until(lambda: any("says it is from" in l for l in self.nodes["op"].logs), 2.0), self.nodes["op"].logs)
        self.assertFalse(self.done.is_set(), "ctl was still waiting when the forged copy was dropped")
        self.finish(box)
        self.assertEqual(self.rows()[0]["status"], "no answer", "alice never answered; bob's copy in her name was dropped at the carrier")


class Interweave(Harness):
    """control_carrier "interweave": the relay is never called, and is down besides, so a call would be an error and not
    only a failed assertion; an op the carrier cannot carry goes through hostexec and says so."""
    carrier = "interweave"

    def setUp(self) -> None:
        super().setUp()
        self.relay.down = True

    def test_a_status_round_trip_goes_by_the_carrier_alone_with_the_relay_refusing_every_connection(self):
        self.boot("alice")
        box = self.run_ctl("alice", "ping", "--json", "--timeout", "10")
        req = self.request_of("alice")
        self.answer("alice", req, relay=False)
        self.assertEqual(self.finish(box), 0, self.err)
        self.assertEqual(self.rows()[0]["status"], "ok")
        self.assertEqual(self.relay.calls, [], "no post, no read")
        self.assertEqual(self.err, [], "and nothing said of a relay that is not used")

    def test_a_request_to_everyone_is_one_send_per_account_and_each_answer_is_a_row(self):
        self.boot("alice", "bob")
        box = self.run_ctl("all", "ping", "--json", "--timeout", "10")
        for login in ("alice", "bob"):
            self.answer(login, self.request_of(login), relay=False)
        self.assertEqual(self.finish(box), 0, self.err)
        self.assertEqual(sorted(r["account"] for r in self.rows()), ["alice", "bob"])
        self.assertEqual(self.relay.calls, [])

    def test_with_no_operator_agentd_nothing_is_sent_and_there_is_no_relay_to_fall_back_to(self):
        self.nodes["alice"] = Node(self, self.net, "alice")
        t0 = time.monotonic()
        rc = ctl.main(["alice", "ping", "--json", "--timeout", "30"], registry=self.registry, call=self.relay, who=WHO, token="t",
                      out=self.out.append, err=self.err.append)
        self.assertEqual(rc, 3)
        self.assertLess(time.monotonic() - t0, 10, "refused at once, not after the whole --timeout")
        self.assertTrue(any("interweave" in e and "nothing sent" in e for e in self.err), self.err)
        self.assertEqual((self.relay.calls, self.out, self.nodes["alice"].requests), ([], [], []))

    def run_with_session(self, session_cls):
        self.nodes["alice"] = Node(self, self.net, "alice")
        with mock.patch.object(link, "Session", session_cls):
            rc = ctl.main(["alice", "ping", "--json", "--timeout", "30"], registry=self.registry, call=self.relay, who=WHO, token="t",
                          out=self.out.append, err=self.err.append)
        return rc

    def test_a_hand_off_that_failed_after_agentd_took_the_request_is_unknown_and_never_nothing_sent(self):
        class Slow:
            def __init__(self, *a, **k):
                self.sent = {"h/alice": (True, "")}

            def wait_sent(self, t):
                raise RuntimeError("the operator's agentd did not finish the sends in time")

            def close(self):
                pass
        rc = self.run_with_session(Slow)
        self.assertEqual(rc, 3)
        self.assertTrue(any("is unknown" in e and "read the accounts" in e for e in self.err), self.err)
        self.assertFalse(any("nothing sent" in e for e in self.err), self.err)
        self.assertEqual(self.relay.calls, [])

    def test_a_request_agentd_refused_or_never_connected_is_nothing_sent(self):   # the positive control of the case above
        class Refused:
            def __init__(self, *a, **k):
                self.sent = {}

            def wait_sent(self, t):
                raise link.SessionRefused("agentd refused it")

            def close(self):
                pass
        self.assertEqual(self.run_with_session(Refused), 3)
        self.assertTrue(any("nothing sent" in e for e in self.err), self.err)
        self.assertFalse(any("is unknown" in e for e in self.err), self.err)

    def test_sends_that_all_failed_are_unknown_unless_each_reason_says_it_never_left(self):
        def session_with(why):
            class S:
                def __init__(self, *a, **k):
                    self.sent = {"h/alice": (False, why)}

                def wait_sent(self, t):
                    return []

                def close(self):
                    pass
            return S
        self.assertEqual(self.run_with_session(session_with("the send did not settle in time")), 3)
        self.assertTrue(any("is unknown" in e for e in self.err), self.err)
        self.err.clear()
        self.assertEqual(self.run_with_session(session_with("no roster row for this peer")), 3)
        self.assertTrue(any("nothing sent" in e for e in self.err), self.err)

    def test_each_request_is_built_and_signed_just_before_its_own_send(self):
        # A request's ts is when it was built and its ttl_s runs from there: signed up front, a late account's would arrive expired.
        from control import breakglass
        self.boot("alice", "bob")
        events: list = []
        real = ctl.build_request

        def spy(args, **kw):
            events.append("build " + kw["to"][0])
            return real(args, **kw)

        def via(request, target, **kw):
            events.append("send " + target["address"])
            return breakglass.Outcome("refused", detail="x", exit=3)
        with mock.patch.object(ctl, "build_request", spy), mock.patch.object(breakglass, "via_hostexec", via):
            ctl.main(["all", "interweave-stop", "--json", "--timeout", "10"], registry=self.registry, call=self.relay, who=WHO,
                     token="t", out=self.out.append, err=self.err.append)
        self.assertEqual(events, ["build h/alice", "send h/alice", "build h/bob", "send h/bob"])

    def test_a_signing_failure_on_a_later_account_prints_the_rows_so_far_and_names_the_untried(self):
        from control import breakglass
        self.boot("alice", "bob")
        calls = []
        real = ctl.sign_request

        def flaky(request, key):
            if request["to"] == ["h/bob"]:
                raise RuntimeError("openssl: could not spawn")
            return real(request, key)

        def via(request, target, **kw):
            calls.append(target["address"])
            ok = {"v": 1, "kind": "reply", "id": "r", "in_reply_to": request["id"], "from": target["address"], "op": request["op"],
                  "ok": True, "data": {request["op"]: {"status": "stopped"}}}
            return breakglass.Outcome("reply", ok, exit=0)
        with mock.patch.object(ctl, "sign_request", flaky), mock.patch.object(breakglass, "via_hostexec", via):
            rc = ctl.main(["all", "interweave-stop", "--json", "--timeout", "10"], registry=self.registry, call=self.relay, who=WHO,
                          token="t", out=self.out.append, err=self.err.append)
        self.assertEqual((rc, calls), (3, ["h/alice"]))
        self.assertEqual([(r["account"], r["status"]) for r in self.rows()], [("alice", "ok"), ("bob", "no answer")])
        self.assertTrue(any("could not spawn" in e and "not sent to bob" in e for e in self.err), self.err)

    def test_a_relay_only_action_goes_through_hostexec_one_signed_request_per_account_and_says_so(self):
        from control import breakglass
        self.boot("alice", "bob")
        sent: list = []

        def via(request, target, *, timeout, registry=None, **kw):
            sent.append((request, target))
            ok = {"v": 1, "kind": "reply", "id": "r", "in_reply_to": request["id"], "from": target["address"], "op": request["op"],
                  "ok": True, "data": {request["op"]: {"status": ctl.ACTION_OK[request["op"]][0]}}}
            return breakglass.Outcome("reply", ok, exit=0)
        with mock.patch.object(breakglass, "via_hostexec", via):
            rc = ctl.main(["all", "interweave-stop", "--json", "--timeout", "10"], registry=self.registry, call=self.relay, who=WHO, token="t",
                          out=self.out.append, err=self.err.append)
        self.assertEqual(rc, 0, self.err)
        self.assertEqual([(r["op"], r["to"], t["address"]) for r, t in sent],
                         [("interweave-stop", ["h/alice"], "h/alice"), ("interweave-stop", ["h/bob"], "h/bob")])
        self.assertTrue(all(r.get("sig") or r.get("signature") for r, _ in sent), "signed: fabric-op refuses an unsigned action")
        self.assertEqual(len({r["id"] for r, _ in sent}), 2)
        self.assertTrue(any("cannot ride" in e and "hostexec" in e and "bin/fabric-op" in e for e in self.err), self.err)
        self.assertEqual(sorted(r["account"] for r in self.rows()), ["alice", "bob"])
        self.assertEqual((self.relay.calls, self.nodes["alice"].requests, self.nodes["bob"].requests), ([], [], []), "never the relay, never the carrier")

    def test_a_refusal_by_fabric_op_is_said_and_is_not_a_success(self):
        from control import breakglass
        self.boot("alice")
        with mock.patch.object(breakglass, "via_hostexec", lambda *a, **k: breakglass.Outcome("refused", detail="not an operator", exit=3)):
            rc = ctl.main(["alice", "interweave-start", "--json", "--timeout", "10"], registry=self.registry, call=self.relay, who=WHO,
                          token="t", out=self.out.append, err=self.err.append)
        self.assertEqual(rc, 2)
        self.assertTrue(any("refused by fabric-op: not an operator" in e for e in self.err), self.err)

    def hostexec_reply(self, calls: list, data=None):
        """breakglass.via_hostexec as a fabric-op that answers: records (request, target) and returns the account's own reply."""
        from control import breakglass

        def via(request, target, *, timeout, registry=None, **kw):
            calls.append((request, target))
            return breakglass.Outcome("reply", {"v": 1, "kind": "reply", "id": "r", "in_reply_to": request["id"], "from": target["address"],
                                                "op": request["op"], "ok": True, "data": data or {"interweave": {"status": "ok"}}}, exit=0)
        return via

    def test_the_carriers_own_read_is_carried_while_the_carrier_runs_and_never_asks_hostexec_or_the_relay(self):
        from control import breakglass
        self.boot("alice")
        with mock.patch.object(breakglass, "via_hostexec", side_effect=AssertionError("hostexec")):
            box = self.run_ctl("alice", "interweave", "--json", "--timeout", "10")
            req = self.request_of("alice")
            self.assertEqual(req["op"], "interweave")
            self.answer("alice", req, relay=False, data={"interweave": {"status": "ok"}})
            self.assertEqual(self.finish(box), 0, self.err)
        row = self.rows()[0]
        self.assertEqual((row["status"], row["carrier"], row["interweave"]), ("ok", "interweave", {"status": "ok"}))
        self.assertEqual(self.relay.calls, [], "the relay is a closed port: not called")
        self.assertEqual(self.err, [])

    def test_a_stopped_carrier_is_read_back_by_hostexec_one_signed_request_per_account_and_the_row_says_which_path(self):
        self.boot("alice")   # alice's carrier takes the send and never answers: what a stopped one does
        calls: list = []
        with mock.patch.object(ctl, "CARRIER_FIRST_ANSWER_S", 1.0), mock.patch("control.breakglass.via_hostexec", self.hostexec_reply(calls)):
            box = self.run_ctl("alice", "interweave", "--json", "--timeout", "10")
            self.assertEqual(self.finish(box), 0, self.err)
        self.assertEqual(self.request_of("alice")["op"], "interweave", "it was asked by the carrier first")
        (request, target), = calls
        self.assertEqual((request["op"], request["to"], request["from"], target["address"]), ("interweave", ["h/alice"], "h/op", "h/alice"))
        self.assertTrue(request.get("sig"), "signed: fabric-op admits it by the one rule")
        self.assertNotEqual(request["id"], self.request_of("alice")["id"], "a new request, signed when it is sent")
        row = self.rows()[0]
        self.assertEqual((row["status"], row["carrier"], row["interweave"]), ("ok", "hostexec", {"status": "ok"}))
        self.assertTrue(any("alice did not answer by InterWeave" in e and "bin/fabric-op" in e for e in self.err), self.err)
        self.assertEqual(self.relay.calls, [])

    def test_an_account_the_send_never_reached_is_asked_by_hostexec_at_once_and_one_that_answered_is_not(self):
        rows = [r for r in ROWS if r["login"] != "bob"]   # no roster row for bob: the send fails, never sent
        self.boot("alice", "bob", op_rows=rows)
        calls: list = []
        t0 = time.monotonic()
        with mock.patch.object(ctl, "CARRIER_FIRST_ANSWER_S", 30.0), mock.patch("control.breakglass.via_hostexec", self.hostexec_reply(calls)):
            box = self.run_ctl("all", "interweave", "--json", "--timeout", "60")
            self.answer("alice", self.request_of("alice"), relay=False, data={"interweave": {"status": "ok"}})
            self.assertEqual(self.finish(box), 0, self.err)
        self.assertLess(time.monotonic() - t0, 15, "bob was not waited for")
        self.assertEqual([t["address"] for _, t in calls], ["h/bob"])
        self.assertEqual({r["account"]: r["carrier"] for r in self.rows()}, {"alice": "interweave", "bob": "hostexec"})
        said = [e for e in self.err if "bin/fabric-op" in e]
        self.assertEqual(len(said), 1, self.err)
        self.assertIn("bob could not be asked by InterWeave (the send did not reach them)", said[0])
        self.assertNotIn("bob did not answer", said[0], "bob was never given a wait, so no wait is claimed for it")
        self.assertNotIn("alice", said[0], "alice answered: she is not in the line")

    def test_the_announce_gives_a_wait_to_the_account_asked_and_none_to_the_one_never_reached(self):
        rows = [r for r in ROWS if r["login"] != "bob"]
        self.boot("alice", "bob", op_rows=rows)   # alice takes the send and stays silent; bob's never happens
        calls: list = []
        with mock.patch.object(ctl, "CARRIER_FIRST_ANSWER_S", 1.0), mock.patch("control.breakglass.via_hostexec", self.hostexec_reply(calls)):
            box = self.run_ctl("all", "interweave", "--json", "--timeout", "10")
            self.assertEqual(self.finish(box), 0, self.err)
        said = [e for e in self.err if "bin/fabric-op" in e]
        self.assertEqual(len(said), 1, self.err)
        self.assertIn("alice did not answer by InterWeave within 1 s; bob could not be asked by InterWeave (the send did not reach them): asked through hostexec", said[0])

    def test_no_operator_agentd_reads_every_account_by_hostexec_without_waiting(self):
        self.nodes["alice"] = Node(self, self.net, "alice")
        calls: list = []
        t0 = time.monotonic()
        with mock.patch("control.breakglass.via_hostexec", self.hostexec_reply(calls)):
            rc = ctl.main(["alice", "interweave", "--json", "--timeout", "30"], registry=self.registry, call=self.relay, who=WHO, token="t",
                          out=self.out.append, err=self.err.append)
        self.assertEqual(rc, 0, self.err)
        self.assertLess(time.monotonic() - t0, 10)
        self.assertEqual([r["carrier"] for r in self.rows()], ["hostexec"])
        self.assertEqual(self.relay.calls, [])

    def test_a_read_fabric_op_refused_or_could_not_run_is_a_failed_run_and_a_no_answer_row(self):
        from control import breakglass
        self.boot("alice")
        for kind, rc_want in (("refused", 2), ("failed", 3)):
            with self.subTest(kind):
                self.out.clear()
                self.err.clear()
                with mock.patch.object(ctl, "CARRIER_FIRST_ANSWER_S", 0.5), mock.patch.object(breakglass, "via_hostexec",
                                                                                              lambda *a, **k: breakglass.Outcome(kind, detail="why", exit=2)):
                    rc = ctl.main(["alice", "interweave", "--json", "--timeout", "5"], registry=self.registry, call=self.relay, who=WHO, token="t",
                                  out=self.out.append, err=self.err.append)
                self.assertEqual(rc, rc_want, self.err)
                self.assertEqual([(r["account"], r["status"]) for r in self.rows()], [("alice", "no answer")])
                self.assertTrue(any("alice: " in e and "why" in e for e in self.err), self.err)

    def test_the_table_names_the_accounts_hostexec_answered(self):
        self.boot("alice")
        with mock.patch.object(ctl, "CARRIER_FIRST_ANSWER_S", 0.5), mock.patch("control.breakglass.via_hostexec", self.hostexec_reply([])):
            rc = ctl.main(["alice", "interweave", "--timeout", "5"], registry=self.registry, call=self.relay, who=WHO, token="t",
                          out=self.out.append, err=self.err.append)
        self.assertEqual(rc, 0, self.err)
        self.assertIn("answered through hostexec, not InterWeave: alice", self.out)

    def test_no_signing_key_leaves_the_silent_account_a_no_answer_row_and_exit_3(self):
        self.boot("alice")
        with mock.patch.object(ctl, "CARRIER_FIRST_ANSWER_S", 0.5), mock.patch.object(ctl, "signing_key", return_value={"error": "no key"}), \
                mock.patch("control.breakglass.via_hostexec", side_effect=AssertionError("unsigned")):
            rc = ctl.main(["alice", "interweave", "--json", "--timeout", "5"], registry=self.registry, call=self.relay, who=WHO, token="t",
                          out=self.out.append, err=self.err.append)
        self.assertEqual(rc, 3)
        self.assertEqual([r["status"] for r in self.rows()], ["no answer"])
        self.assertTrue(any("the interweave read is signed or not sent" in e for e in self.err), self.err)
        self.assertFalse(any("asked through hostexec" in e for e in self.err), "nothing was sent: it is not said to have been")

    def test_a_reply_fabric_op_called_a_failure_is_not_an_ok_row(self):
        from control import breakglass
        self.boot("alice")
        # the target journals "failed" and exits 1 when the reply has no section for the op; the reply still comes back on stdout
        failed = lambda request, target, **k: breakglass.Outcome("reply", {"v": 1, "kind": "reply", "id": "r", "in_reply_to": request["id"],
                                                                           "from": target["address"], "op": request["op"], "ok": True, "data": {}}, exit=1)
        with mock.patch.object(ctl, "CARRIER_FIRST_ANSWER_S", 0.5), mock.patch.object(breakglass, "via_hostexec", failed):
            rc = ctl.main(["alice", "interweave", "--json", "--timeout", "5"], registry=self.registry, call=self.relay, who=WHO, token="t",
                          out=self.out.append, err=self.err.append)
        self.assertEqual(rc, 3, self.err)
        self.assertEqual([r["status"] for r in self.rows()], ["no answer"])
        self.assertTrue(any("holds no interweave section" in e for e in self.err), self.err)

    def test_the_read_is_still_refused_by_the_flag_that_names_hostexec(self):
        # --via is the actions' break-glass; the read's fallback is automatic, never asked for by name
        rc = ctl.main(["alice", "interweave", "--via", "hostexec"], registry=self.registry, call=self.relay, who=WHO, token="t",
                      out=self.out.append, err=self.err.append)
        self.assertNotEqual(rc, 0)
        self.assertTrue(any("is a read" in e for e in self.err), self.err)
        self.assertEqual((self.out, self.relay.calls), ([], []))

    def test_under_dual_the_same_action_is_not_taken_through_hostexec(self):   # the positive control of the routing above
        from control import breakglass
        self.boot("alice")
        with mock.patch.dict(os.environ, {"FABRIC_CONTROL_CARRIER": "dual"}), mock.patch.object(breakglass, "via_hostexec", side_effect=AssertionError("hostexec")):
            self.relay.down = False
            box = self.run_ctl("alice", "interweave-start", "--json", "--timeout", "10")
            self.assertTrue(until(lambda: self.relay.sent))
            self.assertEqual(self.relay.sent[0]["op"], "interweave-start")
            self.relay.add_reply({"v": 1, "kind": "reply", "id": "x", "in_reply_to": self.relay.sent[0]["id"], "from": "h/alice", "op": "interweave-start", "ok": True, "data": {}})
            self.finish(box)


if __name__ == "__main__":
    unittest.main()
