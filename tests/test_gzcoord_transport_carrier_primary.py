#!/usr/bin/env python3
"""The carrier as the transport of record (InterWeave-only cutover plan row W6): `CarrierPrimary`, the adapter's `wait` op, the relay
as a mirror both ways, and the factory's choice by mode.

Through the real bin/gzcoord-inbox in the protocol suite's scratch environment, a stub relay and a fake carrier on its adapter
socket: in carrier-record a relay that refuses every call changes neither the exit status nor what is shown; an idle arm makes a
bounded number of adapter calls; a message both copies bring is shown once whichever lands first, and the relay's copy is
acknowledged. Beside them the units: the carrier's `wait` (returns at an arrival, at its bound, never spins on a record the ledger
has not settled), a failing carrier raising where a mirror stays silent, the four outcomes of a send as a primary, the relay mirror's
fail-open and back-off, and what `open_transport` builds in each mode. Hermetic: scratch directories, sockets and a stub relay in
this process."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import test_gzcoord_carrier_inbox as C  # noqa: E402 — its World: stub relay, scratch account, message builders
import test_gzcoord_protocol as P  # noqa: E402
from gzcoord import transport  # noqa: E402
from gzcoord.carrier import adapter, engine, server  # noqa: E402
from gzcoord.transport import carrier as carrier_transport, dedup, mode, relay as relay_transport  # noqa: E402

ME = {"address": "h/beta", "slug": "dev"}


def tearDownModule():
    for d in P.SCRATCH:
        shutil.rmtree(d, ignore_errors=True)


class FakeCarrier:
    """The adapter socket's other end: `wait` holds `hold` seconds (or until `release`) and then lists what `records` holds."""

    def __init__(self, env: dict, records: list[dict] | None = None, hold: float = 0.2) -> None:
        self.records = [] if records is None else records
        self.hold, self.calls, self.sends = hold, [], []
        self.stop = threading.Event()
        self.send_answer: dict = {"ok": True, "carried": 1, "queued": 1, "posted": 0}
        self.server = server.Server(server.socket_path(env["XDG_RUNTIME_DIR"]), self.handle)

    def handle(self, req: dict) -> dict:
        self.calls.append(req["op"])
        if req["op"] == "wait":
            self.stop.wait(min(self.hold, float(req["seconds"])))
            return {"ok": True, "records": list(self.records)}
        if req["op"] == "unseen":
            return {"ok": True, "records": list(self.records)}
        if req["op"] == "send":
            self.sends.append(req)
            return self.send_answer
        return {"ok": False, "error": "unexpected"}

    def close(self) -> None:
        self.stop.set()
        self.server.close()


def world_in(mode_name: str, pages=None, records=None, hold: float = 0.2):
    w = C.World(pages if pages is not None else [[]], carrier_records=None)
    agent = os.path.join(w.state, "agents", P.LOGIN)
    os.makedirs(agent, exist_ok=True)
    mode.write(mode_name, "h1/op", agent)
    fake = FakeCarrier(w.env, records, hold)
    return w, fake


