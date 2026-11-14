#!/usr/bin/env python3
"""Tests for tools/fabric/gzcoord/carrier/control_link.py — the control plane's InterWeave carrier (ADR-029 rule 18).

The child is tests/fake_interweave_human.py, a stand-in that prints what the real 0.2.0 child printed when it
was measured (outbound twice, `author` the sender's PeerId, `local_endpoint`), over a directory that plays the
network. Nothing here starts a daemon or touches the relay. The environment each child gets is minimal and
explicit, and every temporary directory is removed however a case ends.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import stat
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from gzcoord.carrier import control_link as cc, roster  # noqa: E402

FAKE = os.path.join(HERE, "tests", "fake_interweave_human.py")
PEERS = {"alice": "12D3KooWAlice" + "A" * 39, "bob": "12D3KooWBob" + "B" * 41, "op": "12D3KooWOp" + "O" * 42, "eve": "12D3KooWEve" + "E" * 41}
PLACED = {"h/alice", "h/bob", "h/op"}   # eve has a transport key but no placement: not an account
ROWS = [{"login": n, "peer_id": p} for n, p in PEERS.items()]


def until(cond, seconds: float = 8.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def request(rid: str = "r1", frm: str = "h/op", op: str = "ping", **over) -> dict:
    return {"v": 1, "kind": "request", "id": rid, "from": frm, "to": ["h/alice"], "op": op, "ts": "2026-11-12T12:00:00.000Z", **over}


def reply(rid: str = "p1", to: str = "r1", frm: str = "h/alice", **over) -> dict:
    return {"v": 1, "kind": "reply", "id": rid, "in_reply_to": to, "from": frm, "op": "ping", "ts": "2026-11-12T12:00:01.000Z", "ok": True, **over}


class Scratch(unittest.TestCase):
    def scratch(self) -> str:
        d = tempfile.mkdtemp(prefix="cc-")
        self.addCleanup(shutil.rmtree, d, True)
        return d


class Node:
    """One account's carrier over the fake network. `requests` is what its on_request was handed."""

    def __init__(self, test: Scratch, net: str, name: str, *, rows=ROWS, placed=PLACED, backoff=(0.05,), extra_env=None, start=True):
        self.name, self.logs, self.requests = name, [], []
        d = test.scratch()
        self.dir = d
        env = {"PATH": os.environ["PATH"], "FAKE_NET": net, "FAKE_PEER": PEERS[name], **(extra_env or {})}
        argv = [sys.executable, FAKE, *cc.LISTEN_ARGS]
        self.child = cc.Child(argv, env, lambda ev: None, log=self.logs.append, backoff=backoff)
        self.directory = cc.Directory(lambda: rows, "h", lambda: placed, log=self.logs.append)
        self.arrivals = cc.ArrivalLog(os.path.join(d, "arrivals.jsonl"), "agentd", log=self.logs.append)
        self.carrier = cc.Carrier(directory=self.directory, child=self.child, me=f"h/{name}",
                                  on_request=lambda r, s: self.requests.append((r, s)), arrivals=self.arrivals, log=self.logs.append)
        test.addCleanup(self.close)
        if start:
            self.carrier.start()
            assert until(lambda: self.child.state == "ok"), self.logs

    def close(self) -> None:
        self.carrier.stop()

    def arrival_lines(self) -> list[dict]:
        try:
            with open(self.arrivals.path, encoding="utf-8") as fh:
                return [json.loads(line) for line in fh]
        except FileNotFoundError:
            return []


class Net(Scratch):
    def setUp(self) -> None:
        self.net = self.scratch()

    def node(self, name: str, **kw) -> Node:
        return Node(self, self.net, name, **kw)


