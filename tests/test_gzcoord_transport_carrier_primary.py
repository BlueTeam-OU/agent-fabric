#!/usr/bin/env python3
"""The carrier as the transport of record: `CarrierPrimary`, the adapter's `wait` op, and the watch over it (InterWeave-only
cutover plan rows W6 and W15: the carrier is the only transport).

Through the real bin/gzcoord-inbox in the protocol suite's scratch environment and a carrier stand-in on its adapter socket
(P.Carrier): an idle arm makes a bounded number of adapter calls; a carrier that is not running is waited out to the deadline
with its line, the fix told by who reads it, and no marker; --history is the journal's. Beside them the units: the carrier's
`wait` (returns at an arrival, at its bound, never spins on a record the ledger has not settled), a failing carrier raising where
a mirror stays silent, and the four outcomes of a send as a primary. Hermetic: scratch directories and sockets in this process."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import test_gzcoord_carrier_inbox as C  # noqa: E402 — its World: carrier stand-in, scratch account, message builders
import test_gzcoord_protocol as P  # noqa: E402
from gzcoord.carrier import adapter, engine  # noqa: E402
from gzcoord.transport import carrier as carrier_transport  # noqa: E402

ME = {"address": "h/beta", "slug": "dev"}


def tearDownModule():
    for d in P.SCRATCH:
        shutil.rmtree(d, ignore_errors=True)


class Watch(unittest.TestCase):
    def tearDown(self):
        for w in getattr(self, "worlds", []):
            w.close()

    def world(self, records=None, hold: float | None = 0.2):
        w = C.World(records, hold_s=hold)
        self.worlds = [*getattr(self, "worlds", []), w]
        return w

    def test_an_idle_arm_makes_a_bounded_number_of_adapter_calls(self):
        w = self.world(hold=None)          # the carrier holds a wait to its bound: nothing arrives
        r = w.watch(deadline=6)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("subject-", r.stdout)
        self.assertLessEqual(w.carrier.ops().count("wait"), 2, w.carrier.ops())
        self.assertEqual([c for c in w.carrier.ops() if c != "wait"], [], "no other op: the wait's answer is the page")

    def test_history_is_the_journals(self):
        w = self.world()
        r = subprocess.run([P.INBOX_CMD, "--history"], env=w.env, capture_output=True, text=True, timeout=120,
                           stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("in your journal's last", r.stdout)
        self.assertEqual(w.carrier.ops(), [], "the carrier keeps no past: nothing is asked of it")

    def test_replay_names_an_unreadable_journal_not_the_carrier(self):
        w = self.world()
        agent = os.path.join(w.state, "agents", P.LOGIN)
        os.makedirs(agent, exist_ok=True)
        with open(os.path.join(agent, "episodic.db"), "wb") as fh:
            fh.write(b"this is not a database " * 400)
        r = subprocess.run([P.INBOX_CMD, "--replay", C.mid(1)], env=w.env, capture_output=True, text=True, timeout=120,
                           stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("your journal could not be read", r.stderr)
        self.assertNotIn("carrier failed", r.stderr)

    def registry(self, operator: str | None) -> str:
        """A scratch hosts registry whose operator on this account's host is `operator` (None: a host with another login),
        so a case never reads whether the runner is an operator in the checkout's registry."""
        d = tempfile.mkdtemp(prefix="j261-reg-")
        self.addCleanup(shutil.rmtree, d, True)
        path = os.path.join(d, "registry.json")
        with open(path, "w") as fh:
            json.dump({"hosts": {P.ME["host"]: {"operator": operator or "someone-else"}}, "placement": {}}, fh)
        return path

    def login(self):
        return subprocess.run(["id", "-un"], capture_output=True, text=True, timeout=10).stdout.strip()

    def marker(self, w):
        return os.path.join(w.env["XDG_RUNTIME_DIR"], "agent-fabric", f"gzcoord-inbox-{self.login()}.relay-down")

    def test_a_carrier_that_is_not_running_is_waited_out_to_the_deadline_with_its_line_and_no_marker(self):
        for operator in (False, True):
            w = self.world([C.urec(5)])
            w.carrier.close()                                     # the socket is gone: no carrier
            w.env["AGENT_FABRIC_HOSTS_REGISTRY"] = self.registry(P.ME["agent"] if operator else None)
            r = w.watch(deadline=8)          # past the 3 s bound: j266, a carrier is retried to the deadline, never given up on
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("run the watch again", r.stdout, "the quiet ending, the one a session re-runs")
            if operator:
                self.assertIn(f"fabric-ctl {P.ME['agent']} interweave", r.stdout, "an operator is told the command that says why")
                self.assertNotIn("OBSERVATION", r.stdout)
            else:
                self.assertIn("OBSERVATION to fabric-coordinator", r.stdout, "anyone else is told what they can do")
                self.assertNotIn("fabric-ctl", r.stdout)
        self.assertIn("carrier", r.stdout)
        self.assertFalse(os.path.exists(self.marker(w)), "no give-up, so no Stop-hook marker")
        self.assertNotIn("subject-5", r.stdout, "a carrier that is down shows nothing")


class Send(unittest.TestCase):
    def test_a_send_the_carrier_took_is_journaled_as_the_carriers(self):
        import test_gzcoord_carrier_send as CS
        carrier = P.Carrier()
        self.addCleanup(carrier.close)
        base = P.scratch("send-primary-")
        state, store = os.path.join(base, "state"), P.id_store()
        r = P.send_with(carrier, P.VALID, AGENT_FABRIC_STATE_DIR=state, AGENT_FABRIC_SECRET_STORE=store)
        self.assertEqual(r.code, 0, r.err)
        self.assertEqual([x["message_id"] for x in carrier.posts], [P.VALID_ID])
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
        for operator, want, absent in ((None, "OBSERVATION", "fabric-ctl"), ("beta", "fabric-ctl beta interweave", "OBSERVATION")):
            d = tempfile.mkdtemp(prefix="j261-reg-")
            self.addCleanup(shutil.rmtree, d, True)
            reg = os.path.join(d, "registry.json")
            with open(reg, "w") as fh:
                json.dump({"hosts": {"h": {"operator": operator or "someone-else"}}, "placement": {}}, fh)
            with mock.patch.dict(os.environ, {"AGENT_FABRIC_HOSTS_REGISTRY": reg}):
                x = p.explain(cm.exception)
            self.assertEqual(x["code"], 0)
            self.assertIn(want, x["line"])
            self.assertNotIn(absent, x["line"])
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


if __name__ == "__main__":
    unittest.main()
