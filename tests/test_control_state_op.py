#!/usr/bin/env python3
"""The `state` op and the readers that ask it (agent-fabric ADR-029 rule 16; cutover plan §2.5 row 2): an agentd keeps its
newest state record in its own state directory and answers it, and under control_carrier "interweave" fabric-ctl's states,
the pool's claim reconciliation and read_waits read the accounts through the op, never the relay, which these cases make
refuse every connection. relay and dual keep reading the relay's history: their cases are the suites that existed before
(test_control_ctl, test_control_pool, test_control_queue), run unchanged; the cases here that touch them pin only that the
op is not asked there."""
from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402

own_instance_tree()
from control import agentd, ctl, js, ops, pool, queue, state_read, state_record  # noqa: E402

ME, A, B, C = "h/me", "h/a", "h/b", "h/c"
NOW_MS = 1_800_000_000_000.0
CFG = {"channel": "c", "state_channel": "c:state", "relay_url": "http://127.0.0.1:1", "control_carrier": "interweave"}


def iso(ms: float) -> str:
    return js.iso_from_ms(ms) if hasattr(js, "iso_from_ms") else __import__("datetime").datetime.fromtimestamp(
        ms / 1000, __import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def record(address: str, *, ago_ms: float = 1000, sessions=None, **more) -> dict:
    return {"v": 1, "kind": "state", "from": address, "ts": iso(NOW_MS - ago_ms), "sessions": [] if sessions is None else sessions, **more}


def reply_of(address: str, rec, *, claimed: str | None = None, why: str | None = None, ok: bool = True) -> dict:
    inner = {"address": claimed or address, "state": rec, **({"why": why} if why else {})}
    return {"v": 1, "kind": "reply", "id": "r", "in_reply_to": "q", "from": address, "op": "state", "ts": iso(NOW_MS), "ok": ok,
            "data": {"state": inner}}


class FakeLeg:
    def __init__(self, replies, lost=False, failed=None):
        self.todo, self.lost, self.closed, self.failed_sends = list(replies), lost, False, dict(failed or {})

    def replies(self, _t):
        out, self.todo = self.todo, []
        return out

    def close(self):
        self.closed = True


class Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="state-op-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.file = os.path.join(self.dir, state_record.RECORD_FILE)
        self.clock = [0.0]

    def ask(self, answers: dict, addresses=None, lost=False, boom=None, failed=None, **kw):
        """state_read.ask over a fake leg that answers {sender: reply}; the legs opened are kept in self.legs."""
        self.legs, self.sent = [], []

        def open_leg(request, to, wait_s):
            self.sent.append((request, to))
            if boom:
                raise boom
            leg = FakeLeg([(s, r) for s, r in answers.items()], lost=lost, failed=failed)
            self.legs.append(leg)
            return leg

        def now():
            self.clock[0] += 1.0
            return self.clock[0]
        return state_read.ask(addresses or list(answers), me=ME, own_file=self.file, new_id=lambda: "q", open_leg=open_leg, wait_s=3, now=now, **kw)


class Record(Tmp):
    def test_store_is_atomic_private_and_replaces(self):
        state_record.store(self.file, record(ME))
        state_record.store(self.file, record(ME, ago_ms=5))
        self.assertEqual(state_record.load(self.file)["ts"], iso(NOW_MS - 5))
        self.assertEqual(stat.S_IMODE(os.stat(self.file).st_mode), 0o600)
        self.assertEqual(os.listdir(self.dir), [state_record.RECORD_FILE])   # no temporary left

    def test_a_failed_store_keeps_the_old_record_and_leaves_no_temporary(self):
        state_record.store(self.file, record(ME))
        with self.assertRaises(TypeError):
            state_record.store(self.file, {"v": object()})
        self.assertEqual(state_record.load(self.file)["from"], ME)
        self.assertEqual(os.listdir(self.dir), [state_record.RECORD_FILE])

    def test_absent_and_broken_are_apart(self):
        self.assertIsNone(state_record.load(self.file))
        for text in ("{", "[]", "\xff"):
            with open(self.file, "wb") as fh:
                fh.write(text.encode("latin-1"))
            with self.assertRaises(state_record.StateRecordError):
                state_record.load(self.file)

    def test_the_op_answers_the_record_its_address_or_none_with_a_reason(self):
        self.assertEqual(state_record.state({}, me=ME, file=self.file)["state"], None)
        self.assertIn("no state record", state_record.state({}, me=ME, file=self.file)["why"])
        state_record.store(self.file, record(ME))
        said = state_record.state({}, me=ME, file=self.file)
        self.assertEqual((said["address"], said["state"]), (ME, record(ME)))
        with open(self.file, "w") as fh:
            fh.write("{")
        broken = state_record.state({}, me=ME, file=self.file)
        self.assertIsNone(broken["state"])
        self.assertIn("not JSON", broken["why"])

    def test_the_op_is_public_and_known(self):
        self.assertIn("state", ops.OPS)
        self.assertIn("state", ops.PUBLIC_OPS)
        self.assertNotIn("state", agentd.ACTION_OPS if hasattr(agentd, "ACTION_OPS") else [])


class Poster(Tmp):
    def posted(self, carrier):
        calls = []
        post = agentd.state_poster(lambda *a, **k: calls.append((a, k)), {"control_carrier": carrier, "state_channel": "s"}, ME, self.file)
        post(record(ME))
        return calls

    def test_relay_and_dual_keep_the_file_and_post(self):
        for carrier in ("relay", "dual"):
            with self.subTest(carrier):
                os.path.exists(self.file) and os.unlink(self.file)
                self.assertEqual(len(self.posted(carrier)), 1)
                self.assertEqual(state_record.load(self.file), record(ME))

    def test_interweave_keeps_the_file_and_posts_nothing(self):
        self.assertEqual(self.posted("interweave"), [])
        self.assertEqual(state_record.load(self.file), record(ME))

    def test_a_file_that_cannot_be_kept_still_posts_to_the_relay_but_not_with_the_second_carrier_alone(self):
        self.file = os.path.join(self.dir, "no-such-dir", "state-record.json")
        for carrier in ("relay", "dual"):
            with self.subTest(carrier):
                self.assertEqual(len(self.posted(carrier)), 1)
        with self.assertRaises(OSError):
            self.posted("interweave")

    def test_the_file_is_kept_before_a_post_that_fails(self):
        def refuse(*_a, **_k):
            raise ConnectionRefusedError("refused")
        with self.assertRaises(ConnectionRefusedError):
            agentd.state_poster(refuse, {"control_carrier": "relay", "state_channel": "s"}, ME, self.file)(record(ME))
        self.assertEqual(state_record.load(self.file), record(ME))

    def test_agentd_answers_the_op_from_the_file(self):
        os.environ["AGENT_FABRIC_STATE_DIR"] = self.dir
        self.file = os.path.join(agentd.state_dir(), state_record.RECORD_FILE)
        os.makedirs(os.path.dirname(self.file), exist_ok=True)
        self.addCleanup(os.environ.pop, "AGENT_FABRIC_STATE_DIR", None)
        state_record.store(self.file, record(ME))
        reply = agentd.answer({"op": "state", "id": "q"}, {"me": {"address": ME}, "started": "2026-01-01T00:00:00.000Z"})
        self.assertEqual(reply["data"]["state"], {"address": ME, "state": record(ME)})


class Ask(Tmp):
    def test_each_account_answers_its_record(self):
        got = self.ask({A: reply_of(A, record(A)), B: reply_of(B, record(B))})
        self.assertEqual(got, {A: {"record": record(A)}, B: {"record": record(B)}})
        self.assertTrue(all(leg.closed for leg in self.legs))
        self.assertEqual(self.sent[0][0]["op"], "state")

    def test_silent_account_is_unknown_never_empty(self):
        got = self.ask({A: reply_of(A, record(A))}, addresses=[A, B])
        self.assertIn("did not answer", got[B]["error"])
        self.assertNotIn("record", got[B])

    def test_a_lost_connection_is_said(self):
        got = self.ask({}, addresses=[A], lost=True)
        self.assertIn("closed", got[A]["error"])

    def test_no_record_yet_and_unreadable_are_unknown_with_the_reason(self):
        got = self.ask({A: reply_of(A, None, why="no state record has been written yet")})
        self.assertIn("no state record has been written yet", got[A]["error"])

    def test_a_peers_reason_reaches_a_terminal_without_its_control_characters(self):
        got = self.ask({A: reply_of(A, None, why="\x1b]0;pwned\x07\x1b[2J" + "x" * 500)})
        why = got[A]["error"]
        self.assertFalse(any(ord(c) < 32 or 127 <= ord(c) < 160 for c in why), repr(why))
        self.assertIn("pwned", why)   # the positive control: the text is kept, only its controls are not
        self.assertLess(len(why), 300)

    def test_answers_that_are_not_the_asked_accounts_are_unknown(self):
        cases = {
            "sender is not the one in the record": {A: reply_of(B, record(B))},
            "data names another address": {A: reply_of(A, record(A), claimed=B)},
            "record is from another address": {A: reply_of(A, record(B))},
            "record is not v1": {A: reply_of(A, {**record(A), "v": 2})},
            "record is not a state record": {A: reply_of(A, {**record(A), "kind": "up"})},
            "no ts": {A: reply_of(A, {k: v for k, v in record(A).items() if k != "ts"})},
            "refused": {A: reply_of(A, record(A), ok=False)},
            "the reply's own from is another's": {A: {**reply_of(A, record(A)), "from": B}},
        }
        for name, answers in cases.items():
            with self.subTest(name):
                got = self.ask(answers, addresses=[A])
                self.assertIn("error", got[A], name)
                self.assertNotIn("record", got[A])

    def test_the_own_address_is_read_from_the_file_and_asks_nobody(self):
        state_record.store(self.file, record(ME))
        got = self.ask({}, addresses=[ME])
        self.assertEqual(got, {ME: {"record": record(ME)}})
        self.assertEqual(self.sent, [])
        os.unlink(self.file)
        self.assertIn("no state record", self.ask({}, addresses=[ME])[ME]["error"])

    def test_the_own_record_is_held_to_the_same_shape_as_a_peers(self):
        for bad in ({"v": 1}, {**record(ME), "kind": "up"}, {**record(ME), "from": A}, {**record(ME), "v": 2}):
            with self.subTest(bad):
                state_record.store(self.file, bad)
                got = self.ask({}, addresses=[ME])
                self.assertIn("error", got[ME])
                self.assertNotIn("record", got[ME])

    def test_an_account_the_request_never_reached_is_said_and_not_waited_for(self):
        got = self.ask({A: reply_of(A, record(A))}, addresses=[A, B], failed={B: "no roster row"})
        self.assertEqual(got[B], {"error": "h/b was not asked: no roster row"})
        self.assertIn("record", got[A])
        self.assertLessEqual(self.clock[0], 3, "the window was not run out for an account that was never asked")

    def test_a_leg_that_cannot_be_opened_is_every_asked_account_unknown(self):
        got = self.ask({}, addresses=[A, B], boom=RuntimeError("no socket"))
        self.assertTrue(all("no socket" in v["error"] for v in got.values()))

    def test_use_op(self):
        said = []
        self.assertTrue(state_read.use_op({"control_carrier": "interweave"}, {}, said.append))
        self.assertEqual(said, [])
        for carrier in ("relay", "dual"):
            self.assertFalse(state_read.use_op({"control_carrier": carrier}, {}, said.append))
        self.assertTrue(state_read.use_op({"control_carrier": "dual"}, {"FABRIC_STATE_READ": "op"}, said.append))
        self.assertEqual(len(said), 1)
        with self.assertRaises(RuntimeError):
            state_read.use_op({"control_carrier": "dual"}, {"FABRIC_STATE_READ": "off"}, said.append)

    def test_the_environment_names_the_carrier_and_the_asker_reads_the_op_with_the_relay_refusing(self):
        old = os.environ.get("FABRIC_CONTROL_CARRIER")
        os.environ["FABRIC_CONTROL_CARRIER"] = "interweave"
        self.addCleanup(lambda: os.environ.__setitem__("FABRIC_CONTROL_CARRIER", old) if old is not None else os.environ.pop("FABRIC_CONTROL_CARRIER"))
        cfg = {**agentd.control_config(), "relay_url": "http://127.0.0.1:1"}
        self.assertEqual(cfg["control_carrier"], "interweave")
        legs = []
        asker = state_read.asker(cfg, me=ME, own_file=self.file, new_id=lambda: "q", say=lambda m: None,
                                 open_leg=lambda r, to, w: legs.append(FakeLeg([(A, reply_of(A, record(A, role="python-dev")))])) or legs[-1])
        role_of = pool.role_from_stream(call=refuse, cfg=cfg, now=lambda: NOW_MS, ask=asker)
        self.assertEqual(role_of(A), {"role": "python-dev"})
        self.assertEqual(len(legs), 1)
        os.environ["FABRIC_CONTROL_CARRIER"] = "relay"
        self.assertIsNone(state_read.asker(agentd.control_config(), me=ME, own_file=self.file, new_id=lambda: "q"))

    def test_interweave_is_a_carrier(self):
        self.assertIn("interweave", agentd.CARRIERS)


def refuse(*_a, **_k):
    raise ConnectionRefusedError("the relay refuses every connection")


class Pool(Tmp):
    def reader(self, answers, ago=1000):
        asked = []

        def ask(addresses):
            asked.append(addresses)
            return answers
        return pool.state_reader(call=refuse, cfg=CFG, now=lambda: NOW_MS, ask=ask), asked

    def test_fresh_record_is_read_without_the_relay(self):
        state_of, asked = self.reader({A: {"record": record(A, claims=[])}})
        self.assertEqual(state_of(A), {"record": record(A, claims=[])})
        self.assertEqual(asked, [[A]])

    def test_stale_and_silent_are_unknown(self):
        state_of, _ = self.reader({A: {"record": record(A, ago_ms=pool.STATES_STALE_MS + 1)}})
        self.assertIn("binding is unknown", state_of(A)["error"])
        state_of, _ = self.reader({A: {"error": "h/a did not answer within 3 s"}})
        self.assertEqual(state_of(A), {"error": "h/a did not answer within 3 s"})

    def test_the_role_comes_from_the_op(self):
        role_of = pool.role_from_stream(call=refuse, cfg=CFG, now=lambda: NOW_MS, ask=lambda a: {A: {"record": record(A, role="python-dev")}})
        self.assertEqual(role_of(A), {"role": "python-dev"})
        role_of = pool.role_from_stream(call=refuse, cfg=CFG, now=lambda: NOW_MS, ask=lambda a: {A: {"error": "silent"}})
        self.assertEqual(role_of(A), {"error": "silent"})

    def test_without_ask_the_relay_is_read_as_before(self):
        state_of = pool.state_reader(call=refuse, cfg=CFG, now=lambda: NOW_MS)
        self.assertIn("could not be read", state_of(A)["error"])


class Waits(Tmp):
    MID = "01a1e82e-608d-7764-bd68-b40fedd51841"

    def test_waits_come_from_the_op_and_a_silent_account_is_unknown(self):
        answers = {A: {"record": record(A, waits_on=[self.MID])}, B: {"record": record(B)}, C: {"error": "h/c did not answer"}}
        got = queue.read_waits(call=refuse, cfg=CFG, placed={A, B, C}, ask=lambda addrs: {a: answers[a] for a in addrs})
        self.assertEqual(got["waits"], {self.MID: [A]})
        self.assertEqual(got["accounts"], 2)
        self.assertEqual(got["unknown"], {C: "h/c did not answer"})

    def test_a_valid_record_with_a_waits_on_that_is_no_list_is_unknown_not_a_wait_on_nothing(self):
        bad = {**record(A), "waits_on": "not a list"}
        got = queue.read_waits(call=refuse, cfg=CFG, placed={A, B}, ask=lambda addrs: {A: {"record": bad}, B: {"record": record(B)}})
        self.assertEqual(got["accounts"], 1)   # the positive control: B's record counts
        self.assertIn(A, got["unknown"])
        self.assertNotIn(B, got["unknown"])

    def test_without_ask_the_answer_has_no_unknown_key(self):
        page = {"messages": [{"content": js.stringify(record(A))}]}
        got = queue.read_waits(call=lambda *_a, **_k: page, cfg=CFG, placed={A})
        self.assertNotIn("unknown", got)

    def test_the_cli_reads_no_relay_under_interweave(self):
        out, err = [], []

        class FakeAgentd:
            control_config = staticmethod(lambda: CFG)
            new_id = staticmethod(lambda: "q")
            state_dir = staticmethod(lambda: self.dir)

        reg = os.path.join(self.dir, "registry.json")
        with open(reg, "w") as fh:
            json.dump({"placement": {"a": "h"}}, fh)
        state_record.store(self.file, record("h/a", waits_on=[self.MID]))
        orig = state_read.ask
        state_read.ask = lambda addrs, **kw: orig(addrs, **{**kw, "open_leg": lambda *a: FakeLeg([])})
        self.addCleanup(setattr, state_read, "ask", orig)
        rc = queue.cli(["waits"], out=out.append, err=err.append, agentd=FakeAgentd, who={"host": "h", "agent": "a"}, call=refuse, registry=reg)
        self.assertEqual(rc, 0, (out, err))
        self.assertEqual(json.loads(out[0])["waits"], {self.MID: ["h/a"]})


class Override(Tmp):
    def test_a_misspelt_override_is_a_line_and_an_exit_code_never_a_traceback(self):
        old = os.environ.get("FABRIC_STATE_READ")
        os.environ["FABRIC_STATE_READ"] = "Op"
        self.addCleanup(lambda: os.environ.__setitem__("FABRIC_STATE_READ", old) if old is not None else os.environ.pop("FABRIC_STATE_READ"))
        out = []
        agentd_stub = __import__("types").SimpleNamespace(control_config=lambda: {**CFG, "control_carrier": "relay"}, new_id=lambda: "q", state_dir=lambda: self.dir)
        rc = queue.cli(["waits"], out=out.append, err=lambda m: None, agentd=agentd_stub, who={"agent": "me", "host": "h", "role": None, "project": None})
        self.assertEqual(rc, 3)
        self.assertIn("FABRIC_STATE_READ", json.loads(out[0])["error"])
        reg = os.path.join(self.dir, "registry.json")
        with open(reg, "w") as fh:
            json.dump({"hosts": {"h": {"operator": "op"}}, "placement": {"a": "h", "op": "h"}}, fh)
        err = []
        rc = ctl.main(["a", "states"], registry=reg, call=refuse, who={"host": "h", "agent": "op"}, token=None, out=lambda m: None, err=err.append)
        self.assertEqual(rc, 2)
        self.assertTrue(any("FABRIC_STATE_READ" in e for e in err), err)


class Beside(unittest.TestCase):
    def test_pool_claim_is_answered_off_the_thread_its_claimant_replies_arrive_on(self):
        self.assertTrue(agentd.beside_loop("pool-claim", True))
        self.assertFalse(agentd.beside_loop("pool-claim", False))   # the relay and dual paths keep it inline
        self.assertTrue(agentd.beside_loop("disk", False))          # positive control: the ones always beside the loop are
        self.assertFalse(agentd.beside_loop("presence", True))

    def test_a_misspelt_override_in_the_daemon_is_said_and_the_carrier_alone_decides(self):
        said = []
        orig = agentd._stderr
        agentd._stderr = said.append
        self.addCleanup(setattr, agentd, "_stderr", orig)
        for carrier, asks in (("interweave", True), ("relay", False), ("dual", False)):
            with self.subTest(carrier):
                got = agentd.state_asker_of({"control_carrier": carrier}, me=ME, own_file="f", new_id=lambda: "q", env={"FABRIC_STATE_READ": "Op"})
                self.assertEqual(got is not None, asks)
        self.assertEqual(len(said), 3)
        self.assertIn("override is ignored", said[0])

    def test_the_daemon_reads_the_misspelt_override_from_its_own_environment_and_is_not_stopped_by_it(self):
        # main calls state_asker_of without env, so both the first read and the retry see os.environ: the retry must not.
        said = []
        orig = agentd._stderr
        agentd._stderr = said.append
        self.addCleanup(setattr, agentd, "_stderr", orig)
        old = os.environ.get("FABRIC_STATE_READ")
        os.environ["FABRIC_STATE_READ"] = "Op"
        self.addCleanup(lambda: os.environ.__setitem__("FABRIC_STATE_READ", old) if old is not None else os.environ.pop("FABRIC_STATE_READ"))
        got = agentd.state_asker_of({"control_carrier": "interweave"}, me=ME, own_file="f", new_id=lambda: "q")
        self.assertIsNotNone(got)
        self.assertIsNone(agentd.state_asker_of({"control_carrier": "relay"}, me=ME, own_file="f", new_id=lambda: "q"))
        self.assertEqual(len(said), 2)


class Table(Tmp):
    @staticmethod
    def live(address, **more):   # fresh against the clock ctl.state_row reads, which a fixed timestamp stops being
        return {**record(address, **more), "ts": iso(__import__("time").time() * 1000)}

    def test_the_state_verb_prints_a_row_per_account_and_unknown_with_a_reason(self):
        good = {"status": "ok", "host": "h", "account": "a", "state": {"address": A, "state": self.live(A, role="python-dev")}}
        none = {"status": "ok", "host": "h", "account": "b", "state": {"address": B, "state": None, "why": "no state record has been written yet"}}
        lines = ctl._table_state([good, none])
        self.assertIn("a", lines[1])
        self.assertTrue(lines[2].startswith("b") and "unknown" in lines[2] and "no state record has been written yet" in lines[2])
        self.assertIn("state", ctl.VERB)

    def test_an_answer_that_is_not_the_asked_accounts_state_record_is_unknown_and_never_stops_the_table(self):
        def row(account, address, rec):
            return {"status": "ok", "host": "h", "account": account, "state": {"address": address, "state": rec}}
        cases = {
            "another account's record": row("b", B, self.live(A)),
            "another account's address": row("b", A, self.live(B)),
            "not a state record": row("b", B, {**self.live(B), "kind": "up"}),
            "not v1": row("b", B, {**self.live(B), "v": 7}),
            "no ts": row("b", B, {"sessions": []}),
        }
        for name, bad in cases.items():
            with self.subTest(name):
                lines = ctl._table_state([row("a", A, self.live(A, role="python-dev")), bad])
                self.assertEqual(len(lines), 3)
                self.assertTrue(lines[2].startswith("b") and "unknown" in lines[2] and "working" not in lines[2], lines[2])
        self.assertNotIn("unknown", ctl._table_state([row("b", B, self.live(B, role="python-dev"))])[1])   # the positive control

    def test_a_peers_reason_in_the_table_has_no_control_characters(self):
        none = {"status": "ok", "host": "h", "account": "b", "state": {"address": B, "state": None, "why": "\x1b[2Jboom"}}
        line = ctl._table_state([none])[1]
        self.assertIn("boom", line)
        self.assertNotIn("\x1b", line)


class Main(Tmp):
    """fabric-ctl's own entry, the carrier named by the environment, the relay refusing every call and holding no token."""

    def test_states_through_main_asks_the_op_and_never_the_relay(self):
        reg = os.path.join(self.dir, "registry.json")
        with open(reg, "w") as fh:
            json.dump({"hosts": {"h": {"operator": "op"}}, "placement": {"a": "h", "b": "h", "op": "h"}}, fh)
        old = os.environ.get("FABRIC_CONTROL_CARRIER")
        os.environ["FABRIC_CONTROL_CARRIER"] = "interweave"
        self.addCleanup(lambda: os.environ.__setitem__("FABRIC_CONTROL_CARRIER", old) if old is not None else os.environ.pop("FABRIC_CONTROL_CARRIER"))
        orig = state_read.ask
        self.addCleanup(setattr, state_read, "ask", orig)
        real_ms = __import__("time").time() * 1000   # the record is fresh against the clock main reads, not the fixed one
        fresh = {**record("h/a"), "ts": iso(real_ms)}
        state_read.ask = lambda addrs, **kw: orig(addrs, **{**kw, "wait_s": 0.2, "open_leg": lambda r, to, w: FakeLeg([("h/a", reply_of("h/a", fresh))])})
        out, err = [], []
        rc = ctl.main(["a", "b", "states", "--json"], registry=reg, call=refuse, who={"host": "h", "agent": "op"}, token=None,
                      out=out.append, err=err.append, sleep=lambda _s: None, now=lambda: __import__("time").time())
        rows = {json.loads(x)["address"]: json.loads(x) for x in out}
        self.assertEqual(rc, 1, (out, err))
        self.assertEqual(rows["h/a"]["state"], "none")
        self.assertNotIn("why", rows["h/a"])
        self.assertEqual(rows["h/b"]["state"], "unknown")
        self.assertIn("did not answer", rows["h/b"]["why"])
        self.assertFalse([e for e in err if "relay" in e or "TOKEN" in e], err)


class States(Tmp):
    def run_states(self, answers, follow=False, scripted=None, json_out=True):
        out, err, sleeps = [], [], []
        calls = []

        def ask(addresses):
            calls.append(list(addresses))
            return (scripted.pop(0) if scripted else answers)

        def sleep(s):
            sleeps.append(s)
        rc = ctl.states({"json": json_out, "follow": follow}, [{"address": a} for a in (A, B)], call=refuse, cfg=CFG, out=out.append,
                        err=err.append, now=lambda: NOW_MS, sleep=sleep, forever=False, ask=ask)
        return rc, [json.loads(x) if json_out else x for x in out], err, sleeps, calls

    def test_rows_come_from_the_op_and_a_silent_account_is_unknown(self):
        good = record(A, sessions=[{"session": "s1", "state": "working", "since": iso(NOW_MS - 5000)}])
        rc, rows, err, _, calls = self.run_states({A: {"record": good}, B: {"error": "h/b did not answer within 3 s"}})
        self.assertEqual(rc, 1)
        self.assertEqual(err, [])
        by = {r["address"]: r for r in rows}
        self.assertEqual(by[A]["state"], "working")
        self.assertEqual((by[B]["state"], by[B]["sessions"]), ("unknown", []))
        self.assertEqual(by[B]["why"], "h/b did not answer within 3 s")
        self.assertEqual(calls, [[A, B]])

    def test_a_reason_with_control_characters_is_printed_without_them(self):
        _, rows, *_ = self.run_states({A: {"error": "h/a said \x1b[2J\x07 boom"}, B: {"record": record(B)}}, json_out=False)
        text = "".join(rows)
        self.assertIn("boom", text)
        self.assertFalse(any(c in text for c in "\x1b\x07"), repr(text))

    def test_all_answering_exits_0(self):
        rc, rows, *_ = self.run_states({A: {"record": record(A)}, B: {"record": record(B)}})
        self.assertEqual((rc, [r["state"] for r in rows]), (0, ["none", "none"]))

    def test_a_forged_shape_is_unknown(self):
        bad = {**record(A), "sessions": "nope"}
        rc, rows, *_ = self.run_states({A: {"record": bad}, B: {"record": record(B)}})
        self.assertEqual((rc, rows[0]["state"]), (1, "unknown"))

    def test_a_stale_record_is_unknown_on_its_own_time(self):
        old = record(A, ago_ms=ctl.STATES_STALE_MS + 1, sessions=[{"session": "s1", "state": "working", "since": iso(NOW_MS)}])
        _, rows, *_ = self.run_states({A: {"record": old}, B: {"record": record(B)}})
        self.assertEqual(rows[0]["state"], "unknown")

    def test_follow_asks_again_every_5_s_and_prints_only_a_change(self):
        first = {A: {"record": record(A)}, B: {"record": record(B)}}
        second = {A: {"record": record(A)}, B: {"error": "h/b did not answer"}}
        _, rows, _, sleeps, calls = self.run_states(None, follow=True, scripted=[first, second])
        self.assertEqual(sleeps, [5])
        self.assertEqual(len(calls), 2)
        self.assertEqual([r["address"] for r in rows], [A, B, B])   # A unchanged, B now unknown
        self.assertEqual(rows[-1]["state"], "unknown")

    def test_an_account_that_stops_answering_is_not_shown_by_its_last_record(self):
        first = {A: {"record": record(A, sessions=[{"session": "s1", "state": "working", "since": iso(NOW_MS)}])}, B: {"record": record(B)}}
        second = {A: {"error": "silent"}, B: {"record": record(B)}}
        _, rows, *_ = self.run_states(None, follow=True, scripted=[first, second])
        self.assertEqual([r["state"] for r in rows if r["address"] == A], ["working", "unknown"])


if __name__ == "__main__":
    unittest.main()