class Framing(unittest.TestCase):
    def test_a_record_is_the_prefix_and_its_json_and_comes_back_whole(self):
        rec = request(args={"x": "é "})
        text = cc.frame(rec)
        self.assertTrue(text.startswith("fabric-control/1 {"))
        self.assertEqual(cc.unframe(text), rec)

    def test_what_has_no_prefix_or_is_not_an_object_is_refused_with_a_reason(self):
        for bad in ("hello", '{"kind":"request"}', "fabric-control/2 {}", " fabric-control/1 {}", "fabric-control/1 [1]", "fabric-control/1 nope",
                    "fabric-control/1", None, 5):
            with self.assertRaises(cc.Refused, msg=repr(bad)):
                cc.unframe(bad)
        self.assertEqual(cc.unframe("fabric-control/1 {}"), {}, "positive control: the bare prefix and an object is a record")

    def test_the_relay_only_ops_are_the_four_that_take_the_channel_down_or_ask_about_it(self):
        self.assertEqual(cc.RELAY_ONLY_OPS, {"interweave", "interweave-install", "interweave-start", "interweave-stop"})
        self.assertNotIn("interweave-evidence", cc.RELAY_ONLY_OPS, "evidence goes by both, as any other op")

    def test_the_render_and_the_carrier_name_the_same_endpoint(self):
        self.assertEqual(cc.ENDPOINT, roster.CONTROL_ENDPOINT)
        self.assertEqual(cc.PART_BYTES, 32768)
        self.assertLessEqual(cc.PART_BYTES, 32 * 1024, "the owner's ceiling")

    def test_socket_path_needs_an_absolute_runtime_dir(self):
        self.assertEqual(cc.socket_path({"XDG_RUNTIME_DIR": "/run/user/1"}), "/run/user/1/agent-fabric/control.sock")
        for env in ({}, {"XDG_RUNTIME_DIR": ""}, {"XDG_RUNTIME_DIR": "run"}):
            self.assertIsNone(cc.socket_path(env))

    def test_the_child_sees_no_token_proxy_or_session_variable(self):
        env = cc.child_env({"PATH": "/p", "HOME": "/h", "CLAUDE_BRIDGE_AUTH_TOKEN": "x", "HTTPS_PROXY": "y", "XDG_RUNTIME_DIR": "/r", "AGENT_FABRIC_X": "z"})
        self.assertEqual(env, {"PATH": "/p", "HOME": "/h", "XDG_RUNTIME_DIR": "/r"})
        self.assertEqual(cc.program_path({"HOME": "/h"}), "/h/.local/bin/interweave-human")


class DirectoryCases(unittest.TestCase):
    def test_a_peer_maps_to_its_placed_address_and_back_and_a_stranger_to_nothing(self):
        d = cc.Directory(lambda: ROWS, "h", lambda: PLACED)
        self.assertEqual(d.address_of(PEERS["alice"]), "h/alice")
        self.assertEqual(d.peer_of("h/bob"), PEERS["bob"])
        self.assertIsNone(d.address_of("12D3KooWNobody"), "a PeerId the roster does not hold")
        self.assertIsNone(d.address_of(PEERS["eve"]), "a roster row nobody places is no account")
        self.assertIsNone(d.address_of(None))
        self.assertIsNone(d.peer_of("h/eve"))
        self.assertEqual(d.addresses(), ["h/alice", "h/bob", "h/op"])

    def test_a_row_that_names_a_host_is_addressed_there(self):
        d = cc.Directory(lambda: [{"login": "x", "peer_id": "P", "host": "h2"}], "h", lambda: {"h2/x"})
        self.assertEqual(d.address_of("P"), "h2/x")

    def test_a_roster_that_does_not_verify_admits_nobody_and_says_so_once(self):
        logs = []

        def boom():
            raise roster.RosterError("no origin/main")
        d = cc.Directory(boom, "h", lambda: PLACED, log=logs.append)
        self.assertIsNone(d.address_of(PEERS["alice"]))
        self.assertIsNone(d.address_of(PEERS["alice"]))
        self.assertEqual(len(logs), 1, "said when it was read, not for every message")
        self.assertIn("admitting nobody", logs[0])

    def test_it_reads_the_rows_again_only_when_the_stamp_moves(self):
        calls, stamp = [], [1]
        d = cc.Directory(lambda: calls.append(1) or ROWS, "h", lambda: PLACED, stamp=lambda: stamp[0])
        d.address_of("x"), d.address_of("y")
        self.assertEqual(len(calls), 1)
        stamp[0] = 2
        d.address_of("x")
        self.assertEqual(len(calls), 2)


