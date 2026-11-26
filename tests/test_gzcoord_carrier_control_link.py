#!/usr/bin/env python3
"""Tests for tools/fabric/gzcoord/carrier/control_link.py — the control plane's InterWeave carrier (ADR-029 rule 18).

The child is tests/fake_interweave_human.py, a stand-in that prints what the real 0.2.0 child printed when it
was measured (outbound twice, `author` the sender's PeerId, `local_endpoint`), over a directory that plays the
network. Nothing here starts a daemon or touches the relay. The environment each child gets is minimal and
explicit, and every temporary directory is removed however a case ends.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
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

    def __init__(self, test: Scratch, net: str, name: str, *, rows=ROWS, placed=PLACED, backoff=(0.05,), extra_env=None, start=True, relay_off=False):
        self.name, self.logs, self.requests = name, [], []
        d = test.scratch()
        self.dir = d
        env = {"PATH": os.environ["PATH"], "FAKE_NET": net, "FAKE_PEER": PEERS[name], **(extra_env or {})}
        argv = [sys.executable, FAKE, *cc.LISTEN_ARGS]
        self.child = cc.Child(argv, env, lambda ev: None, log=self.logs.append, backoff=backoff)
        self.directory = cc.Directory(lambda: rows, "h", lambda: placed, log=self.logs.append)
        self.arrivals = cc.ArrivalLog(os.path.join(d, "arrivals.jsonl"), "agentd", log=self.logs.append)
        self.carrier = cc.Carrier(directory=self.directory, child=self.child, me=f"h/{name}",
                                  on_request=lambda r, s: self.requests.append((r, s)), arrivals=self.arrivals, log=self.logs.append,
                                  relay_off=relay_off)
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
        self.assertEqual(cc.CARRIER_ACTION_OPS, {"interweave-install", "interweave-start", "interweave-stop"}, "what no mode carries")
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

    def test_slow_hand_overs_count_against_the_budget_and_the_rest_are_never_sent(self):
        n = self.node("alice")
        def slow(address, record):
            time.sleep(0.3)   # a child that drains its pipe slowly: each hand-over takes this long
            return cc.failed("slow stub")
        t0 = time.monotonic()
        with mock.patch.object(n.carrier, "start_send", slow):
            got = n.carrier.send_to([f"h/a{i}" for i in range(10)], request(), 1.0)
        took = time.monotonic() - t0
        self.assertLess(took, 1.0 + 0.5, f"the hand-overs ran past the budget: {took:.1f}s")
        never = [a for a, (ok, why) in got.items() if why == cc.OUT_OF_TIME]
        self.assertTrue(0 < len(never) < 10, got)
        self.assertEqual(sorted(got), sorted(f"h/a{i}" for i in range(10)), "every address has an outcome")

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


class PinnedDigest(Scratch):
    """Child's check on the real program_check: the installed interweave-human is hashed against release.json at each spawn."""

    BODY = b"the pinned program"

    def setUp(self) -> None:
        d = self.scratch()
        os.makedirs(os.path.join(d, ".local", "bin"))
        self.program = os.path.join(d, ".local", "bin", cc.PROGRAM_NAME)
        self.release = os.path.join(d, "release.json")
        self.env = {"HOME": d, "GZCOORD_CARRIER_RELEASE": self.release, "PATH": os.environ["PATH"]}
        self.pin()
        self.spawns, self.logs = [], []

    def pin(self, digest: str | None = None, key: str = cc.PROGRAM_NAME) -> None:
        digest = hashlib.sha256(self.BODY).hexdigest() if digest is None else digest
        entry = {"program_sha256": {key: digest}}
        with open(self.release, "w") as fh:
            json.dump({"current": "9.9.9", "releases": {"9.9.9": {platform.machine(): entry}}}, fh)

    def install(self, body: bytes) -> None:
        with open(self.program, "wb") as fh:
            fh.write(body)
        os.chmod(self.program, 0o755)

    def popen(self, *a, **k):
        self.spawns.append(a)
        raise OSError("fake: no process")

    def child(self) -> "cc.Child":
        c = cc.Child([self.program, *cc.LISTEN_ARGS], {}, lambda ev: None, log=self.logs.append, popen=self.popen,
                     backoff=(0.02,), check=cc.program_check(self.env))
        self.addCleanup(c.stop)
        return c

    def refused(self, c, text: str) -> None:
        c.start()
        self.assertTrue(until(lambda: c.restarts >= 2), self.logs)
        self.assertEqual(self.spawns, [])
        self.assertEqual(c.state, "off")
        lines = [l for l in self.logs if l.startswith("not starting")]
        self.assertTrue(lines and all(text in l for l in lines), self.logs)

    def test_a_matching_digest_spawns(self):
        self.install(self.BODY)
        c = self.child()
        c.start()
        self.assertTrue(until(lambda: self.spawns), self.logs)
        self.assertFalse([l for l in self.logs if l.startswith("not starting")])

    def test_a_different_digest_is_refused(self):
        self.install(b"a lookalike")
        self.refused(self.child(), "is not the pinned release's interweave-human")

    def test_a_missing_file_is_refused(self):
        self.refused(self.child(), "cannot be read")

    def test_a_pin_without_the_key_is_refused(self):
        self.install(self.BODY)
        self.pin(key="transportctl")
        self.refused(self.child(), "pins no program_sha256 for interweave-human")

    def test_a_malformed_digest_is_refused(self):
        self.install(self.BODY)
        self.pin(digest="ABC")
        self.refused(self.child(), "not lowercase hex SHA-256")

    def test_a_corrected_install_spawns_on_the_next_restart(self):
        self.install(b"a lookalike")
        c = self.child()
        c.start()
        self.assertTrue(until(lambda: c.restarts >= 1), self.logs)
        self.assertEqual(self.spawns, [])
        self.install(self.BODY)
        self.assertTrue(until(lambda: self.spawns), self.logs)

    def test_a_check_that_raises_refuses_and_the_supervisor_lives(self):
        def broken():
            raise RuntimeError("boom")
        c = cc.Child([self.program], {}, lambda ev: None, log=self.logs.append, popen=self.popen, backoff=(0.02,), check=broken)
        self.addCleanup(c.stop)
        self.refused(c, "the digest check failed (RuntimeError: boom)")

    def agentd_start(self, digest_of_body: bytes) -> tuple[list, str]:
        """start_for_agentd as agentd calls it (no argv): the program writes a marker if it is ever run."""
        marker = os.path.join(self.env["HOME"], "ran")
        self.install(f"#!/bin/sh\n: > {marker}\n".encode())
        self.pin(digest=hashlib.sha256(digest_of_body).hexdigest())
        logs = []
        env = {**self.env, "AGENT_FABRIC_STATE_DIR": self.scratch()}
        with mock.patch.dict(os.environ, {"AGENT_FABRIC_STATE_DIR": env["AGENT_FABRIC_STATE_DIR"]}):
            running = cc.start_for_agentd(me="h/alice", on_request=lambda r, s: None, placed=lambda: PLACED, env=env, log=logs.append,
                                          directory=cc.Directory(lambda: ROWS, "h", lambda: PLACED, log=logs.append))
        self.addCleanup(running.stop)
        return logs, marker

    def test_agentd_start_refuses_a_program_the_release_does_not_pin(self):
        logs, marker = self.agentd_start(b"something else")
        self.assertTrue(until(lambda: any(l.startswith("not starting") for l in logs)), logs)
        time.sleep(0.3)
        self.assertFalse(os.path.exists(marker), "the unpinned program ran")

    def test_agentd_start_runs_the_pinned_program(self):
        # The positive control of the refusal above: same wiring, the file the release pins.
        marker = os.path.join(self.env["HOME"], "ran")
        body = f"#!/bin/sh\n: > {marker}\n".encode()
        logs, _ = self.agentd_start(body)
        self.assertTrue(until(lambda: os.path.exists(marker)), logs)

    def test_an_injected_argv_is_not_checked(self):
        logs = []
        argv = [sys.executable, FAKE, *cc.LISTEN_ARGS]
        with mock.patch.dict(os.environ, {"GZCOORD_CARRIER_RELEASE": self.release}):
            running = cc.start_for_agentd(me="h/alice", on_request=lambda r, s: None, placed=lambda: PLACED,
                                          env=self.env, log=logs.append, argv=argv,
                                          directory=cc.Directory(lambda: ROWS, "h", lambda: PLACED, log=logs.append))
        self.addCleanup(running.stop)
        # The fake exits 1 without FAKE_NET, which child_env withholds: that it ran at all is the point.
        self.assertTrue(until(lambda: any("the child exited" in l for l in logs)), logs)
        self.assertFalse([l for l in logs if l.startswith("not starting")], logs)


