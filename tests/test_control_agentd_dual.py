#!/usr/bin/env python3
"""agentd on both carriers (agent-fabric ADR-029 rule 18), the account's side: the real agentd.main() in a thread of
this process, its relay a tests/test_control_agentd.py FakeRelay, its second carrier a real control_link.Carrier
over tests/fake_interweave_human.py children joined by a directory. The operator's end is a second Carrier of this
process (what the operator's agentd is to fabric-ctl). The background work main() starts beside the loop (the
tickers, the session watcher, the tools report) is replaced by nothing: it is not under test and would touch the
account. Nothing leaves this process or touches a live relay, daemon or home.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from control import agentd, ops  # noqa: E402
from control import sessions as sessions_mod  # noqa: E402
from gzcoord.carrier import control_link as link  # noqa: E402
from test_control_agentd import FakeRelay, executable, iso, now_iso  # noqa: E402
from test_gzcoord_carrier_control_link import FAKE, PEERS, PLACED, ROWS, Node, Scratch, until  # noqa: E402

REGISTRY = {"hosts": {"h": {"operator": "op"}}, "placement": {"alice": "h", "bob": "h"}}


def body(rid: str, **over) -> dict:
    return {"v": 1, "kind": "request", "id": rid, "from": "h/op", "to": ["h/alice"], "op": "ping", "ts": now_iso(), "ttl_s": 30, **over}


class Base(Scratch):
    """No cases: the account's agentd running in this process, and the operator's carrier beside it."""
    carrier = "dual"

    def setUp(self) -> None:
        self.net, self.runtime, self.state, self.home = (self.scratch() for _ in range(4))
        self.operator = self.scratch()
        os.makedirs(os.path.join(self.operator, "runtime", "hosts"))
        with open(os.path.join(self.operator, "runtime", "hosts", "registry.json"), "w", encoding="utf-8") as fh:
            json.dump(REGISTRY, fh)
        self.argv_file = os.path.join(self.home, "argv")
        os.makedirs(os.path.join(self.home, ".local", "bin"))
        # The program agentd runs is where the pinned release's installer puts it: a wrapper, since the child's
        # environment is only what it needs to find its profile.
        executable(os.path.join(self.home, ".local", "bin", "interweave-human"),
                   f"#!/bin/sh\nFAKE_NET={self.net} FAKE_PEER={PEERS['alice']} FAKE_ARGV={self.argv_file} exec {sys.executable} {FAKE} \"$@\"\n")
        self.relay = FakeRelay()
        self.addCleanup(self.relay.close)
        self.logs: list[str] = []
        env = {"HOME": self.home, "XDG_RUNTIME_DIR": self.runtime, "AGENT_FABRIC_STATE_DIR": self.state, "AGENT_FABRIC_OPERATOR": self.operator,
               "CLAUDE_BRIDGE_URL": self.relay.url(), "FABRIC_CONTROL_CHANNEL": "test:control", "FABRIC_CONTROL_CARRIER": self.carrier,
               "PATH": os.environ["PATH"]}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        who = {"host": "h", "agent": "alice", "project": None, "binding": None}
        directory = link.Directory(lambda: ROWS, "h", lambda: PLACED, log=self.logs.append)
        self.patches = [
            mock.patch.object(agentd.gzcoord, "whoami", return_value=who),
            mock.patch.object(agentd.gzcoord, "identity", return_value={"address": "h/alice", "slug": "alice"}),
            mock.patch.object(agentd.gzcoord, "inbox_root", return_value=self.state),
            mock.patch.object(agentd.gzcoord, "integration_config", return_value={"configured": False}),
            mock.patch.object(agentd.gzcoord, "token", return_value="tok"),
            mock.patch.object(link, "default_directory", return_value=directory),
            mock.patch.object(agentd, "POLL_S", 1),
            mock.patch.object(agentd, "watch_source", lambda *a, **k: None),
            mock.patch.object(agentd, "Ticker", lambda *a, **k: SimpleNamespace(start=lambda: None)),
            mock.patch.object(agentd, "start_tools_report", lambda *a, **k: SimpleNamespace(refresh_again=lambda: None)),
            mock.patch.object(sessions_mod, "StateWatcher", lambda **k: SimpleNamespace(tick=lambda: None)),
            mock.patch.object(agentd.pressure, "sampler", lambda: SimpleNamespace(tick=lambda: None)),
            mock.patch.object(agentd, "_stderr", self.logs.append),
        ]
        for q in self.patches:
            q.start()
            self.addCleanup(q.stop)
        self.leaver: list = []
        self.left: list = []   # every exit the daemon asks for: recorded, never made (os._exit would end the suite)
        real_leaver = agentd.leaver
        lv = mock.patch.object(agentd, "leaver", lambda *a, **k: (self.leaver.append(real_leaver(*a, exit=self.left.append, **k)), self.leaver[-1])[1])
        lv.start()
        self.addCleanup(lv.stop)
        self.stop = threading.Event()
        self.ctx_seen: list[dict] = []
        real_answer = agentd.answer

        def spying(request, ctx):
            self.ctx_seen.append({k: ctx.get(k) for k in ("part_bytes", "carrier_evidence_opts")})
            return real_answer(request, ctx)
        a = mock.patch.object(agentd, "answer", spying)
        a.start()
        self.addCleanup(a.stop)
        self.thread = threading.Thread(target=agentd.main, kwargs={"stop": self.stop}, daemon=True)
        self.thread.start()
        self.addCleanup(self.shutdown)
        self.relay.until_waiting()
        if self.carrier == "dual":
            self.assertTrue(until(lambda: os.path.isdir(os.path.join(self.net, PEERS["alice"]))), self.logs)   # its child is up
        self.op = Node(self, self.net, "op")
        self.replies: list[tuple[dict, str]] = []
        self.op.carrier.watch("*", lambda r, s: None)

    def shutdown(self) -> None:
        self.stop.set()
        self.thread.join(timeout=15)
        agentd.run_exit_hooks()
        agentd.EXIT_HOOKS.clear()

    def watch(self, rid: str) -> list[tuple[dict, str]]:
        got: list[tuple[dict, str]] = []
        self.op.carrier.watch(rid, lambda r, s: got.append((r, s)))
        return got

    def send_iw(self, record: dict, via: Node | None = None) -> None:
        node = via or self.op
        ok, why = node.carrier.send_to(["h/alice"], record, 5)["h/alice"]
        self.assertTrue(ok, why)

    def relay_replies(self, rid: str) -> list[dict]:
        return [r for r in self.relay.replies() if r.get("in_reply_to") == rid]


class AgentdDual(Base):
    def test_a_request_by_the_second_carrier_is_answered_by_both_with_the_same_record(self):
        got = self.watch("r1")
        self.send_iw(body("r1"))
        self.assertTrue(until(lambda: got and self.relay_replies("r1")), self.logs)
        self.assertEqual(got[0][1], "h/alice")
        self.assertEqual(got[0][0], self.relay_replies("r1")[0], "the same reply, byte for byte: one record, two carriers")
        self.assertTrue(any("answered ping for h/op (r1) (via interweave)" in l for l in self.logs), self.logs)

    def test_a_request_that_arrives_on_both_is_answered_once(self):
        got = self.watch("dup")
        self.relay.add("h/op", json.dumps(body("dup")))
        self.send_iw(body("dup"))
        self.assertTrue(until(lambda: got and self.relay_replies("dup")), self.logs)
        time.sleep(1.5)
        self.assertEqual((len(got), len(self.relay_replies("dup"))), (1, 1), "one seen-set across both carriers")
        # positive control: a different id is answered, so the silence above is the seen-set's and not a dead loop
        again = self.watch("other")
        self.send_iw(body("other"))
        self.assertTrue(until(lambda: again), self.logs)

    def test_a_request_the_other_way_round_is_answered_once_too(self):
        got = self.watch("dup2")
        self.send_iw(body("dup2"))
        self.assertTrue(until(lambda: got and self.relay_replies("dup2")), self.logs)
        self.relay.add("h/op", json.dumps(body("dup2")))
        time.sleep(1.5)
        self.assertEqual((len(got), len(self.relay_replies("dup2"))), (1, 1))

    def test_a_forged_from_is_not_answered_on_either_carrier(self):
        bob = Node(self, self.net, "bob")
        got = self.watch("forged")
        self.send_iw(body("forged"), via=bob)   # bob writes the operator's address
        time.sleep(1.0)
        self.assertEqual((got, self.relay_replies("forged")), ([], []))

    def test_a_request_older_than_its_ttl_is_dropped(self):
        got = self.watch("old")
        self.send_iw(body("old", ts=iso(time.time() * 1000 - 120_000), ttl_s=5))
        self.assertTrue(until(lambda: any('"expired"' in l and "via interweave" in l for l in self.logs)), self.logs)
        self.assertEqual((got, self.relay_replies("old")), ([], []))
        fresh = self.watch("fresh")
        self.send_iw(body("fresh"))
        self.assertTrue(until(lambda: fresh), "positive control: a fresh one is answered")

    def test_the_relay_only_ops_are_never_answered_when_they_arrive_by_the_second_carrier(self):
        got = self.watch("ro")
        for i, op in enumerate(sorted(link.RELAY_ONLY_OPS)):
            self.op.carrier.watch(f"ro{i}", lambda r, s: got.append((r, s)))
            self.send_iw(body(f"ro{i}", op=op))
        time.sleep(1.0)
        self.assertEqual(got, [])
        from control.upgrade import state_dir
        with open(os.path.join(state_dir(), "control-arrivals.jsonl"), encoding="utf-8") as fh:
            verdicts = [json.loads(l)["verdict"] for l in fh]
        self.assertEqual(verdicts, ["relay-only-op"] * 4, "each was logged with its carrier and why it was dropped")
        # and by the relay the same op IS answered (the relay carries these)
        self.relay.add("h/op", json.dumps(body("ro-relay", op="interweave")))
        self.assertTrue(until(lambda: self.relay_replies("ro-relay")), self.logs)
        self.assertEqual(len(self.relay_replies("ro-relay")), 1)

    def test_a_reply_to_a_relay_request_goes_by_the_second_carrier_too_but_not_for_a_relay_only_op(self):
        got = self.watch("viarelay")
        self.relay.add("h/op", json.dumps(body("viarelay")))
        self.assertTrue(until(lambda: got and self.relay_replies("viarelay")), self.logs)
        ro = self.watch("ro-relay2")
        self.relay.add("h/op", json.dumps(body("ro-relay2", op="interweave")))
        self.assertTrue(until(lambda: self.relay_replies("ro-relay2")), self.logs)
        time.sleep(1.0)
        self.assertEqual(ro, [], "the reply to a relay-only op is relay-only")

    def test_with_the_relay_gone_the_answer_still_comes_by_the_second_carrier(self):
        got = self.watch("nore")
        self.relay.closed.set()
        self.relay.server.shutdown()
        self.relay.server.server_close()
        self.send_iw(body("nore"))
        self.assertTrue(until(lambda: got), self.logs)
        self.assertTrue(until(lambda: any("relay copy of ping reply" in l and "not posted" in l for l in self.logs)), self.logs)

    def test_a_restart_asked_for_while_the_second_carriers_reply_is_going_waits_for_it(self):
        from gzcoord.carrier import control_link as cl
        gate, sent = threading.Event(), []
        left = self.left
        real = cl.Carrier.reply

        def slow(carrier, request, reply):
            gate.wait(10)
            sent.append(reply["id"])
            return real(carrier, request, reply)
        with mock.patch.object(cl.Carrier, "reply", slow):
            got = self.watch("lv")
            self.send_iw(body("lv"))
            self.assertTrue(until(lambda: self.relay_replies("lv")), self.logs)   # the relay copy is posted; the other is held
            leave = self.leaver[0]
            leave.request("the fabric moved")
            time.sleep(0.5)
            self.assertEqual(left, [], "the daemon did not leave with the second copy unsent")
            gate.set()
            self.assertTrue(until(lambda: left == [0]), self.logs)
            self.assertEqual(len(sent), 1)
            self.assertTrue(until(lambda: got), "and the copy reached the operator")

    def ctl_session(self, rid: str, **over) -> "link.Session":
        """fabric-ctl's end on this agentd's socket, asking h/op: what the operator's own session is to its agentd."""
        record = body(rid, **{"from": "h/alice", "to": ["h/op"], **over})
        session = link.Session(link.socket_path(), record, ["h/op"], 30)
        self.addCleanup(session.close)
        session.wait_sent(10)
        return session

    def op_replies(self, rid: str) -> None:
        self.assertTrue(until(lambda: self.op.requests), self.logs)
        self.op.carrier.reply(self.op.requests[0][0], {"v": 1, "kind": "reply", "id": "rp-" + rid, "in_reply_to": rid, "from": "h/op",
                                                       "op": "ping", "ts": now_iso(), "ok": True, "data": {}})

    def test_a_restart_asked_for_during_a_ctl_session_waits_for_it_and_its_replies_still_come(self):
        # j146: the operator's `upgrade fabric` moves its own agentd's code while the same command collects replies.
        session = self.ctl_session("hold")
        self.leaver[0].request("source changed")
        time.sleep(0.5)
        self.assertEqual(self.left, [], "the daemon did not leave under an open fabric-ctl session")
        self.op_replies("hold")
        got: list = []
        self.assertTrue(until(lambda: got.extend(session.poll(0.2)) or got), "the reply after the restart was asked for still comes")
        self.assertEqual(got[0]["from"], "h/op")
        self.assertEqual(self.left, [])
        session.close()
        self.assertTrue(until(lambda: self.left == [0]), "and the daemon leaves once the session is over")

    def test_a_ctl_session_holds_a_restart_back_only_for_the_cap(self):
        with mock.patch.object(link, "HOLD_MAX_S", 0.3):
            self.ctl_session("cap")
            self.leaver[0].request("source changed")
            self.assertTrue(until(lambda: self.left == [0]), "a fabric-ctl left waiting does not keep the daemon on old code")

    def test_the_cap_counts_from_the_hold_though_the_sends_never_finish(self):
        # A child that sends nothing keeps send_to for its whole budget; the cap must not wait for it.
        gate = threading.Event()
        self.addCleanup(gate.set)
        with mock.patch.object(link, "HOLD_MAX_S", 0.3), mock.patch.object(link.Carrier, "send_to", lambda *a, **k: gate.wait(30) and {}):
            session = link.Session(link.socket_path(), body("silent", **{"from": "h/alice", "to": ["h/op"]}), ["h/op"], 30)
            self.addCleanup(session.close)
            time.sleep(0.1)   # the server has accepted the request and taken its hold
            self.leaver[0].request("source changed")
            self.assertTrue(until(lambda: self.left == [0]), "a silent child did not keep the restart back past the cap")

    def test_a_session_opened_after_a_restart_was_asked_for_holds_nothing_new(self):
        first = self.ctl_session("one")
        self.leaver[0].request("source changed")
        late = link.Session(link.socket_path(), body("two", **{"from": "h/alice", "to": ["h/op"]}), ["h/op"], 30)
        self.addCleanup(late.close)
        late.wait_sent(10)
        first.close()
        self.assertTrue(until(lambda: self.left == [0]), "only the session open at the request held it; a later one did not")

    def test_a_request_the_daemon_refused_holds_nothing(self):
        session = link.Session(link.socket_path(), body("nope", **{"from": "h/mallory"}), ["h/op"], 30)
        self.addCleanup(session.close)
        with self.assertRaises(link.SessionRefused):
            session.wait_sent(10)
        self.leaver[0].request("source changed")
        self.assertTrue(until(lambda: self.left == [0]), self.logs)

    def test_an_account_on_both_splits_at_the_bound_the_second_carrier_carries(self):
        got = self.watch("ctx")
        self.send_iw(body("ctx"))
        self.assertTrue(until(lambda: got and self.ctx_seen), self.logs)
        self.assertEqual(self.ctx_seen[0]["part_bytes"], link.PART_BYTES)
        self.assertEqual(self.ctx_seen[0]["carrier_evidence_opts"], {"page_bytes": link.PART_BYTES})

    def test_the_child_is_the_one_listen_with_the_rules_argv_and_exit_ends_it(self):
        self.assertTrue(until(lambda: os.path.exists(self.argv_file)), self.logs)
        with open(self.argv_file, encoding="utf-8") as fh:
            self.assertEqual([json.loads(l) for l in fh], [list(link.LISTEN_ARGS)], "one child, started once")
        self.assertEqual(oct(os.stat(os.path.join(self.runtime, "agent-fabric", "control.sock")).st_mode & 0o777), "0o600")
        self.assertIn(link.Running.stop.__name__, [getattr(h, "__name__", "") for h in agentd.EXIT_HOOKS])
        agentd.run_exit_hooks()
        self.assertFalse(os.path.exists(os.path.join(self.runtime, "agent-fabric", "control.sock")), "the exit hook took the socket down")