class ChildCases(Net):
    def test_it_runs_exactly_the_listen_argv_the_rule_names(self):
        self.assertEqual(" ".join(cc.LISTEN_ARGS),
                         "--profile gzcoord listen --json --input --consume --endpoint fabric-control")
        argv_file = os.path.join(self.scratch(), "argv")
        self.node("alice", extra_env={"FAKE_ARGV": argv_file})
        with open(argv_file, encoding="utf-8") as fh:
            self.assertEqual(json.loads(fh.read().splitlines()[0]), list(cc.LISTEN_ARGS))

    def test_a_send_reaches_the_peer_as_a_framed_message_from_the_sender_and_outbound_twice_settles_once(self):
        a, b = self.node("alice"), self.node("bob")
        s = a.child.send(f"{PEERS['bob']}/fabric-control", cc.frame(reply()))
        self.assertEqual(a.child.settle(s, 5), (True, ""))
        self.assertTrue(until(lambda: b.arrival_lines()), b.logs)
        self.assertEqual((b.arrival_lines()[0]["from"], b.arrival_lines()[0]["id"]), ("h/alice", "p1"))
        self.assertEqual(a.child.state, "ok", "the second outbound for the same ref found nothing waiting, and changed nothing")
        self.assertEqual(a.child._pending, {})

    def test_a_send_is_never_pending_and_names_the_peers_fabric_control(self):
        sends = os.path.join(self.scratch(), "sends")
        a, b = self.node("alice", extra_env={"FAKE_SENDS": sends}), self.node("bob")
        self.assertTrue(a.child.settle(a.child.send(f"{PEERS['bob']}/fabric-control", "t"), 5)[0])
        with open(sends, encoding="utf-8") as fh:
            sent = [json.loads(l) for l in fh][0]
        self.assertIs(sent["pending"], False, "a send the child cancels when its wait runs out, never one a later run sends again")
        self.assertEqual(sent["conversation"], f"{PEERS['bob']}/fabric-control")
        self.assertEqual(set(sent), {"conversation", "text", "ref", "pending"})
        # a request the carrier builds goes to <peer>/fabric-control and nowhere else
        s = a.carrier.start_send("h/bob", request())
        self.assertTrue(s.wait(5)[0])
        with open(sends, encoding="utf-8") as fh:
            self.assertEqual({json.loads(l)["conversation"] for l in fh}, {f"{PEERS['bob']}/fabric-control"})
        self.assertIsNotNone(b)

    def test_a_send_while_the_child_is_not_ready_fails_at_once_and_is_not_queued(self):
        n = self.node("alice", start=False)
        s = n.child.send("x/fabric-control", "t")
        self.assertEqual(s.wait(0), (False, "the InterWeave channel is restarting"))
        self.assertEqual(n.child._pending, {}, "nothing is held for a later child")
        n.carrier.start()
        self.assertTrue(until(lambda: n.child.state == "ok"))
        ok, why = n.child.settle(n.child.send(f"{PEERS['bob']}/fabric-control", "t"), 5)
        self.assertFalse(ok)
        self.assertIn("route-unavailable", why, "positive control: now it reaches the child, and the fake network refuses bob")

    def test_the_daemons_refusal_is_the_sends_failure_with_its_token(self):
        n = self.node("alice", extra_env={"FAKE_PROBLEM": "too-large"})
        ok, why = n.child.settle(n.child.send("p/fabric-control", "t"), 5)
        self.assertFalse(ok)
        self.assertIn("too-large", why)

    def test_a_line_the_child_refuses_fails_that_send_and_the_child_goes_on(self):
        n = self.node("alice")
        s = n.child.send("x", "t")   # a conversation that is no PeerId: the real child refuses the line, naming the send's ref
        ok, why = s.wait(5)
        self.assertEqual(ok, False)
        self.assertIn("refused the line", why)
        self.assertEqual(n.child.state, "ok", "and goes on running")

    def test_a_send_after_the_childs_input_closed_fails_and_never_raises(self):
        n = self.node("alice")
        n.child._proc.stdin.close()   # what the supervisor does once the child has ended, while state still says ok
        s = n.child.send("p/fabric-control", "t")
        self.assertEqual(s.wait(0)[0], False)
        self.assertIn("closed", s.wait(0)[1])
        self.assertEqual(n.carrier.send_to(["h/bob"], request(), 1)["h/bob"][0], False)

    def test_a_child_that_answers_nothing_three_sends_running_is_ended_and_restarted(self):
        n = self.node("alice", extra_env={"FAKE_SILENT": "1"})
        pid = n.child._proc.pid
        for _ in range(cc.WEDGED_AFTER):
            ok, _why = n.child.settle(n.child.send("p/fabric-control", "t"), 0.2)
            self.assertFalse(ok)
        self.assertTrue(until(lambda: n.child._proc is not None and n.child._proc.pid != pid and n.child.state == "ok"), n.logs)
        self.assertTrue(any("wedged" in l for l in n.logs))

    def test_a_child_that_stops_reading_is_ended_and_does_not_hold_the_callers_or_its_own_reader(self):
        n = self.node("alice", extra_env={"FAKE_DEAF": "1"})
        pid = n.child._proc.pid
        big = "x" * 40000
        started = time.monotonic()
        results = [n.child.send("p/fabric-control", big) for _ in range(6)]   # 240 KB: past a pipe's 64 KiB
        self.assertLess(time.monotonic() - started, cc.WRITE_WAIT_S + 5, "the writes were bounded")
        self.assertTrue(any(r.ref == "-" and "drain" in r.why for r in results), [r.why for r in results])
        self.assertTrue(until(lambda: n.child._proc is not None and n.child._proc.pid != pid), n.logs)
        self.assertTrue(any("wedged" in l for l in n.logs))

    def test_a_child_that_exits_is_restarted_and_each_exit_is_named(self):
        for code, word in ((3, "no daemon"), (4, "another client holds"), (5, "cannot be used")):
            with self.subTest(code=code):
                n = self.node("alice", extra_env={"FAKE_EXIT": str(code)}, backoff=(0.02,), start=False)
                n.carrier.start()
                self.assertTrue(until(lambda: n.child.restarts >= 2), n.logs)
                self.assertTrue(any(word in l for l in n.logs), n.logs)
                self.assertEqual(n.child.state, "off" if code in cc.OFF_EXITS else "restarting")
                n.close()

    def test_a_program_that_cannot_start_is_off_and_retried(self):
        logs = []
        c = cc.Child(["/nonexistent/interweave-human"], {}, lambda ev: None, log=logs.append, backoff=(0.02,))
        self.addCleanup(c.stop)
        c.start()
        self.assertTrue(until(lambda: c.restarts >= 2))
        self.assertEqual(c.state, "off")
        self.assertTrue(any("cannot start" in l for l in logs))

    def test_stop_ends_the_child(self):
        n = self.node("alice")
        proc = n.child._proc
        n.close()
        self.assertTrue(until(lambda: proc.poll() is not None))