class Watch(unittest.TestCase):
    def tearDown(self):
        for w, fake in getattr(self, "worlds", []):
            fake.close()
            w.close()

    def world(self, *a, **kw):
        w, fake = world_in(*a, **kw)
        self.worlds = [*getattr(self, "worlds", []), (w, fake)]
        return w, fake

    def test_a_relay_that_refuses_every_call_changes_neither_exit_status_nor_what_is_shown(self):
        seen = []
        for relay_down in (False, True):            # the control first: the relay answers, with nothing for this login
            w, fake = self.world("carrier-record", records=[C.urec(1)])
            w.relay_down = relay_down
            w.ack_down = relay_down
            r = w.watch()
            self.assertGreater(w.calls, 0, "the relay is asked beside the carrier: the case reaches the mirror")
            seen.append((r.returncode, r.stdout))
        self.assertEqual(seen[0][0], 0)
        self.assertEqual(seen[0][1].count("subject-1"), 1, seen[0][1])
        self.assertEqual(seen[1], seen[0], "same status and same output with the relay refusing everything")

    def test_an_idle_arm_makes_a_bounded_number_of_adapter_calls(self):
        w, fake = self.world("carrier-record", hold=60)          # the carrier holds a wait to its bound: nothing arrives
        r = w.watch(deadline=6)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("subject-", r.stdout)
        self.assertLessEqual(fake.calls.count("wait"), 2, fake.calls)
        self.assertEqual([c for c in fake.calls if c != "wait"], [], "no other op: the wait's answer is the page")
        self.assertLessEqual(w.calls, 2, "and the relay mirror is read once a slice, not spun on")

    def test_a_message_both_copies_bring_is_shown_once_from_the_carrier_and_the_relays_copy_is_acknowledged(self):
        w, fake = self.world("carrier-record", pages=[[C.relay_rec(1)]], records=[C.urec(1)])
        r = w.watch()
        self.assertEqual((r.returncode, r.stdout.count("subject-1")), (0, 1), r.stdout + r.stderr)
        self.assertNotIn("relay seq 1", r.stdout, "the carrier's copy is the one shown: its sender is verified")
        self.assertEqual(w.acks, ["r1"])
        self.assertEqual([bool(x.get("pending")) for x in w.ledger_lines()], [True, False])
        self.assertEqual([x["via"] for x in w.ledger_lines()][0], "interweave")

    def test_the_relays_copy_first_then_the_carriers_is_shown_once(self):
        w, fake = self.world("carrier-record", pages=[[C.relay_rec(2)]])
        first = w.drain()
        fake.records.append(C.urec(2))
        w.pages = [[]]
        second = w.drain()
        self.assertEqual((first.stdout.count("subject-2"), second.stdout.count("subject-2")), (1, 0), first.stdout + second.stdout)
        self.assertEqual(w.acks, ["r2"])

    def test_the_carriers_copy_first_then_the_relays_is_shown_once_and_acknowledged(self):
        w, fake = self.world("carrier-record", records=[C.urec(3)])
        first = w.drain()
        w.pages = [[C.relay_rec(3)]]
        w.calls = 0
        second = w.drain()
        self.assertEqual((first.stdout.count("subject-3"), second.stdout.count("subject-3")), (1, 0), first.stdout + second.stdout)
        self.assertEqual(w.acks, ["r3"], "the relay's late copy is acknowledged, not shown")

    def test_history_in_a_carrier_mode_is_the_journals_and_calls_no_relay(self):
        w, fake = self.world("carrier-only")
        r = subprocess.run([P.INBOX_CMD, "--history"], env=w.env, capture_output=True, text=True, timeout=120,
                           stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("in your journal's last", r.stdout)
        self.assertEqual(w.calls, 0)

    def test_replay_by_seq_in_a_carrier_mode_names_an_unreadable_journal_not_the_carrier(self):
        w, fake = self.world("carrier-only")
        agent = os.path.join(w.state, "agents", P.LOGIN)
        os.makedirs(agent, exist_ok=True)
        with open(os.path.join(agent, "episodic.db"), "wb") as fh:
            fh.write(b"this is not a database " * 400)
        r = subprocess.run([P.INBOX_CMD, "--replay", "1234"], env=w.env, capture_output=True, text=True, timeout=120,
                           stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("your journal could not be read", r.stderr)
        self.assertNotIn("carrier failed", r.stderr)

    def test_carrier_only_calls_the_relay_never(self):
        w, fake = self.world("carrier-only", pages=[[C.relay_rec(4)]], records=[C.urec(4)])
        r = w.watch()
        self.assertEqual((r.returncode, r.stdout.count("subject-4")), (0, 1), r.stdout + r.stderr)
        self.assertEqual((w.calls, w.acks), (0, []), "nothing in the inbox path reached the relay")

    def login(self):
        return subprocess.run(["id", "-un"], capture_output=True, text=True, timeout=10).stdout.strip()

    def marker(self, w):
        return os.path.join(w.env["XDG_RUNTIME_DIR"], "agent-fabric", f"gzcoord-inbox-{self.login()}.relay-down")

    def test_a_carrier_that_is_not_running_ends_the_watch_with_its_line_and_marker(self):
        w, fake = self.world("carrier-record", pages=[[C.relay_rec(5)]])
        fake.close()                                              # the socket is gone: no carrier
        r = w.watch(deadline=8)
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
        self.assertIn(f"fabric-ctl {self.login()} interweave", r.stdout, "the line names the command that says why")
        self.assertIn("carrier", r.stdout)
        self.assertNotIn("relay unreachable", r.stdout)
        self.assertTrue(os.path.exists(self.marker(w)), "the Stop hook's marker: it means the carrier here")
        self.assertNotIn("subject-5", r.stdout, "the relay's copy is not shown by a watch whose record is down")
        self.assertEqual(w.acks, [], "and not acknowledged")

    def test_a_relay_that_is_down_ends_no_watch_while_the_carrier_answers_and_in_relay_record_it_does(self):
        w, fake = self.world("carrier-record", hold=60)
        w.relay_down = True
        r = w.watch(deadline=8)          # the give-up bound is 3 s here: the relay has been down longer than it
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("unreachable", r.stdout)
        self.assertFalse(os.path.exists(self.marker(w)))
        w2, fake2 = self.world("relay-record", hold=60)
        w2.relay_down = True
        r2 = w2.watch(deadline=8)
        self.assertEqual(r2.returncode, 5, "the positive control: the same outage ends a relay-record watch")

    def test_carrier_only_never_starts_the_relay_hosting(self):
        code = ("import sys; sys.path.insert(0, sys.argv[1])\n"
                "from gzcoord import inbox, transport\n"
                "def hosted(cfg, t=None):\n"
                "    open(sys.argv[2], 'a').write('x')\n"
                "    return {'hosted': False, 'started': False}\n"
                "transport.start_hosted = hosted\n"
                "sys.exit(inbox.run([]))\n")
        for mode_name, expect in (("carrier-only", False), ("carrier-record", True)):
            w, fake = self.world(mode_name)
            flag = os.path.join(P.scratch("hosted-"), "called")
            r = subprocess.run([sys.executable, "-c", code, P.TOOLS, flag], env=w.env, capture_output=True, text=True,
                               timeout=120, stdin=subprocess.DEVNULL)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(os.path.exists(flag), expect, mode_name)


class Send(unittest.TestCase):
    def test_a_send_the_carrier_took_is_journaled_as_the_carriers_and_the_relay_is_never_called(self):
        import test_gzcoord_carrier_send as CS
        run = P.scratch("run-")
        carrier = server.Server(server.socket_path(run), lambda req: {"ok": True, "carried": 1, "queued": 1, "posted": 0})
        self.addCleanup(carrier.close)
        relay = P.Relay()
        self.addCleanup(relay.close)
        base = P.scratch("send-primary-")
        state, store = os.path.join(base, "state"), P.id_store()
        agent = os.path.join(state, "agents", P.LOGIN)
        os.makedirs(agent)
        mode.write("carrier-only", "h1/op", agent)
        r = P.send_with(relay.url, P.VALID, AGENT_FABRIC_STATE_DIR=state, AGENT_FABRIC_SECRET_STORE=store, XDG_RUNTIME_DIR=run)
        self.assertEqual(r.code, 0, r.err)
        self.assertEqual(relay.posts, [])
        self.assertEqual(CS.rows(state, store), [("outbound", "accepted", "interweave", None)])


class Units(unittest.TestCase):
    def fake_adapter(self, answer):
        a = adapter.Adapter(path="/x/sock", call=lambda path, req, timeout: answer(req, timeout))
        a.present = lambda: True      # type: ignore[method-assign]
        return a

    # ── the adapter ──────────────────────────────────────────────────
    def test_wait_asks_for_at_most_the_bound_and_gives_the_socket_the_slack(self):
        got = []
        a = self.fake_adapter(lambda req, timeout: got.append((req, timeout)) or {"ok": True, "records": [{"message_id": "m"}]})
        self.assertEqual(a.wait(3600, threading.Event()), [{"message_id": "m"}])
        self.assertEqual(got, [({"op": "wait", "seconds": adapter.WAIT_MAX}, adapter.WAIT_MAX + adapter.WAIT_SLACK)])

    def test_wait_raises_for_every_way_the_carrier_is_not_answering(self):
        def refuse(req, timeout):
            return {"ok": False, "error": "no"}

        def dead(req, timeout):
            raise OSError("reset")
        for ask in (refuse, dead):
            with self.assertRaises(adapter.CarrierError) as cm:
                self.fake_adapter(ask).wait(1, threading.Event())
            self.assertFalse(cm.exception.absent)
        with self.assertRaises(adapter.CarrierError) as cm:
            adapter.Adapter(path="/no/such/socket").wait(1, threading.Event())
        self.assertTrue(cm.exception.absent)
        self.assertTrue(cm.exception.never_reached_it)

    def test_wait_of_an_aborted_slice_asks_nothing(self):
        asked = []
        a = self.fake_adapter(lambda req, timeout: asked.append(req) or {"ok": True, "records": []})
        gone = threading.Event()
        gone.set()
        self.assertEqual(a.wait(5, gone), [])
        self.assertEqual(asked, [])

    def test_post_result_keeps_what_post_answered_and_says_why(self):
        def ans(out):
            return self.fake_adapter(lambda req, timeout: out)
        self.assertEqual(ans({"ok": True, "carried": 2, "queued": 2}).post("m", "t"), "accepted")
        self.assertEqual(ans({"ok": True, "carried": 0, "queued": 0}).post("m", "t"), "not-carried")
        self.assertEqual(ans({"ok": False, "error": "x", "carried": 2, "queued": 1}).post("m", "t"), "failed")
        r = ans({"ok": False, "error": "disk", "carried": 2, "queued": 1}).post_result("m", "t")
        self.assertEqual((r.state, r.proved_unsent), ("failed", False), "some recipients are recorded: not unsent")
        r = ans({"ok": False, "error": "disk", "carried": 2, "queued": 0}).post_result("m", "t")
        self.assertEqual((r.state, r.proved_unsent), ("failed", True))
        self.assertEqual(adapter.Adapter(path="/no/such").post_result("m", "t").state, "absent")
        r = ans({"ok": False, "error": "bad request: ValueError"}).post_result("m", "t")
        self.assertEqual((r.state, r.proved_unsent), ("failed", False), "no queued count: recipients may be recorded")

    def test_the_mirrors_line_for_a_refusal_before_any_record_is_what_it_was_before_the_count(self):
        lines = {}
        for name, out in (("pre-record", {"ok": False, "error": "x", "carried": 0, "queued": 0}),
                          ("partial", {"ok": False, "error": "x", "carried": 2, "queued": 1})):
            saved, sys.stderr = sys.stderr, types.SimpleNamespace(write=lambda s: said.append(s), flush=lambda: None)
            said: list[str] = []
            try:
                self.fake_adapter(lambda req, timeout, out=out: out).post("m", "t")
            finally:
                sys.stderr = saved
            lines[name] = "".join(said)
        self.assertIn("refused (x); the relay carries on", lines["pre-record"])
        self.assertIn("refused (x, 1 recipient(s) recorded)", lines["partial"], "the control: a partly recorded call still says how many")

    def test_post_result_is_silent_on_stderr_unless_it_is_the_mirror(self):
        saved, sys.stderr = sys.stderr, types.SimpleNamespace(write=lambda s: written.append(s), flush=lambda: None)
        written: list[str] = []
        try:
            a = self.fake_adapter(lambda req, timeout: {"ok": False, "error": "no"})
            a.post_result("m", "t")
            self.assertEqual(written, [])
            a.post_result("m", "t", fail_open=True)
            self.assertTrue(written, "the mirror's line says the relay carries on")
        finally:
            sys.stderr = saved

    # ── the carrier's wait op ────────────────────────────────────────
    def carrier(self, records):
        spool = types.SimpleNamespace(unseen=lambda: list(records))
        c = types.SimpleNamespace(spool=spool, stop=threading.Event(), arrival=threading.Event())
        c.wait_unseen = lambda s: engine.Carrier.wait_unseen(c, s)
        return c

    def test_wait_unseen_returns_at_once_with_records_and_at_its_bound_without(self):
        c = self.carrier([{"mid": "a"}])
        t0 = time.monotonic()
        self.assertEqual(c.wait_unseen(30), [{"mid": "a"}])
        self.assertLess(time.monotonic() - t0, 1)
        c = self.carrier([])
        t0 = time.monotonic()
        self.assertEqual(c.wait_unseen(0.5), [])
        self.assertGreaterEqual(time.monotonic() - t0, 0.45, "the positive control: with nothing it does wait")

    def test_wait_unseen_wakes_on_an_arrival_and_not_at_the_next_look(self):
        records: list[dict] = []
        c = self.carrier(records)
        threading.Timer(0.3, lambda: (records.append({"mid": "n"}), c.arrival.set())).start()
        t0 = time.monotonic()
        self.assertEqual(c.wait_unseen(30), [{"mid": "n"}])
        self.assertLess(time.monotonic() - t0, 0.9, "the look interval is 1 s: an arrival does not wait for it")

    def test_wait_unseen_stops_with_the_carrier(self):
        c = self.carrier([])
        c.stop.set()
        t0 = time.monotonic()
        self.assertEqual(c.wait_unseen(3600), [])
        self.assertLess(time.monotonic() - t0, 1)

    def test_wait_unseen_is_clamped_by_the_carrier_whatever_the_caller_asks(self):
        c = self.carrier([])
        saved, engine.MAX_WAIT = engine.MAX_WAIT, 0.4
        try:
            t0 = time.monotonic()
            self.assertEqual(c.wait_unseen(3600), [])      # stop is clear: only the clamp ends it
            self.assertGreaterEqual(time.monotonic() - t0, 0.35, "the positive control: it did wait")
            self.assertLess(time.monotonic() - t0, 2)
        finally:
            engine.MAX_WAIT = saved

    def test_the_wait_op_answers_in_the_adapter_channels_shape_and_a_bad_seconds_is_a_bad_request(self):
        c = self.carrier([{"mid": "a"}])
        out = engine.Carrier.handle_request(c, {"op": "wait", "seconds": 1})
        self.assertEqual(out, {"ok": True, "records": [{"mid": "a"}]})
        with self.assertRaises((TypeError, ValueError)):
            engine.Carrier.handle_request(c, {"op": "wait", "seconds": "soon"})     # the server turns this into ok:false

    # ── CarrierPrimary ───────────────────────────────────────────────
    def primary(self, answer, **kw):
        return carrier_transport.CarrierPrimary(self.fake_adapter(answer), address="h/beta", **kw)

    def test_a_send_is_accepted_or_raises_with_whether_the_carrier_can_hold_it(self):
        p = self.primary(lambda req, t: {"ok": True, "carried": 1, "queued": 1})
        self.assertEqual(p.send("m", "t").state, "accepted")
        p = self.primary(lambda req, t: {"ok": True, "carried": 0, "queued": 0})
        with self.assertRaises(adapter.CarrierError) as cm:
            p.send("m", "t")
        self.assertTrue(p.never_delivered(cm.exception), "no roster member carries it: nothing was recorded")
        p = self.primary(lambda req, t: {"ok": False, "error": "disk", "carried": 2, "queued": 1})
        with self.assertRaises(adapter.CarrierError) as cm:
            p.send("m", "t")
        self.assertFalse(p.never_delivered(cm.exception), "one recipient is recorded and will be sent")

        def dead(req, t):
            raise OSError("timed out")
        p = self.primary(dead)
        with self.assertRaises(adapter.CarrierError) as cm:
            p.send("m", "t")
        self.assertFalse(p.never_delivered(cm.exception), "sent and not answered: the carrier may hold it")
        p = carrier_transport.CarrierPrimary(adapter.Adapter(path="/no/such"), address="h/beta")
        with self.assertRaises(adapter.CarrierError) as cm:
            p.send("m", "t")
        self.assertTrue(p.never_delivered(cm.exception))
        self.assertFalse(p.never_delivered(OSError("x")), "an error that is not the carrier's proves nothing")

    def test_the_mirror_is_unchanged_a_send_to_no_carrier_is_a_state_not_a_raise(self):
        m = carrier_transport.CarrierTransport(adapter.Adapter(path="/no/such"))
        self.assertEqual(m.send("m", "t").state, "absent")
        self.assertEqual(m.receive(1, threading.Event()), [])

    def test_receive_raises_and_the_line_names_the_login_and_the_command_that_says_why(self):
        p = carrier_transport.CarrierPrimary(adapter.Adapter(path="/no/such"), address="h/beta")
        with self.assertRaises(adapter.CarrierError) as cm:
            p.receive(1, threading.Event())
        x = p.explain(cm.exception)
        self.assertEqual(x["code"], 0)
        self.assertIn("fabric-ctl beta interweave", x["line"])
        self.assertFalse(p.refresh(cm.exception))

    def test_a_record_listed_again_at_once_is_not_news(self):
        rec = [{"message_id": "m"}]
        p = self.primary(lambda req, t: {"ok": True, "records": rec})
        saved, carrier_transport.SAME_PAGE_PAUSE_S = carrier_transport.SAME_PAGE_PAUSE_S, 0.4
        try:
            t0 = time.monotonic()
            p.receive(30, threading.Event())
            self.assertLess(time.monotonic() - t0, 0.3, "the first listing is returned as it comes")
            t0 = time.monotonic()
            p.receive(30, threading.Event())
            self.assertGreaterEqual(time.monotonic() - t0, 0.3, "the same listing again waits out the pause")
            gone = threading.Event()
            gone.set()
            t0 = time.monotonic()
            p.receive(30, gone)
            self.assertLess(time.monotonic() - t0, 0.2, "and an abort cuts it")
        finally:
            carrier_transport.SAME_PAGE_PAUSE_S = saved

    def test_newest_is_the_journals_rows_and_without_a_journal_it_raises(self):
        rows = [{"id": "m", "content": "c"}]
        p = self.primary(lambda req, t: {}, journal_newest=lambda n: rows[:n])
        self.assertEqual(p.newest(5), {"messages": rows})
        with self.assertRaises(adapter.CarrierError):
            self.primary(lambda req, t: {}).newest(5)

    # ── the relay as a mirror ────────────────────────────────────────
    def test_the_relay_mirror_fails_open_says_it_once_and_is_not_asked_again_for_a_while(self):
        class Dead:
            name = "relay"

            def __init__(self):
                self.calls = 0

            def send(self, *a):
                self.calls += 1
                raise RuntimeError("down")

            def receive(self, *a):
                self.calls += 1
                raise RuntimeError("down")

        now = [0.0]
        dead = Dead()
        m = relay_transport.RelayMirror(dead, clock=lambda: now[0])     # type: ignore[arg-type]
        saved, sys.stderr = sys.stderr, types.SimpleNamespace(write=lambda s: said.append(s), flush=lambda: None)
        said: list[str] = []
        try:
            self.assertEqual(m.send("m", "t").state, "failed")
            self.assertEqual(m.receive(0, threading.Event()), [])
            self.assertEqual(m.receive(0, threading.Event()), [])
            self.assertEqual(dead.calls, 1, "after a failure, a send's too, nothing is asked of the relay within the back-off")
            now[0] += relay_transport.MIRROR_DOWN_FOR_S + 1
            self.assertEqual(m.receive(0, threading.Event()), [])
            self.assertEqual(dead.calls, 2, "positive control: later it is asked again")
        finally:
            sys.stderr = saved
        self.assertEqual(len([s for s in said if s.strip()]), 1, "one line for the outage")

    def test_the_relay_mirror_is_bounded_by_a_short_call_and_the_relay_as_the_record_is_not(self):
        from gzcoord.inbox_parts import relay as inbox_relay
        timeouts = []
        saved = inbox_relay.api
        inbox_relay.api = lambda tok, path, url=None, method="GET", body=None, timeout=inbox_relay.API_TIMEOUT: (
            timeouts.append(timeout) or {"seq": 1, "messages": []})
        try:
            mirror = relay_transport.RelayMirror(relay_transport.RelayTransport("http://x", "c", "h/beta", "t",
                                                                                 call_timeout=relay_transport.MIRROR_CALL_S))
            mirror.send("m", "t")
            mirror.receive(0, threading.Event())
            mirror.ack("r1")
            self.assertEqual(timeouts, [relay_transport.MIRROR_CALL_S] * 3)
            timeouts.clear()
            relay_transport.RelayTransport("http://x", "c", "h/beta", "t").receive(55, threading.Event())
            self.assertGreater(timeouts[0], 55, "the control: the record's wait keeps the client's own bound")
        finally:
            inbox_relay.api = saved

    def test_the_relay_mirror_takes_a_rotated_token_once_and_says_a_refusal_as_one(self):
        from gzcoord.inbox_parts import relay as inbox_relay
        seen = []

        def api(tok, path, url=None, method="GET", body=None, timeout=inbox_relay.API_TIMEOUT):
            seen.append(tok)
            if tok == "old":
                raise inbox_relay.RelayError("401", 401)
            return {"messages": []}
        saved_api, saved_tok = inbox_relay.api, relay_transport.synced_token
        inbox_relay.api, relay_transport.synced_token = api, lambda: "new"
        try:
            mirror = relay_transport.RelayMirror(relay_transport.RelayTransport("http://x", "c", "h/beta", "old"))
            self.assertEqual(mirror.receive(0, threading.Event()), [])
            self.assertEqual(seen, ["old", "new"], "refused once, retried once with the synced token")
            seen.clear()
            relay_transport.synced_token = lambda: "old"          # the control: nothing fresher to take
            mirror = relay_transport.RelayMirror(relay_transport.RelayTransport("http://x", "c", "h/beta", "old"))
            saved_err, sys.stderr = sys.stderr, types.SimpleNamespace(write=lambda s: said.append(s), flush=lambda: None)
            said: list[str] = []
            try:
                mirror.receive(0, threading.Event())
            finally:
                sys.stderr = saved_err
            self.assertEqual(seen, ["old"])
            self.assertTrue(any("refused the token" in x for x in said), said)
        finally:
            inbox_relay.api, relay_transport.synced_token = saved_api, saved_tok

    def test_the_factory_bounds_the_mirror_and_not_the_primary_relay(self):
        self.assertEqual(self.build("carrier-record").mirrors[0]._relay._call_timeout, relay_transport.MIRROR_CALL_S)
        self.assertIsNone(self.build("relay-record").primary._call_timeout)

    def test_replay_labels_a_row_by_the_journal_only_when_the_caller_says_the_page_is_the_journals(self):
        import io
        from contextlib import redirect_stdout
        from gzcoord.inbox_parts import records
        rec = {"id": "m", "seq": None, "sender": "x/y", "timestamp": "T", "content": C.msg(1), "carrier": "interweave",
               "sender_verified": True}
        out = {}
        for journal in (False, True):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = records.replay({"messages": [rec]}, "c", C.mid(1), {"address": C.ME, "slug": "x"}, None, True, journal)
            out[journal] = (code, json.loads(buf.getvalue()))
        self.assertEqual((out[False][1]["carrier"], out[False][1]["sender_verified"]), (records.RELAY_CARRIER, False),
                         "a relay page claiming to be verified is never believed")
        self.assertEqual((out[True][1]["carrier"], out[True][1]["sender_verified"]), ("interweave", True))

    # ── the factory, by mode ─────────────────────────────────────────
    def build(self, mode_name, **kw):
        d = P.scratch("mode-factory-")
        mode.write(mode_name, "h1/op", d)
        cfg = {"relay_url": "http://127.0.0.1:9", "channel": "c"}
        return transport.open_transport(kw.pop("cfg", cfg), token="t", me=ME, state_dir=d, iso_now=lambda: "2026-11-14T00:00:00Z",
                                        **kw)

    def test_each_mode_builds_its_own_transports(self):
        names = lambda tp: (tp.primary.name, [m.name for m in tp.mirrors], tp.mode)   # noqa: E731
        self.assertEqual(names(self.build("relay-record")), ("relay", ["interweave"], "relay-record"))
        self.assertEqual(names(self.build("carrier-record")), ("interweave", ["relay"], "carrier-record"))
        self.assertIsInstance(self.build("carrier-record").primary, transport.CarrierPrimary)
        self.assertEqual(names(self.build("carrier-only", cfg=None)), ("interweave", [], "carrier-only"))

    def test_journal_off_send_follows_the_modes_primary_with_no_mirror(self):
        got = {}
        for m in ("relay-record", "carrier-record", "carrier-only"):
            tp = self.build(m, journal_off=True, for_send=True)
            got[m] = (tp.primary.name, tp.mirrors)
        self.assertEqual(got, [({"op": "wait", "seconds": adapter.WAIT_MAX}, adapter.WAIT_MAX + adapter.WAIT_SLACK)])

    def test_wait_raises_for_every_way_the_carrier_is_not_answering(self):
        def refuse(req, timeout):
            return {"ok": False, "error": "no"}

        def dead(req, timeout):
            raise OSError("reset")
        for ask in (refuse, dead):
            with self.assertRaises(adapter.CarrierError) as cm:
                self.fake_adapter(ask).wait(1, threading.Event())
            self.assertFalse(cm.exception.absent)
        with self.assertRaises(adapter.CarrierError) as cm:
            adapter.Adapter(path="/no/such/socket").wait(1, threading.Event())
        self.assertTrue(cm.exception.absent)
        self.assertTrue(cm.exception.never_reached_it)

    def test_wait_of_an_aborted_slice_asks_nothing(self):
        asked = []
        a = self.fake_adapter(lambda req, timeout: asked.append(req) or {"ok": True, "records": []})
        gone = threading.Event()
        gone.set()
        self.assertEqual(a.wait(5, gone), [])
        self.assertEqual(asked, [])

    def test_post_result_keeps_what_post_answered_and_says_why(self):
        def ans(out):
            return self.fake_adapter(lambda req, timeout: out)
        self.assertEqual(ans({"ok": True, "carried": 2, "queued": 2}).post("m", "t"), "accepted")
        self.assertEqual(ans({"ok": True, "carried": 0, "queued": 0}).post("m", "t"), "not-carried")
        self.assertEqual(ans({"ok": False, "error": "x", "carried": 2, "queued": 1}).post("m", "t"), "failed")
        r = ans({"ok": False, "error": "disk", "carried": 2, "queued": 1}).post_result("m", "t")
        self.assertEqual((r.state, r.proved_unsent), ("failed", False), "some recipients are recorded: not unsent")
        r = ans({"ok": False, "error": "disk", "carried": 2, "queued": 0}).post_result("m", "t")
        self.assertEqual((r.state, r.proved_unsent), ("failed", True))
        self.assertEqual(adapter.Adapter(path="/no/such").post_result("m", "t").state, "absent")
        r = ans({"ok": False, "error": "bad request: ValueError"}).post_result("m", "t")
        self.assertEqual((r.state, r.proved_unsent), ("failed", False), "no queued count: recipients may be recorded")

    def test_the_mirrors_line_for_a_refusal_before_any_record_is_what_it_was_before_the_count(self):
        lines = {}
        for name, out in (("pre-record", {"ok": False, "error": "x", "carried": 0, "queued": 0}),
                          ("partial", {"ok": False, "error": "x", "carried": 2, "queued": 1})):
            saved, sys.stderr = sys.stderr, types.SimpleNamespace(write=lambda s: said.append(s), flush=lambda: None)
            said: list[str] = []
            try:
                self.fake_adapter(lambda req, timeout, out=out: out).post("m", "t")
            finally:
                sys.stderr = saved
            lines[name] = "".join(said)
        self.assertIn("refused (x); the relay carries on", lines["pre-record"])
        self.assertIn("refused (x, 1 recipient(s) recorded)", lines["partial"], "the control: a partly recorded call still says how many")

    def test_post_result_is_silent_on_stderr_unless_it_is_the_mirror(self):
        saved, sys.stderr = sys.stderr, types.SimpleNamespace(write=lambda s: written.append(s), flush=lambda: None)
        written: list[str] = []
        try:
            a = self.fake_adapter(lambda req, timeout: {"ok": False, "error": "no"})
            a.post_result("m", "t")
            self.assertEqual(written, [])
            a.post_result("m", "t", fail_open=True)
            self.assertTrue(written, "the mirror's line says the relay carries on")
        finally:
            sys.stderr = saved

    # ── the carrier's wait op ────────────────────────────────────────
    def carrier(self, records):
        spool = types.SimpleNamespace(unseen=lambda: list(records))
        c = types.SimpleNamespace(spool=spool, stop=threading.Event(), arrival=threading.Event())
        c.wait_unseen = lambda s: engine.Carrier.wait_unseen(c, s)
        return c

    def test_wait_unseen_returns_at_once_with_records_and_at_its_bound_without(self):
        c = self.carrier([{"mid": "a"}])
        t0 = time.monotonic()
        self.assertEqual(c.wait_unseen(30), [{"mid": "a"}])
        self.assertLess(time.monotonic() - t0, 1)
        c = self.carrier([])
        t0 = time.monotonic()
        self.assertEqual(c.wait_unseen(0.5), [])
        self.assertGreaterEqual(time.monotonic() - t0, 0.45, "the positive control: with nothing it does wait")

    def test_wait_unseen_wakes_on_an_arrival_and_not_at_the_next_look(self):
        records: list[dict] = []
        c = self.carrier(records)
        threading.Timer(0.3, lambda: (records.append({"mid": "n"}), c.arrival.set())).start()
        t0 = time.monotonic()
        self.assertEqual(c.wait_unseen(30), [{"mid": "n"}])
        self.assertLess(time.monotonic() - t0, 0.9, "the look interval is 1 s: an arrival does not wait for it")

    def test_wait_unseen_stops_with_the_carrier(self):
        c = self.carrier([])
        c.stop.set()
        t0 = time.monotonic()
        self.assertEqual(c.wait_unseen(3600), [])
        self.assertLess(time.monotonic() - t0, 1)

    def test_wait_unseen_is_clamped_by_the_carrier_whatever_the_caller_asks(self):
        c = self.carrier([])
        saved, engine.MAX_WAIT = engine.MAX_WAIT, 0.4
        try:
            t0 = time.monotonic()
            self.assertEqual(c.wait_unseen(3600), [])      # stop is clear: only the clamp ends it
            self.assertGreaterEqual(time.monotonic() - t0, 0.35, "the positive control: it did wait")
            self.assertLess(time.monotonic() - t0, 2)
        finally:
            engine.MAX_WAIT = saved

    def test_the_wait_op_answers_in_the_adapter_channels_shape_and_a_bad_seconds_is_a_bad_request(self):
        c = self.carrier([{"mid": "a"}])
        out = engine.Carrier.handle_request(c, {"op": "wait", "seconds": 1})
        self.assertEqual(out, {"ok": True, "records": [{"mid": "a"}]})
        with self.assertRaises((TypeError, ValueError)):
            engine.Carrier.handle_request(c, {"op": "wait", "seconds": "soon"})     # the server turns this into ok:false

    # ── CarrierPrimary ───────────────────────────────────────────────
    def primary(self, answer, **kw):
        return carrier_transport.CarrierPrimary(self.fake_adapter(answer), address="h/beta", **kw)

    def test_a_send_is_accepted_or_raises_with_whether_the_carrier_can_hold_it(self):
        p = self.primary(lambda req, t: {"ok": True, "carried": 1, "queued": 1})
        self.assertEqual(p.send("m", "t").state, "accepted")
        p = self.primary(lambda req, t: {"ok": True, "carried": 0, "queued": 0})
        with self.assertRaises(adapter.CarrierError) as cm:
            p.send("m", "t")
        self.assertTrue(p.never_delivered(cm.exception), "no roster member carries it: nothing was recorded")
        p = self.primary(lambda req, t: {"ok": False, "error": "disk", "carried": 2, "queued": 1})
        with self.assertRaises(adapter.CarrierError) as cm:
            p.send("m", "t")
        self.assertFalse(p.never_delivered(cm.exception), "one recipient is recorded and will be sent")

        def dead(req, t):
            raise OSError("timed out")
        p = self.primary(dead)
        with self.assertRaises(adapter.CarrierError) as cm:
            p.send("m", "t")
        self.assertFalse(p.never_delivered(cm.exception), "sent and not answered: the carrier may hold it")
        p = carrier_transport.CarrierPrimary(adapter.Adapter(path="/no/such"), address="h/beta")
        with self.assertRaises(adapter.CarrierError) as cm:
            p.send("m", "t")
        self.assertTrue(p.never_delivered(cm.exception))
        self.assertFalse(p.never_delivered(OSError("x")), "an error that is not the carrier's proves nothing")

    def test_the_mirror_is_unchanged_a_send_to_no_carrier_is_a_state_not_a_raise(self):
        m = carrier_transport.CarrierTransport(adapter.Adapter(path="/no/such"))
        self.assertEqual(m.send("m", "t").state, "absent")
        self.assertEqual(m.receive(1, threading.Event()), [])

    def test_receive_raises_and_the_line_names_the_login_and_the_command_that_says_why(self):
        p = carrier_transport.CarrierPrimary(adapter.Adapter(path="/no/such"), address="h/beta")
        with self.assertRaises(adapter.CarrierError) as cm:
            p.receive(1, threading.Event())
        x = p.explain(cm.exception)
        self.assertEqual(x["code"], 0)
        self.assertIn("fabric-ctl beta interweave", x["line"])
        self.assertFalse(p.refresh(cm.exception))

    def test_a_record_listed_again_at_once_is_not_news(self):
        rec = [{"message_id": "m"}]
        p = self.primary(lambda req, t: {"ok": True, "records": rec})
        saved, carrier_transport.SAME_PAGE_PAUSE_S = carrier_transport.SAME_PAGE_PAUSE_S, 0.4
        try:
            t0 = time.monotonic()
            p.receive(30, threading.Event())
            self.assertLess(time.monotonic() - t0, 0.3, "the first listing is returned as it comes")
            t0 = time.monotonic()
            p.receive(30, threading.Event())
            self.assertGreaterEqual(time.monotonic() - t0, 0.3, "the same listing again waits out the pause")
            gone = threading.Event()
            gone.set()
            t0 = time.monotonic()
            p.receive(30, gone)
            self.assertLess(time.monotonic() - t0, 0.2, "and an abort cuts it")
        finally:
            carrier_transport.SAME_PAGE_PAUSE_S = saved

    def test_newest_is_the_journals_rows_and_without_a_journal_it_raises(self):
        rows = [{"id": "m", "content": "c"}]
        p = self.primary(lambda req, t: {}, journal_newest=lambda n: rows[:n])
        self.assertEqual(p.newest(5), {"messages": rows})
        with self.assertRaises(adapter.CarrierError):
            self.primary(lambda req, t: {}).newest(5)

    # ── the relay as a mirror ────────────────────────────────────────
    def test_the_relay_mirror_fails_open_says_it_once_and_is_not_asked_again_for_a_while(self):
        class Dead:
            name = "relay"

            def __init__(self):
                self.calls = 0

            def send(self, *a):
                self.calls += 1
                raise RuntimeError("down")

            def receive(self, *a):
                self.calls += 1
                raise RuntimeError("down")

        now = [0.0]
        dead = Dead()
        m = relay_transport.RelayMirror(dead, clock=lambda: now[0])     # type: ignore[arg-type]
        saved, sys.stderr = sys.stderr, types.SimpleNamespace(write=lambda s: said.append(s), flush=lambda: None)
        said: list[str] = []
        try:
            self.assertEqual(m.send("m", "t").state, "failed")
            self.assertEqual(m.receive(0, threading.Event()), [])
            self.assertEqual(m.receive(0, threading.Event()), [])
            self.assertEqual(dead.calls, 1, "after a failure, a send's too, nothing is asked of the relay within the back-off")
            now[0] += relay_transport.MIRROR_DOWN_FOR_S + 1
            self.assertEqual(m.receive(0, threading.Event()), [])
            self.assertEqual(dead.calls, 2, "positive control: later it is asked again")
        finally:
            sys.stderr = saved
        self.assertEqual(len([s for s in said if s.strip()]), 1, "one line for the outage")

    def test_the_relay_mirror_is_bounded_by_a_short_call_and_the_relay_as_the_record_is_not(self):
        from gzcoord.inbox_parts import relay as inbox_relay
        timeouts = []
        saved = inbox_relay.api
        inbox_relay.api = lambda tok, path, url=None, method="GET", body=None, timeout=inbox_relay.API_TIMEOUT: (
            timeouts.append(timeout) or {"seq": 1, "messages": []})
        try:
            mirror = relay_transport.RelayMirror(relay_transport.RelayTransport("http://x", "c", "h/beta", "t",
                                                                                 call_timeout=relay_transport.MIRROR_CALL_S))
            mirror.send("m", "t")
            mirror.receive(0, threading.Event())
            mirror.ack("r1")
            self.assertEqual(timeouts, [relay_transport.MIRROR_CALL_S] * 3)
            timeouts.clear()
            relay_transport.RelayTransport("http://x", "c", "h/beta", "t").receive(55, threading.Event())
            self.assertGreater(timeouts[0], 55, "the control: the record's wait keeps the client's own bound")
        finally:
            inbox_relay.api = saved

    def test_the_relay_mirror_takes_a_rotated_token_once_and_says_a_refusal_as_one(self):
        from gzcoord.inbox_parts import relay as inbox_relay
        seen = []

        def api(tok, path, url=None, method="GET", body=None, timeout=inbox_relay.API_TIMEOUT):
            seen.append(tok)
            if tok == "old":
                raise inbox_relay.RelayError("401", 401)
            return {"messages": []}
        saved_api, saved_tok = inbox_relay.api, relay_transport.synced_token
        inbox_relay.api, relay_transport.synced_token = api, lambda: "new"
        try:
            mirror = relay_transport.RelayMirror(relay_transport.RelayTransport("http://x", "c", "h/beta", "old"))
            self.assertEqual(mirror.receive(0, threading.Event()), [])
            self.assertEqual(seen, ["old", "new"], "refused once, retried once with the synced token")
            seen.clear()
            relay_transport.synced_token = lambda: "old"          # the control: nothing fresher to take
            mirror = relay_transport.RelayMirror(relay_transport.RelayTransport("http://x", "c", "h/beta", "old"))
            saved_err, sys.stderr = sys.stderr, types.SimpleNamespace(write=lambda s: said.append(s), flush=lambda: None)
            said: list[str] = []
            try:
                mirror.receive(0, threading.Event())
            finally:
                sys.stderr = saved_err
            self.assertEqual(seen, ["old"])
            self.assertTrue(any("refused the token" in x for x in said), said)
        finally:
            inbox_relay.api, relay_transport.synced_token = saved_api, saved_tok

    def test_the_factory_bounds_the_mirror_and_not_the_primary_relay(self):
        self.assertEqual(self.build("carrier-record").mirrors[0]._relay._call_timeout, relay_transport.MIRROR_CALL_S)
        self.assertIsNone(self.build("relay-record").primary._call_timeout)

    def test_replay_labels_a_row_by_the_journal_only_when_the_caller_says_the_page_is_the_journals(self):
        import io
        from contextlib import redirect_stdout
        from gzcoord.inbox_parts import records
        rec = {"id": "m", "seq": None, "sender": "x/y", "timestamp": "T", "content": C.msg(1), "carrier": "interweave",
               "sender_verified": True}
        out = {}
        for journal in (False, True):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = records.replay({"messages": [rec]}, "c", C.mid(1), {"address": C.ME, "slug": "x"}, None, True, journal)
            out[journal] = (code, json.loads(buf.getvalue()))
        self.assertEqual((out[False][1]["carrier"], out[False][1]["sender_verified"]), (records.RELAY_CARRIER, False),
                         "a relay page claiming to be verified is never believed")
        self.assertEqual((out[True][1]["carrier"], out[True][1]["sender_verified"]), ("interweave", True))

    # ── the factory, by mode ─────────────────────────────────────────
    def build(self, mode_name, **kw):
        d = P.scratch("mode-factory-")
        mode.write(mode_name, "h1/op", d)
        cfg = {"relay_url": "http://127.0.0.1:9", "channel": "c"}
        return transport.open_transport(kw.pop("cfg", cfg), token="t", me=ME, state_dir=d, iso_now=lambda: "2026-11-14T00:00:00Z",
                                        **kw)

    def test_each_mode_builds_its_own_transports(self):
        names = lambda tp: (tp.primary.name, [m.name for m in tp.mirrors], tp.mode)   # noqa: E731
        self.assertEqual(names(self.build("relay-record")), ("relay", ["interweave"], "relay-record"))
        self.assertEqual(names(self.build("carrier-record")), ("interweave", ["relay"], "carrier-record"))
        self.assertIsInstance(self.build("carrier-record").primary, transport.CarrierPrimary)
        self.assertEqual(names(self.build("carrier-only", cfg=None)), ("interweave", [], "carrier-only"))

    def test_journal_off_send_follows_the_modes_primary_with_no_mirror(self):
        got = {m: (lambda tp: (tp.primary.name, tp.mirrors))(self.build(m, journal_off=True, for_send=True, cfg=None if m == "carrier-only" else None) if False else self.build(m, journal_off=True, for_send=True))
               for m in ("relay-record", "carrier-record", "carrier-only")}
        self.assertEqual(got, {"relay-record": ("relay", []), "carrier-record": ("interweave", []), "carrier-only": ("interweave", [])})

    def test_journal_off_send_in_carrier_record_needs_no_relay_configuration(self):
        self.assertEqual(self.build("carrier-record", journal_off=True, for_send=True, cfg=None).primary.name, "interweave")

    def test_journal_off_receive_is_refused_in_the_carrier_modes_not_in_relay_record(self):
        for m in ("carrier-record", "carrier-only"):
            with self.assertRaisesRegex(transport.ModeError, "no receiving with GZCOORD_JOURNAL=off"):
                self.build(m, journal_off=True)
        self.assertEqual(self.build("relay-record", journal_off=True).primary.name, "relay")   # the positive control

    def test_a_read_of_the_record_builds_the_primary_alone(self):
        for m, primary in (("relay-record", "relay"), ("carrier-record", "interweave"), ("carrier-only", "interweave")):
            tp = self.build(m, record_only=True, journal_off=True)
            self.assertEqual((tp.primary.name, tp.mirrors), (primary, []), m)

    def test_a_relay_mode_without_a_configured_relay_is_refused_in_a_line(self):
        with self.assertRaises(transport.ModeError):
            self.build("carrier-record", cfg=None)

    # ── dedup order ──────────────────────────────────────────────────
    def test_the_carrier_first_order_marks_the_relays_copy_quiet(self):
        class Lock:
            def __init__(self):
                self.shown: set = set()
                self.lines: list = []

            def decide(self, mid, via, verdict, h):
                first = (mid, h) not in self.shown
                self.shown.add((mid, h))
                return types.SimpleNamespace(show=first, may_repeat=False, flagged=False, append_pending=first)

            def pending(self, mid, via, flagged, h):
                self.lines.append((mid, via))

            def finish_repeat(self, *a):
                pass

        text = C.msg(1)
        for first, quiet_one in ((True, "relay"), (False, "interweave")):
            relay_c = {"rec": {"content": text, "id": "r1"}, "msg": dedup.gzmsg.parse(text), "isMine": True}
            classified = [relay_c]
            lock = Lock()
            dedup.admit(lock, classified, [relay_c], [C.urec(1)], carrier_first=first)
            self.assertEqual(bool(relay_c.get("quiet")), quiet_one == "relay", first)
            self.assertEqual(len(lock.lines), 1)
            self.assertEqual(lock.lines[0][1], "interweave" if first else "relay")


if __name__ == "__main__":
    unittest.main()