class LegReady(Net):
    """j163: after a restart the first InterWeave replies failed or came 5-91 s late because the roster (gpg per row) was verified
    inside the first send's budget and agentd took requests before its child had a session."""

    def start(self, slow: float = 0.2, **kw):
        sock_dir = self.scratch()
        self.ready_file = os.path.join(self.scratch(), "ready")
        logs: list[str] = []
        calls: list[bool] = []
        sock = self.sock = os.path.join(sock_dir, "agent-fabric", cc.SOCKET_NAME)

        def rows():
            calls.append(os.path.exists(sock))   # whether fabric-ctl could already connect while the roster was being verified
            time.sleep(slow)
            return ROWS
        env = {"PATH": os.environ["PATH"], "XDG_RUNTIME_DIR": sock_dir, "HOME": self.scratch()}
        child_env = {"PATH": os.environ["PATH"], "FAKE_NET": self.net, "FAKE_PEER": PEERS["alice"], "FAKE_READY_FILE": self.ready_file}
        directory = cc.Directory(rows, "h", lambda: PLACED, log=logs.append)
        with mock.patch.dict(os.environ, {"AGENT_FABRIC_STATE_DIR": self.scratch()}), mock.patch.object(cc, "child_env", lambda e=None: child_env):
            running = cc.start_for_agentd(me="h/alice", on_request=lambda r, s: None, placed=lambda: PLACED, env=env, log=logs.append,
                                          argv=[sys.executable, FAKE, *cc.LISTEN_ARGS], directory=directory, **kw)
        self.addCleanup(running.stop)
        return running, directory, logs, calls, sock

    def test_it_returns_with_the_roster_verified_and_the_child_in_session_and_binds_the_socket_last(self):
        threading.Timer(0.6, lambda: open(self.ready_file, "w").close()).start()
        t0 = time.monotonic()
        running, directory, logs, calls, sock = self.start(ready_wait_s=20)
        self.assertGreaterEqual(time.monotonic() - t0, 0.5, "returned before the child had its session")
        self.assertEqual(running.carrier.child.state, "ok", logs)
        self.assertEqual(calls, [False], "the roster was verified once, and before the socket was bound")
        self.assertTrue(os.path.exists(sock))
        t1 = time.monotonic()
        self.assertEqual(directory.address_of(PEERS["bob"]), "h/bob")
        self.assertLess(time.monotonic() - t1, 0.1, "the first lookup after the start verified the roster again")
        self.assertEqual(len(calls), 1)
        self.assertTrue(any("roster verified in" in l and "child ok" in l for l in logs), logs)

    def test_a_leg_not_ready_in_time_is_said_and_the_socket_is_still_served(self):
        # the positive control of the case above: the same child, its ready file never made
        running, _d, logs, _calls, sock = self.start(ready_wait_s=0.5)
        self.assertEqual(running.carrier.child.state, "restarting")
        self.assertTrue(any("not ready in 0.5 s" in l for l in logs), logs)
        self.assertTrue(os.path.exists(sock))

    def test_without_a_wait_nothing_is_held_back(self):
        t0 = time.monotonic()
        running, _d, _logs, calls, sock = self.start()
        self.assertLess(time.monotonic() - t0, 5)
        self.assertEqual(calls, [], "the roster is left to the first lookup, as before the wait existed")
        self.assertTrue(os.path.exists(sock))

    def test_a_roster_check_that_outlasts_the_wait_does_not_hold_the_caller_past_it(self):
        # j163 review F3: the check runs git and gpg with timeouts of their own; the bound is the caller's, not theirs
        t0 = time.monotonic()
        running, _d, logs, calls, sock = self.start(ready_wait_s=0.5, slow=3.0)
        self.assertLess(time.monotonic() - t0, 2.5)
        self.assertTrue(any("roster not verified" in l and "not ready in 0.5 s" in l for l in logs), logs)
        self.assertTrue(os.path.exists(sock))

    def test_the_stop_hook_is_given_before_the_wait_so_a_leave_during_it_stops_the_child(self):
        # when the hook is given, not only that it was: inside the wait (0.3 s), not after it
        at_hook: list = []
        t0 = time.monotonic()
        running, _d, _logs, _c, _s = self.start(ready_wait_s=0.3, on_started=lambda f: at_hook.append((f, time.monotonic() - t0, os.path.exists(self.sock))))
        self.assertEqual([f for f, _t, _e in at_hook], [running.carrier.stop])
        self.assertFalse(at_hook[0][2], "the hook was given after fabric-ctl's socket was bound")
        self.assertLess(at_hook[0][1], 0.25, "the hook was given after the readiness wait")
        self.assertGreaterEqual(time.monotonic() - t0, 0.3, "positive control: the wait did take its 0.3 s")

    def test_the_inbox_waits_for_begin_when_the_caller_asks(self):
        running, _d, logs, _c, _s = self.start(begin=False)
        self.assertFalse(running.carrier.inbox._thread.is_alive())
        running.begin()
        self.assertTrue(running.carrier.inbox._thread.is_alive())

    def test_a_send_whose_budget_is_spent_says_0_s_not_a_negative_one(self):
        s = cc.Send("r")
        self.assertEqual(s.wait(-10.9651), (False, "no answer from the child in 0 s"))


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

    def test_the_drop_wording_names_the_path_the_op_takes_in_each_mode(self):
        # relay and dual: the carrier's read is asked on the relay, and so is an action; relay_off: the carrier is alone, an action
        # goes through hostexec and the read is answered when it arrives, so it is never among the dropped.
        self.assertEqual(cc._refusal_why(cc.RELAY_ONLY_OPS), "goes on the relay only")
        self.assertEqual(cc._refusal_why(cc.CARRIER_ACTION_OPS), "goes through hostexec, never on the carrier")
        self.assertNotIn(cc.CARRIER_NAME, cc.CARRIER_ACTION_OPS)

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
        # A reply to a request no session has registered yet is held for it (j160), whoever sent it; it ends as a
        # no-waiter line only when it expires or is evicted.
        self.assertEqual(verdicts, {"p-ok": "ok", "p-forged": "forged-from", "p-other": "held"})
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

    def test_an_account_sends_a_request_to_itself_in_process_and_not_through_the_child(self):
        a = self.nodes["alice"]
        a.child.send = lambda *_: self.fail("a request to this account went to the child")
        rec = request(frm="h/alice", to=["h/alice"])
        self.assertEqual(a.carrier.send_to(["h/alice"], rec, 1)["h/alice"], (True, ""))
        self.assertTrue(until(lambda: a.requests), a.logs)
        self.assertEqual(a.requests, [(rec, "h/alice")])
        self.assertEqual([(l["carrier"], l["verdict"], l["from"]) for l in a.arrival_lines()], [("interweave", "ok", "h/alice")])

    def test_a_loopback_send_neither_counts_toward_nor_resets_the_childs_wedged_tally(self):
        a = self.nodes["alice"]
        a.child._timeouts = 2
        a.carrier.send_to(["h/alice"], request(frm="h/alice"), 1)
        self.assertEqual(a.child._timeouts, 2, "a send that never reached the child said nothing about it")
        # positive control: a send that did go to the child and was answered does reset it
        self.assertEqual(a.carrier.send_to(["h/bob"], request(frm="h/alice", to=["h/bob"]), 5)["h/bob"], (True, ""))
        self.assertEqual(a.child._timeouts, 0)

    def test_what_may_not_go_by_interweave_does_not_loop_back_either(self):
        a = self.nodes["alice"]
        for rec in [request(op=op) for op in cc.RELAY_ONLY_OPS] + [reply(frm="h/alice")]:
            self.assertEqual(a.carrier.send_to(["h/alice"], rec, 1)["h/alice"][0], False, rec)
        time.sleep(0.2)
        self.assertEqual(a.requests, [])

    def test_a_request_the_handler_cannot_take_is_said_and_does_not_stop_the_carrier(self):
        a = self.nodes["alice"]

        def boom(r, s):
            raise RuntimeError("handler broke")
        a.carrier._on_request = boom
        self.assertEqual(a.carrier.send_to(["h/alice"], request(frm="h/alice"), 1)["h/alice"][0], True)
        self.assertTrue(until(lambda: any("handler broke" in l for l in a.logs)), a.logs)

    def test_a_reply_to_a_request_from_this_account_goes_to_its_waiter_in_process(self):
        a = self.nodes["alice"]
        got = []
        a.carrier.watch("r1", lambda rec, sender: got.append((rec["id"], sender)))
        a.child.send = lambda *_: self.fail("a reply to this account went to the child")
        a.carrier.reply(request(frm="h/alice"), reply(rid="p5", frm="h/alice"))
        self.assertEqual(got, [("p5", "h/alice")])
        a.carrier.unwatch("r1")
        a.carrier.reply(request(frm="h/alice"), reply(rid="p6", frm="h/alice"))
        self.assertEqual([l["verdict"] for l in a.arrival_lines()], ["ok", "no-waiter"])

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

    def test_close_returns_only_after_the_handler_has_finished(self):
        # j157: a handler writing the arrival log after close() re-created the scratch dir its owner had removed.
        started, finished = threading.Event(), []

        def slow(ev):
            started.set()
            time.sleep(0.3)
            finished.append(ev["n"])
        inbox = cc.Inbox(slow, lambda l: None)
        inbox.start()
        inbox.put({"n": 1})
        self.assertTrue(started.wait(5))
        inbox.close()
        self.assertEqual(finished, [1], "the handler was still running when close() returned")

    def test_close_drops_the_backlog_and_says_so_and_names_a_handler_that_outlives_the_wait(self):
        gate, seen, logs = threading.Event(), [], []

        def slow(ev):
            gate.wait(5)
            seen.append(ev["n"])
        inbox = cc.Inbox(slow, logs.append)
        inbox.start()
        for n in range(4):
            inbox.put({"n": n})
        self.assertTrue(until(lambda: not inbox._q or len(inbox._q) == 3))
        with mock.patch.object(cc, "CLOSE_WAIT_S", 0.1):
            inbox.close()
        self.assertTrue(any("dropped" in l and "InterWeave alone is lost" in l for l in logs), logs)
        self.assertTrue(any("still running" in l for l in logs), logs)
        gate.set()
        self.assertTrue(until(lambda: not inbox._thread.is_alive()))
        self.assertEqual(seen, [0], "only the message in hand was handled after close")

    def test_a_message_put_after_close_is_not_handled(self):
        seen, logs = [], []
        inbox = cc.Inbox(lambda ev: seen.append(ev["n"]), logs.append)
        inbox.start()
        inbox.close()
        inbox.put({"n": 1})
        self.assertTrue(any("read after close" in l for l in logs), logs)
        self.assertFalse(inbox._thread.is_alive())
        self.assertEqual((seen, len(inbox._q)), ([], 0))

    def test_close_from_the_handler_itself_does_not_wait_for_itself(self):
        done = threading.Event()
        box = []

        def handle(ev):
            box[0].close()
            done.set()
        inbox = cc.Inbox(handle, lambda l: None)
        box.append(inbox)
        inbox.start()
        inbox.put({"n": 1})
        self.assertTrue(done.wait(5))

    def test_close_of_an_inbox_never_started_returns(self):
        cc.Inbox(lambda ev: None, lambda l: None).close()

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