class AgentdRelay(Base):
    """Absent or "relay": the daemon is what it was — no child, no socket, no second reply."""
    carrier = "relay"

    def test_a_relay_daemon_starts_no_child_and_no_socket_and_splits_at_the_relays_bound(self):
        got = self.watch("r")
        self.relay.add("h/op", json.dumps(body("r")))
        self.assertTrue(until(lambda: self.relay_replies("r")), self.logs)
        time.sleep(0.5)
        self.assertFalse(os.path.exists(self.argv_file), "no child was started")
        self.assertFalse(os.path.exists(os.path.join(self.runtime, "agent-fabric")), "no socket directory either")
        self.assertEqual(got, [])
        self.assertEqual(self.ctx_seen[0], {"part_bytes": None, "carrier_evidence_opts": None})
        self.assertEqual(agentd.EXIT_HOOKS, [])
        self.assertFalse(any("(via" in l for l in self.logs), "and the log lines are the relay's, byte for byte")


class Parts(unittest.TestCase):
    def test_the_memory_and_evidence_parts_take_the_bound_they_are_given(self):
        from control import carrier_evidence as ev
        rows = [{"t": f"2026-11-01T00:00:{i:02d}Z", "pad": "x" * 100} for i in range(60)]
        page, nxt = ev._page(rows, "t", 2000)
        self.assertTrue(0 < len(page) < 20 and nxt == rows[len(page)]["t"], "a small bound cuts at a second")
        page, nxt = ev._page(rows, "t")
        self.assertEqual((len(page), nxt), (60, None), "the default is the relay's, as it was")
        self.assertEqual(ev.PAGE_BYTES, 64 * 1024)

    def test_a_memory_ctx_part_bytes_reaches_the_harvest(self):
        seen = {}

        def fake_memory(home, **kw):
            seen.update(kw)
            return {"status": "ok", "bundles": []}
        with mock.patch.object(ops, "memory", fake_memory):
            ops.collect("memory", {"part_bytes": 32768})
            self.assertEqual(seen["part_bytes"], 32768)
            seen.clear()
            ops.collect("memory", {})
        self.assertNotIn("part_bytes", seen, "and without it the harvest keeps its own bound")


if __name__ == "__main__":
    unittest.main()