class Inbound(Net):
    def deliver(self, frm: str, to: str, text: str) -> None:
        a = self.nodes[frm]
        ok, why = a.child.settle(a.child.send(f"{PEERS[to]}/fabric-control", text), 5)
        self.assertTrue(ok, why)

    def setUp(self) -> None:
        super().setUp()
        self.nodes = {n: self.node(n) for n in ("alice", "bob", "op")}

    def test_a_request_from_the_address_the_roster_gives_the_peer_is_handed_on(self):
        self.deliver("op", "alice", cc.frame(request()))
        a = self.nodes["alice"]
        self.assertTrue(until(lambda: a.requests), a.logs)
        self.assertEqual(a.requests[0], (request(), "h/op"))
        self.assertEqual(a.arrival_lines()[0]["carrier"], "interweave")
        self.assertEqual(a.arrival_lines()[0]["verdict"], "ok")

    def test_a_forged_from_is_dropped_and_logged_with_its_verdict(self):
        # bob writes the operator's address in `from`: the positive control above is the same record from op's own peer
        self.deliver("bob", "alice", cc.frame(request(rid="forged", frm="h/op")))
        a = self.nodes["alice"]
        self.assertTrue(until(lambda: any("says it is from" in l for l in a.logs)), a.logs)
        self.assertEqual(a.requests, [])
        self.assertEqual(a.arrival_lines()[-1]["verdict"], "forged-from")
        self.assertEqual(a.arrival_lines()[-1]["from"], "h/bob", "logged under the roster's address, never the claim")

    def test_a_peer_the_roster_does_not_hold_is_never_admitted(self):
        stranger = "12D3KooWStranger" + "S" * 36
        d = self.scratch()
        os.makedirs(os.path.join(self.net, stranger))
        env = {"PATH": os.environ["PATH"], "FAKE_NET": self.net, "FAKE_PEER": stranger}
        c = cc.Child([sys.executable, FAKE, *cc.LISTEN_ARGS], env, lambda ev: None, backoff=(0.05,))
        self.addCleanup(c.stop)
        c.start()
        self.assertTrue(until(lambda: c.state == "ok"))
        self.assertTrue(c.settle(c.send(f"{PEERS['alice']}/fabric-control", cc.frame(request(rid="s1", frm="h/op"))), 5)[0])
        a = self.nodes["alice"]
        self.assertTrue(until(lambda: any("PeerId the roster does not hold" in l for l in a.logs)), a.logs)
        self.assertEqual(a.requests, [])
        self.assertEqual(os.listdir(d), [])

    def test_a_message_without_the_prefix_is_dropped(self):
        self.deliver("op", "alice", json.dumps(request(rid="bare")))
        a = self.nodes["alice"]
        self.assertTrue(until(lambda: any("prefix" in l for l in a.logs)), a.logs)
        self.assertEqual(a.requests, [])

    def test_a_relay_only_op_that_arrives_on_interweave_is_dropped(self):
        for op in sorted(cc.RELAY_ONLY_OPS):
            self.deliver("op", "alice", cc.frame(request(rid=f"x-{op}", op=op)))
        self.deliver("op", "alice", cc.frame(request(rid="ev", op="interweave-evidence")))
        a = self.nodes["alice"]
        self.assertTrue(until(lambda: [r for r, _ in a.requests if r["id"] == "ev"]), a.logs)
        self.assertEqual([r["id"] for r, _ in a.requests], ["ev"], "evidence got through, the four did not")
        self.assertEqual(sum(1 for l in a.arrival_lines() if l["verdict"] == "relay-only-op"), 4)

    def test_a_message_for_another_endpoint_of_the_profile_is_not_ours(self):
        a = self.nodes["alice"]
        a.carrier.inbound({"direction": "in", "local_endpoint": "gzcoord", "author": PEERS["op"], "text": cc.frame(request(rid="other"))})
        a.carrier.inbound({"direction": "in", "local_endpoint": None, "author": PEERS["op"], "text": cc.frame(request(rid="drained"))})
        self.assertEqual([r["id"] for r, _ in a.requests], ["drained"], "null is a row drained from the store: fabric-control's by the render")

    def test_a_reply_goes_to_the_waiter_of_its_request_and_only_from_the_peer_its_from_names(self):
        op = self.nodes["op"]
        got = []
        op.carrier.watch("r1", lambda rec, sender: got.append((rec["id"], sender)))
        self.deliver("alice", "op", cc.frame(reply(rid="p-ok", to="r1", frm="h/alice")))
        self.deliver("bob", "op", cc.frame(reply(rid="p-forged", to="r1", frm="h/alice")))
        self.deliver("bob", "op", cc.frame(reply(rid="p-other", to="elsewhere", frm="h/bob")))
        self.assertTrue(until(lambda: len(op.arrival_lines()) >= 3), op.logs)
        self.assertEqual(got, [("p-ok", "h/alice")], "a copy bob wrote in alice's name is not alice's answer")
        verdicts = {l["id"]: l["verdict"] for l in op.arrival_lines()}
        self.assertEqual(verdicts, {"p-ok": "ok", "p-forged": "forged-from", "p-other": "no-waiter"})
        op.carrier.unwatch("r1")
        self.deliver("alice", "op", cc.frame(reply(rid="p-late", to="r1")))
        self.assertTrue(until(lambda: any(l["id"] == "p-late" for l in op.arrival_lines())))
        self.assertEqual(got, [("p-ok", "h/alice")], "unwatched: nobody is told")

    def test_a_reply_is_sent_to_the_sender_of_the_request_by_its_roster_peer(self):
        a, op = self.nodes["alice"], self.nodes["op"]
        got = []
        op.carrier.watch("r1", lambda rec, sender: got.append(rec["id"]))
        a.carrier.reply(request(), reply(rid="p9"))
        self.assertTrue(until(lambda: got == ["p9"]), a.logs + op.logs)

    def test_no_reply_goes_for_a_relay_only_op_and_none_to_a_sender_without_a_row(self):
        a = self.nodes["alice"]
        for op in cc.RELAY_ONLY_OPS:
            a.carrier.reply(request(op=op), reply())
        a.carrier.reply(request(frm="h/stranger"), reply())
        self.assertEqual(sum(1 for p in os.listdir(os.path.join(self.net, PEERS["op"])) if not p.startswith(".")), 0)
        self.assertTrue(any("no roster row" in l for l in a.logs))

    def test_an_account_does_not_send_to_itself(self):
        a = self.nodes["alice"]
        self.assertEqual(a.carrier.send_to(["h/alice"], request(), 1)["h/alice"][0], False)

    def test_the_inbound_queue_is_bounded_and_drops_the_oldest_with_a_line(self):
        gate, seen, logs = threading.Event(), [], []

        def slow(ev):
            gate.wait()
            seen.append(ev["n"])
        inbox = cc.Inbox(slow, logs.append, limit=3)
        inbox.start()
        for n in range(8):
            inbox.put({"n": n})
        gate.set()
        self.assertTrue(until(lambda: len(seen) >= 3))
        inbox.close()
        self.assertEqual(seen[-3:], [5, 6, 7], "the newest survive")
        self.assertGreaterEqual(inbox.dropped, 4)
        self.assertTrue(any("dropped the oldest" in l for l in logs))

    def test_one_message_that_breaks_the_handler_does_not_end_the_queue(self):
        done, logs = [], []

        def handle(ev):
            if ev["n"] == 0:
                raise RuntimeError("boom")
            done.append(ev["n"])
        inbox = cc.Inbox(handle, logs.append)
        inbox.start()
        inbox.put({"n": 0})
        inbox.put({"n": 1})
        self.assertTrue(until(lambda: done == [1]))
        inbox.close()
        self.assertTrue(any("broke the handler" in l for l in logs))