class RelayOff(Net):
    """The carrier alone (control_carrier "interweave", Carrier(relay_off=True)): the carrier's own read rides it, the three actions that
    take the channel down still never do. The default Carrier (relay and dual) is the other half, in the cases above."""

    def setUp(self) -> None:
        super().setUp()
        self.nodes = {n: self.node(n, relay_off=True) for n in ("alice", "op")}
        self.sock_dir = os.path.join(self.scratch(), "agent-fabric")
        self.path = os.path.join(self.sock_dir, "control.sock")
        self.server = cc.Server(self.path, self.nodes["op"].carrier, "h/op", log=self.nodes["op"].logs.append,
                                refused_ops=self.nodes["op"].carrier.refused_ops)
        self.server.start()
        self.addCleanup(self.server.stop)

    def test_the_read_that_arrives_is_handed_on_and_the_three_actions_are_dropped(self):
        a = self.nodes["alice"]
        for op in sorted(cc.CARRIER_ACTION_OPS) + ["interweave"]:
            self.deliver_to_alice(op)
        self.assertTrue(until(lambda: [r for r, _ in a.requests]), a.logs)
        self.assertTrue(until(lambda: len(a.arrival_lines()) == 4), a.logs)
        self.assertEqual([r["op"] for r, _ in a.requests], ["interweave"])
        self.assertEqual(sorted(l["verdict"] for l in a.arrival_lines()), ["ok", "relay-only-op", "relay-only-op", "relay-only-op"])

    def deliver_to_alice(self, op: str) -> None:
        self.nodes["alice"].carrier.inbound({"direction": "in", "local_endpoint": None, "author": PEERS["op"],
                                             "text": cc.frame(request(rid=f"x-{op}", op=op))})

    def test_the_read_is_answered_by_the_carrier_and_an_action_never_is(self):
        a, op = self.nodes["alice"], self.nodes["op"]
        got = []
        op.carrier.watch("r1", lambda rec, sender: got.append(rec["id"]))
        a.carrier.reply(request(rid="r1", op="interweave"), reply(rid="p-read", to="r1"))
        for action in sorted(cc.CARRIER_ACTION_OPS):
            a.carrier.reply(request(rid="r1", op=action), reply(rid=f"p-{action}", to="r1"))
        self.assertTrue(until(lambda: got == ["p-read"]), a.logs + op.logs)
        time.sleep(0.3)
        self.assertEqual(got, ["p-read"], "the actions' replies were not sent")

    def test_the_socket_takes_the_read_and_refuses_each_action_by_name(self):
        s = cc.Session(self.path, request(rid="q-read", op="interweave", to=["h/alice"]), ["h/alice"], 5)
        self.addCleanup(s.close)
        s.wait_sent(5)
        self.assertEqual(s.sent["h/alice"], (True, ""))
        self.assertTrue(until(lambda: self.nodes["alice"].requests), self.nodes["alice"].logs)
        for action in sorted(cc.CARRIER_ACTION_OPS):
            with self.subTest(action):
                t = cc.Session(self.path, request(rid="q-" + action, op=action), ["h/alice"], 5)
                self.addCleanup(t.close)
                with self.assertRaises(RuntimeError) as cm:
                    t.wait_sent(5)
                self.assertIn("through hostexec, never on the carrier", str(cm.exception))
        self.assertEqual([r["id"] for r, _ in self.nodes["alice"].requests], ["q-read"])

    def test_the_operators_own_read_loops_back_and_an_own_action_does_not(self):
        op = self.nodes["op"]
        self.assertEqual(op.carrier.send_to(["h/op"], request(frm="h/op", to=["h/op"], op="interweave"), 1)["h/op"], (True, ""))
        self.assertTrue(until(lambda: op.requests), op.logs)
        for action in sorted(cc.CARRIER_ACTION_OPS):
            self.assertFalse(op.carrier.send_to(["h/op"], request(frm="h/op", to=["h/op"], op=action), 1)["h/op"][0], action)
        self.assertEqual([r["op"] for r, _ in op.requests], ["interweave"])


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

    def test_this_accounts_own_reply_that_beats_its_waiter_is_kept_and_handed_over_at_watch(self):
        # The operator's own row in dual (j164): the relay copy is answered before fabric-ctl's session registers.
        a = self.nodes["alice"]
        a.carrier.reply(request(frm="h/alice"), reply(rid="p7", frm="h/alice"))
        got = []
        a.carrier.watch("r1", lambda rec, sender: got.append((rec["id"], sender)))
        self.assertEqual(got, [("p7", "h/alice")])
        self.assertEqual([l["verdict"] for l in a.arrival_lines()], ["held", "ok"])
        a.carrier.unwatch("r1")
        a.carrier.watch("r1", lambda rec, sender: got.append("again"))
        self.assertEqual(len(got), 1, "a held reply is handed over once")

    def test_a_reply_after_its_session_ended_is_not_kept(self):
        a = self.nodes["alice"]
        a.carrier.watch("r2", lambda *_: None)
        a.carrier.unwatch("r2")
        a.carrier.reply(request(rid="r2", frm="h/alice"), reply(rid="p8", to="r2", frm="h/alice"))
        a.carrier._route_reply(reply(rid="p9", to="r2", frm="h/bob"), "h/bob")
        got = []
        a.carrier.watch("r2", lambda rec, s: got.append(rec))
        self.assertEqual(got, [])
        self.assertEqual([l["verdict"] for l in a.arrival_lines()], ["no-waiter", "no-waiter"])

    def test_a_peers_reply_that_beats_the_session_is_held_and_handed_over_as_that_peers(self):
        # j160: in dual the relay copy is posted first, so a fast peer's InterWeave reply can come before `watch`.
        a = self.nodes["alice"]
        a.carrier._route_reply(reply(rid="p9", to="r3", frm="h/bob"), "h/bob")
        got = []
        a.carrier.watch("r3", lambda rec, sender: got.append((rec["id"], sender)))
        self.assertEqual(got, [("p9", "h/bob")])
        self.assertEqual([(l["verdict"], l["from"]) for l in a.arrival_lines()], [("held", "h/bob"), ("ok", "h/bob")])

    def test_the_replies_held_for_one_request_are_bounded_and_a_dropped_one_names_its_sender(self):
        a = self.nodes["alice"]
        for i in range(cc.EARLY_PER_ID + 1):
            a.carrier._route_reply(reply(rid=f"p{i}", to="r4", frm="h/bob"), "h/bob")
        got = []
        a.carrier.watch("r4", lambda rec, s: got.append(rec))
        self.assertEqual(len(got), cc.EARLY_PER_ID)
        last = a.arrival_lines()[cc.EARLY_PER_ID]
        self.assertEqual((last["verdict"], last["from"]), ("no-waiter", "h/bob"))

    def test_a_second_reply_to_a_held_request_evicts_nobody_when_the_store_is_full(self):
        a = self.nodes["alice"]
        for i in range(cc.EARLY_MAX):
            a.carrier._route_reply(reply(rid=f"p{i}", to=f"q{i}", frm="h/bob"), "h/bob")
        a.carrier._route_reply(reply(rid="px", to="q0", frm="h/bob"), "h/bob")
        self.assertEqual(len(a.carrier._early), cc.EARLY_MAX)
        self.assertEqual(len(a.carrier._early["q0"][0]), 2, "the oldest id keeps both of its replies")
        self.assertEqual([l for l in a.arrival_lines() if l["verdict"] == "no-waiter"], [])

    def test_held_replies_are_bounded_and_expire(self):
        a = self.nodes["alice"]
        for i in range(cc.EARLY_MAX + 5):
            a.carrier._route_reply(reply(rid=f"p{i}", to=f"q{i}", frm="h/bob"), "h/bob")
        self.assertEqual(len(a.carrier._early), cc.EARLY_MAX)
        for k in a.carrier._early:
            a.carrier._early[k] = (a.carrier._early[k][0], time.monotonic() - cc.EARLY_HOLD_S - 1)
        a.carrier._route_reply(reply(rid="px", to="qx", frm="h/bob"), "h/bob")
        self.assertEqual(list(a.carrier._early), ["qx"])
        lines = a.arrival_lines()
        self.assertEqual(sum(1 for l in lines if l["verdict"] == "held"), cc.EARLY_MAX + 6)
        self.assertEqual(sum(1 for l in lines if l["verdict"] == "no-waiter"), cc.EARLY_MAX + 5, "every evicted or expired one is said as no-waiter")
        self.assertEqual({l["from"] for l in lines}, {"h/bob"}, "each under the sender it came from, never this account's")

    def test_the_operators_own_address_is_answered_through_its_own_socket(self):
        op = self.nodes["op"]
        s = cc.Session(self.path, request(rid="q7", frm="h/op", to=["h/op"]), ["h/op"], 10)
        self.addCleanup(s.close)
        s.wait_sent(5)
        self.assertEqual(s.sent["h/op"], (True, ""))
        self.assertTrue(until(lambda: op.requests), op.logs)
        op.carrier.reply(op.requests[0][0], reply(rid="o1", to="q7", frm="h/op"))
        got = []
        self.assertTrue(until(lambda: got.extend(s.poll(0.2)) or got), "the own reply was not streamed back")
        self.assertEqual((got[0]["carrier"], got[0]["from"], got[0]["record"]["id"]), ("interweave", "h/op", "o1"))

    def test_a_reply_that_arrives_in_the_same_chunk_behind_sent_all_is_not_lost(self):
        # The in-process reply of this account can follow `sent-all` at once, in one recv with it.
        path = os.path.join(self.scratch(), "s.sock")
        srv = socket.socket(socket.AF_UNIX)
        self.addCleanup(srv.close)
        srv.bind(path)
        srv.listen(1)
        lines = [{"event": "sent", "to": "h/op", "ok": True, "why": ""}, {"event": "sent-all"},
                 {"event": "reply", "carrier": "interweave", "from": "h/op", "record": reply(rid="o2", to="q8", frm="h/op")}]

        def serve() -> None:
            conn, _ = srv.accept()
            with conn:
                conn.recv(65536)
                conn.sendall("".join(json.dumps(l) + "\n" for l in lines).encode())
                time.sleep(1)
        threading.Thread(target=serve, daemon=True).start()
        s = cc.Session(path, request(rid="q8", frm="h/op"), ["h/op"], 5)
        self.addCleanup(s.close)
        got = s.wait_sent(3)
        self.assertEqual([g["record"]["id"] for g in got], ["o2"])

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
            captured = waiter
            waiter(big, "h/alice")
        self.assertIsNone(op.carrier._waiters.get("stuck"), "the connection was dropped with its waiter")
        self.assertLess(time.monotonic() - t0, 40, "bounded, not for the rest of wait_s")
        self.assertTrue(any("not reading" in l for l in op.logs), op.logs)
        self.assertTrue(any("a reply" in l and "after it opened" in l for l in op.logs), op.logs)
        # One line per session, and the shutdown it did itself is never reported as a ctl that had ended.
        waiter = captured
        waiter(big, "h/alice")   # the inbox thread had captured it before the drop: no second line, no write
        waiter_gone = [l for l in op.logs if "stuck"[:8] in l]
        self.assertEqual(len(waiter_gone), 1, op.logs)
        self.assertNotIn("had ended", waiter_gone[0])

    def test_a_reply_after_ctl_closed_says_the_session_ended_not_that_it_is_not_reading(self):
        s = cc.Session(self.path, request(rid="gone", to=["h/alice"]), ["h/alice"], 60)
        s.wait_sent(5)
        op = self.nodes["op"]
        waiter = op.carrier._waiters["gone"]
        # SHUT_RD, not close(): the server's write then fails with EPIPE while its read sees no EOF, so the session
        # stays open and the write path is reached on every run. After close() the server thread's wake-up races
        # this call, and when it wins the "ended" guard logs the same words whatever the EPIPE branch says.
        self.addCleanup(s.close)
        s._conn.shutdown(socket.SHUT_RD)
        waiter({"kind": "reply", "id": "x", "in_reply_to": "gone", "from": "h/alice"}, "h/alice")
        lines = [l for l in op.logs if "gone"[:8] in l]
        self.assertEqual(len(lines), 1, op.logs)
        self.assertIn("had ended", lines[0])   # the positive control
        self.assertIn("Broken pipe", lines[0])
        self.assertIn("a reply", lines[0])
        self.assertIn("after it opened", lines[0])
        self.assertFalse(any("not reading" in l for l in op.logs), op.logs)

    def test_a_reply_after_the_session_finished_is_not_written_and_logs_once_with_its_age(self):
        s = cc.Session(self.path, request(rid="late", to=["h/alice"]), ["h/alice"], 60)
        s.wait_sent(5)
        op = self.nodes["op"]
        waiter = op.carrier._waiters["late"]
        s.close()
        # The session thread has finished (and its finally marked it) only once it has unwatched; the lock a put
        # takes is the one the marking takes, so a put after this point sees "ended" and never touches the socket.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and op.carrier._waiters.get("late") is not None:
            time.sleep(0.01)
        time.sleep(0.3)
        for _ in range(2):
            waiter({"kind": "reply", "id": "x", "in_reply_to": "late", "from": "h/alice"}, "h/alice")
        lines = [l for l in op.logs if "late" in l]
        self.assertEqual(len(lines), 1, op.logs)
        self.assertIn("had ended", lines[0])
        self.assertIn("s after it opened", lines[0])
        self.assertNotIn("not reading", lines[0])

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

    def test_stopping_the_server_ends_its_accept_thread(self):
        # close() alone leaves an accept() already blocked in the kernel, and that thread outlived the server: in a suite
        # that starts a server per case it answered a later case's connection from a carrier that had been stopped.
        def accepting():
            return [t for t in threading.enumerate() if t.name == "control-carrier-socket" and t.is_alive()]
        self.assertTrue(until(lambda: accepting()), "positive control: the running server has its accept thread")
        self.server.stop()
        self.assertTrue(until(lambda: not accepting(), 3.0), "the accept thread is gone after stop()")

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