class SocketCases(Net):
    def setUp(self) -> None:
        super().setUp()
        self.nodes = {n: self.node(n) for n in ("alice", "op")}
        self.sock_dir = os.path.join(self.scratch(), "agent-fabric")
        self.path = os.path.join(self.sock_dir, "control.sock")
        self.server = cc.Server(self.path, self.nodes["op"].carrier, "h/op", log=self.nodes["op"].logs.append)
        self.server.start()
        self.addCleanup(self.server.stop)

    def test_the_socket_is_owner_only_in_an_owner_only_directory(self):
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.sock_dir).st_mode), 0o700)

    def test_a_request_is_sent_per_target_and_the_replies_come_back_with_their_sender(self):
        rec = request(rid="q1", to=["h/alice"])
        s = cc.Session(self.path, rec, ["h/alice", "h/stranger"], 10)
        self.addCleanup(s.close)
        s.wait_sent(5)
        self.assertEqual(s.sent["h/alice"], (True, ""))
        self.assertEqual(s.sent["h/stranger"][0], False)
        self.assertIn("no roster row", s.sent["h/stranger"][1])
        alice = self.nodes["alice"]
        self.assertTrue(until(lambda: alice.requests), alice.logs)
        self.assertEqual(alice.requests[0][0]["id"], "q1")
        alice.carrier.reply(alice.requests[0][0], reply(rid="a1", to="q1"))
        got = []
        self.assertTrue(until(lambda: got.extend(s.poll(0.2)) or got), "the reply was not streamed back")
        self.assertEqual((got[0]["carrier"], got[0]["from"], got[0]["record"]["id"]), ("interweave", "h/alice", "a1"))

    def test_a_reply_that_alice_did_not_send_is_not_streamed(self):
        s = cc.Session(self.path, request(rid="q2"), ["h/alice"], 10)
        self.addCleanup(s.close)
        s.wait_sent(5)
        alice = self.nodes["alice"]
        # alice's peer sends a reply that claims bob's address: the carrier drops it before the waiter
        a = alice.child.settle(alice.child.send(f"{PEERS['op']}/fabric-control", cc.frame(reply(rid="liar", to="q2", frm="h/bob"))), 5)
        self.assertTrue(a[0])
        self.assertTrue(until(lambda: any(l["id"] == "liar" for l in self.nodes["op"].arrival_lines())))
        self.assertEqual(s.poll(0.5), [])

    def test_the_four_relay_only_ops_are_refused_by_the_socket(self):
        for op in sorted(cc.RELAY_ONLY_OPS):
            s = cc.Session(self.path, request(rid="x-" + op, op=op), ["h/alice"], 5)
            self.addCleanup(s.close)
            with self.assertRaises(RuntimeError) as cm:
                s.wait_sent(5)
            self.assertIn("relay only", str(cm.exception))
        self.assertEqual(self.nodes["alice"].requests, [], "none was sent")

    def test_a_record_that_is_not_this_accounts_own_is_refused(self):
        s = cc.Session(self.path, request(rid="x", frm="h/alice"), ["h/alice"], 5)
        self.addCleanup(s.close)
        with self.assertRaises(RuntimeError) as cm:
            s.wait_sent(5)
        self.assertIn("this agentd is h/op", str(cm.exception))

    def test_a_malformed_request_is_refused_with_its_reason(self):
        for line in (b"junk\n", b'{"op":"x"}\n', b'{"op":"send","record":{"kind":"request","id":"i"},"to":"h/a","wait_s":5}\n',
                     b'{"op":"send","record":{"kind":"request","id":"i"},"to":[],"wait_s":0}\n',
                     b'{"op":"send","record":{"kind":"reply","id":"i"},"to":[],"wait_s":5}\n'):
            with self.subTest(line=line):
                c = socket.socket(socket.AF_UNIX)
                c.settimeout(5)
                c.connect(self.path)
                c.sendall(line)
                self.assertIn(b'"event":"refused"', c.recv(4096))
                c.close()

    def test_wait_s_is_any_positive_number_up_to_a_day_and_nothing_else(self):
        for wait, accepted in ((5, True), (7200, True), (86400, True), (86401, False), (0, False), (-1, False), (True, False), ("5", False)):
            c = socket.socket(socket.AF_UNIX)
            c.settimeout(5)
            c.connect(self.path)
            c.sendall(json.dumps({"op": "send", "record": request(rid=f"w{wait}"), "to": [], "wait_s": wait}).encode() + b"\n")
            first = c.recv(4096)
            self.assertEqual(b'"event":"refused"' not in first, accepted, (wait, first))
            c.close()

    def test_a_ctl_that_stops_reading_loses_its_waiter_and_never_stalls_the_inbox_thread(self):
        patch = mock.patch.object(cc, "SOCKET_SEND_S", 0.3)
        patch.start()
        self.addCleanup(patch.stop)
        s = cc.Session(self.path, request(rid="stuck", to=["h/alice"]), ["h/alice"], 60)
        self.addCleanup(s.close)
        s.wait_sent(5)   # ctl now reads nothing more
        op = self.nodes["op"]
        big = {"kind": "reply", "id": "x", "in_reply_to": "stuck", "from": "h/alice", "data": {"pad": "x" * 200000}}
        t0 = time.monotonic()
        for _ in range(40):
            waiter = op.carrier._waiters.get("stuck")
            if waiter is None:
                break
            waiter(big, "h/alice")
        self.assertIsNone(op.carrier._waiters.get("stuck"), "the connection was dropped with its waiter")
        self.assertLess(time.monotonic() - t0, 40, "bounded, not for the rest of wait_s")
        self.assertTrue(any("not reading" in l for l in op.logs), op.logs)

    def test_a_peer_of_another_user_is_closed_unread(self):
        from unittest import mock
        with mock.patch.object(cc, "_peer_uid", return_value=os.getuid() + 1):
            c = socket.socket(socket.AF_UNIX)
            c.settimeout(5)
            c.connect(self.path)
            # The link closes at accept, before it reads: a loaded runner lets that close land
            # before our send (EPIPE) or after it, with the line unread (ECONNRESET on recv).
            # Either is "closed unread"; only bytes coming back would be a failure.
            # recv still runs after a broken send: a refusal written before the close stays readable.
            try:
                c.sendall(b'{"op":"send"}\n')
            except (BrokenPipeError, ConnectionResetError):
                pass
            try:
                answer = c.recv(4096)
            except ConnectionResetError:
                answer = b""
            self.assertEqual(answer, b"", "closed without a word, not refused with a reason a stranger could read")
            c.close()
        self.assertTrue(any("another user" in l for l in self.nodes["op"].logs))

    def test_the_sends_are_bounded_by_the_requests_own_ttl(self):
        # the child never answers: the send must end at the request's ttl_s (1 s), not at the 30 s ctl will wait for replies
        self.nodes["op"].child.send = lambda conversation, text: cc.Send("never")
        t0 = time.monotonic()
        s = cc.Session(self.path, request(rid="slow", to=["h/alice"], ttl_s=1), ["h/alice"], 30)
        self.addCleanup(s.close)
        s.wait_sent(10)
        self.assertLess(time.monotonic() - t0, 5, "the send gave up at the ttl, not at wait_s")
        self.assertFalse(s.sent["h/alice"][0])
        self.assertIn("no answer from the child", s.sent["h/alice"][1])
        self.assertEqual(self.nodes["alice"].requests, [], "and nothing was left to arrive later")

    def test_a_stale_socket_is_replaced_and_a_live_one_is_never_taken(self):
        other = cc.Server(self.path, self.nodes["op"].carrier, "h/op")
        with self.assertRaises(OSError) as cm:
            other.start()
        self.assertIn("held by a running agentd", str(cm.exception))
        self.server.stop()
        stale = socket.socket(socket.AF_UNIX)
        stale.bind(self.path)
        stale.close()   # the file stays, nobody answers
        again = cc.Server(self.path, self.nodes["op"].carrier, "h/op")
        again.start()
        self.addCleanup(again.stop)
        s = cc.Session(self.path, request(rid="q3", to=["h/alice"]), ["h/alice"], 5)
        self.addCleanup(s.close)
        s.wait_sent(5)
        self.assertTrue(s.sent["h/alice"][0])

    def test_no_agentd_on_the_path_is_a_runtime_error_the_caller_can_say(self):
        with self.assertRaises(RuntimeError) as cm:
            cc.Session(os.path.join(self.sock_dir, "absent.sock"), request(), ["h/alice"], 5)
        self.assertIn("does not answer", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
