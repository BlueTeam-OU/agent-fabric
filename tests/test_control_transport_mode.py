#!/usr/bin/env python3
"""The account's GZCoord transport mode (InterWeave-only cutover plan D2, D10, row W5; agent-fabric ADR-029, ADR-067):
the state file and its reader (gzcoord/transport/mode.py), `open_transport` reading it, the signed `<carrier>-mode` action
(control/transport_mode.py), `fabric-ctl <login|all> <carrier>` showing it, and the refusal of carrier-only while a placed
account is not past relay-record. What a mode sends or reads is W6 to W8's and is not here. The running watch taking a change
is tests/test_gzcoord_transport_mode_watch.py. A scratch state directory per test, removed with it."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402

own_instance_tree()
from control import agentd, ctl, ops, sign  # noqa: E402
from control import transport_mode as tm  # noqa: E402
from gzcoord import transport  # noqa: E402
from gzcoord.carrier import CARRIER_NAME  # noqa: E402
from gzcoord.transport import mode  # noqa: E402

OPERATOR = "h1/op"
OP = f"{CARRIER_NAME}-mode"
ME = {"address": "h1/me"}
CFG = {"relay_url": "http://127.0.0.1:1", "channel": "c"}


class Scratch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="transport-mode-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.file = os.path.join(self.dir, mode.FILE)

    def write(self, text):
        with open(self.file, "w", encoding="utf-8") as fh:
            fh.write(text)


class State(Scratch):
    def test_no_file_is_relay_record_and_reading_creates_nothing(self):
        self.assertEqual(mode.read(self.dir), {"mode": "relay-record", "set_by": None, "set_at": None})
        self.assertEqual(os.listdir(self.dir), [])

    def test_a_written_mode_reads_back_with_who_and_when_and_leaves_no_temporary(self):
        mode.write("carrier-record", OPERATOR, self.dir)
        r = mode.read(self.dir)
        self.assertEqual((r["mode"], r["set_by"]), ("carrier-record", OPERATOR))
        self.assertRegex(r["set_at"], r"^\d{4}-\d\d-\d\dT")
        self.assertEqual(os.listdir(self.dir), [mode.FILE] if not os.path.exists(os.path.join(self.dir, ".lock")) else sorted([mode.FILE, ".lock"]))

    def test_every_mode_round_trips_and_an_unknown_one_is_not_written(self):
        for m in mode.MODES:
            mode.write(m, OPERATOR, self.dir)
            self.assertEqual(mode.read(self.dir)["mode"], m)
        with self.assertRaises(ValueError):
            mode.write("carrier-both", OPERATOR, self.dir)
        self.assertEqual(mode.read(self.dir)["mode"], mode.MODES[-1], "the refused write left the file as it was")

    def test_a_file_that_is_not_a_mode_is_an_error_never_the_default(self):
        for text in ("", "{", "[]", "null", '{"mode": "relay"}', '{"mode": null}', '{}', '{"mode": ["relay-record"]}'):
            self.write(text)
            with self.assertRaisesRegex(mode.ModeError, r"transport-mode\.json"):
                mode.read(self.dir)
        self.write('{"mode": "relay-record"}')      # the positive control: the same reader accepts a good one
        self.assertEqual(mode.read(self.dir)["mode"], "relay-record")

    def test_a_directory_in_the_files_place_is_an_error(self):
        os.mkdir(self.file)
        with self.assertRaises(mode.ModeError):
            mode.read(self.dir)


class Watching(Scratch):
    def watcher(self, every=5.0):
        self.now = 0.0
        return mode.Watcher("relay-record", self.dir, every=every, clock=lambda: self.now)

    def test_a_change_is_seen_once_and_not_before_the_poll_interval(self):
        w = self.watcher()
        mode.write("carrier-record", OPERATOR, self.dir)
        self.now = 4.9
        self.assertFalse(w.changed(), "the file is read at most once per interval")
        self.now = 5.0
        self.assertTrue(w.changed())
        self.now = 10.0
        self.assertFalse(w.changed(), "the same mode is not a second change")
        mode.write("carrier-only", OPERATOR, self.dir)
        self.now = 15.0
        self.assertTrue(w.changed())

    def test_the_bound_a_default_watch_keeps_is_inside_the_minute(self):
        from gzcoord import inbox
        self.assertLessEqual(inbox.MODE_POLL_S, 30)

    def test_a_file_that_cannot_be_read_is_no_change_and_a_later_good_one_is(self):
        w = self.watcher()
        self.write("{")
        self.now = 5.0
        self.assertFalse(w.changed())
        self.write('{"mode": "carrier-record"}')
        self.now = 10.0
        self.assertTrue(w.changed())

    def test_removing_the_file_is_a_move_back_to_the_default(self):
        self.now = 0.0
        w = mode.Watcher("carrier-record", self.dir, every=1.0, clock=lambda: self.now)
        self.now = 1.0
        self.assertTrue(w.changed())
        self.assertEqual(w.current, "relay-record")


class OpenTransport(Scratch):
    def open(self, **kw):
        return transport.open_transport(CFG, token="tok", me=ME, state_dir=self.dir, iso_now=lambda: "2026-11-13T00:00:00Z", **kw)

    def shape(self, mux):
        return (type(mux.primary).__name__, mux.primary.relay_url, mux.primary.channel, [type(m).__name__ for m in mux.mirrors])

    def test_with_no_state_file_the_mux_is_todays(self):
        mux = self.open()
        self.assertEqual(mux.mode, "relay-record")
        self.assertEqual(self.shape(mux), ("RelayTransport", CFG["relay_url"], "c", ["CarrierTransport"]))
        self.assertEqual(self.shape(self.open(journal_off=True))[3], [], "the journal off still has no mirror")
        self.assertFalse(os.path.exists(self.file), "opening a transport writes no mode")

    def test_every_mode_is_carried_and_all_are_wired_to_the_current_transports_for_now(self):
        base = self.shape(self.open())
        for m in mode.MODES:
            mode.write(m, OPERATOR, self.dir)
            mux = self.open()
            self.assertEqual(mux.mode, m)
            self.assertEqual(self.shape(mux), base, m)

    def test_a_damaged_file_refuses_to_open_and_the_message_names_the_fix(self):
        self.write("not json")
        with self.assertRaisesRegex(transport.ModeError, rf"{CARRIER_NAME}-mode --mode"):
            self.open()
        with self.assertRaises(transport.ModeError):
            transport.open_transport(CFG, token="tok", me=ME, state_dir=self.dir, journal_off=True)


class Action(Scratch):
    def req(self, **args):
        return {"op": OP, "id": "r1", "from": OPERATOR, "args": args}

    def test_the_action_is_signed_and_the_agent_answers_it_and_it_is_not_public(self):
        self.assertIn(OP, sign.ACTION_OPS)
        self.assertIn(OP, ops.OPS)
        self.assertNotIn(OP, ops.PUBLIC_OPS)
        self.assertEqual(ctl.ACTION_OK[OP], ["set"])

    def test_set_writes_the_record_under_the_signers_address_and_says_what_it_replaced(self):
        a = tm.set_mode(self.req(mode="carrier-record"), state_dir=self.dir)
        self.assertEqual((a["status"], a["previous"], a["mode"]["mode"], a["mode"]["set_by"]), ("set", "relay-record", "carrier-record", OPERATOR))
        b = tm.set_mode({**self.req(mode="carrier-only"), "from": "h1/other"}, state_dir=self.dir)
        self.assertEqual((b["previous"], mode.read(self.dir)["set_by"]), ("carrier-record", "h1/other"))

    def test_set_refuses_what_is_not_a_mode_and_writes_nothing(self):
        for args in ({}, {"mode": "relay"}, {"mode": None}, {"mode": "carrier-record", "x": 1}, {"mode": ["carrier-record"]}):
            a = tm.set_mode(self.req(**args), state_dir=self.dir)
            self.assertEqual(a["status"], "refused", args)
        self.assertEqual(tm.set_mode({"op": OP, "from": OPERATOR, "args": "carrier-record"}, state_dir=self.dir)["status"], "refused")
        self.assertEqual(tm.set_mode({"op": OP, "args": {"mode": "carrier-record"}}, state_dir=self.dir)["status"], "refused", "who signed it is not said")
        self.assertFalse(os.path.exists(self.file))
        self.assertEqual(tm.set_mode(self.req(mode="carrier-record"), state_dir=self.dir)["status"], "set", "the positive control")

    def test_set_repairs_a_file_nobody_can_read_and_previous_is_unknown(self):
        self.write("{")
        a = tm.set_mode(self.req(mode="relay-record"), state_dir=self.dir)
        self.assertEqual((a["status"], a["previous"]), ("set", None))
        self.assertEqual(mode.read(self.dir)["mode"], "relay-record")

    def test_a_file_that_cannot_be_replaced_is_failed_not_set(self):
        os.mkdir(self.file)          # os.replace cannot put a file over a directory
        a = tm.set_mode(self.req(mode="carrier-record"), state_dir=self.dir)
        self.assertEqual(a["status"], "failed")
        self.assertIn(mode.FILE, a["reason"])

    def test_the_read_shows_the_mode_or_that_it_is_unreadable(self):
        self.assertEqual(tm.section(self.dir)["mode"], "relay-record")
        mode.write("carrier-only", OPERATOR, self.dir)
        self.assertEqual(tm.section(self.dir)["mode"], "carrier-only")
        self.write("{")
        s = tm.section(self.dir)
        self.assertIsNone(s["mode"])
        self.assertIn("transport-mode.json", s["error"])

    def test_the_interweave_read_carries_the_mode_beside_what_is_installed(self):
        import control.carrier_install as ci
        keep = ci.installed
        ci.installed = lambda **_: {"status": "ok"}
        self.addCleanup(setattr, ci, "installed", keep)
        mode.write("carrier-record", OPERATOR, self.dir)
        got = ops._carrier({"mode_state_dir": self.dir})
        self.assertEqual((got["status"], got["transport_mode"]["mode"]), ("ok", "carrier-record"))

    def test_the_daemon_dispatches_it_with_the_signers_address(self):
        ctx = {"me": {"address": "h1/a"}, "started": "2026-10-28T00:00:00.000Z", "home": self.dir, "root": HERE, "mode_opts": {"state_dir": self.dir}}
        r = agentd.answer({"op": OP, "id": "r", "from": OPERATOR, "args": {"mode": "carrier-record"}}, ctx)
        self.assertEqual(r["data"][OP]["status"], "set")
        self.assertEqual(mode.read(self.dir)["set_by"], OPERATOR)


class Ctl(Scratch):
    def test_parse_wants_a_known_mode_and_allows_all_and_no_other_verb_takes_one(self):
        a = ctl.parse_args(["all", OP, "--mode", "carrier-record"])
        self.assertEqual((a["op"], a["mode"], a["targets"]), (OP, "carrier-record", ["all"]))
        self.assertEqual(ctl.parse_args(["all", OP, "--mode=carrier-only"])["mode"], "carrier-only")
        for argv, why in ((["all", OP], "takes --mode"), (["all", OP, "--mode", "relay"], "one of"), (["all", "hold", "--reason", "r", "--mode", "carrier-record"], "goes with")):
            with self.assertRaisesRegex(ctl.CtlError, why, msg=argv):
                ctl.parse_args(argv)

    def test_the_request_carries_the_mode_and_nothing_else(self):
        cfg = {"ttl_s": 60}
        r = ctl.build_request(ctl.parse_args(["all", OP, "--mode", "carrier-record"]), id="i", from_=OPERATOR, to="*", cfg=cfg)
        self.assertEqual((r["op"], r["args"]), (OP, {"mode": "carrier-record"}))

    def test_the_read_table_prints_each_accounts_mode_and_unknown_as_unknown(self):
        def row(login, section):
            return {"kind": "reply", "from": f"h1/{login}", "op": CARRIER_NAME, "data": {CARRIER_NAME: {"status": "ok", "version": "1.2.3", **section}}}
        expected = [{"login": l, "host": "h1", "address": f"h1/{l}"} for l in "abcd"]
        replies = [row("a", {"transport_mode": {"mode": "relay-record"}}), row("b", {"transport_mode": {"mode": "carrier-only"}}),
                   row("c", {"transport_mode": {"mode": None, "error": "x"}}), row("d", {})]
        lines = {l.split()[0]: l for l in ctl.table(CARRIER_NAME, ctl.rows(expected, replies)).splitlines()[1:]}
        self.assertRegex(lines["a"], r"^a\s+ok\s+relay-record\s")
        self.assertRegex(lines["b"], r"^b\s+ok\s+carrier-only\s")
        self.assertRegex(lines["c"], r"^c\s+ok\s+unreadable\s")
        self.assertRegex(lines["d"], r"^d\s+ok\s+-\s", "an older agent that reports none")


class Fleet(Scratch):
    """Three placed accounts, each with a state directory of its own, answering the read and the action as their daemons do."""
    LOGINS = ("a", "b", "c")

    def setUp(self):
        super().setUp()
        self.reg = os.path.join(self.dir, "registry.json")
        with open(self.reg, "w", encoding="utf-8") as fh:
            json.dump({"hosts": {"h1": {"operator": "op"}}, "placement": {l: "h1" for l in self.LOGINS}}, fh)
        self.home = {l: os.path.join(self.dir, l) for l in self.LOGINS}
        for d in self.home.values():
            os.mkdir(d)
        self.silent: set[str] = set()
        self.sent: list[dict] = []
        self.states: dict = {}
        keep = (ctl.signing_key, ctl.sign_request)
        ctl.signing_key, ctl.sign_request = (lambda *a, **k: {"key": "k"}), (lambda r, k: r)
        self.addCleanup(lambda: setattr(ctl, "signing_key", keep[0]) or setattr(ctl, "sign_request", keep[1]))

    def put(self, login, m):
        if m is not None:
            mode.write(m, OPERATOR, self.home[login])

    def call(self, path, method="GET", body=None, **_kw):
        if path.startswith("/api/send"):
            req = json.loads(json.loads(body)["content"])
            self.sent.append(req)
            self.states.clear()
            for login in self.LOGINS:
                if login in self.silent:
                    continue
                if req["op"] == OP:
                    data = {OP: tm.set_mode({**req, "from": req["from"]}, state_dir=self.home[login])}
                else:
                    data = {CARRIER_NAME: {"status": "ok", "transport_mode": tm.section(self.home[login])}}
                self.states[login] = {"v": 1, "kind": "reply", "id": f"r-{login}", "in_reply_to": req["id"], "from": f"h1/{login}", "op": req["op"], "ok": True, "data": data}
            return {"id": "m1"}
        return {"messages": [{"id": f"x-{l}", "content": json.dumps(r)} for l, r in self.states.items()]}

    def run_ctl(self, argv):
        out, err = [], []
        rc = ctl.main([*argv, "--timeout", "5"], registry=self.reg, call=self.call, out=out.append, err=err.append, sleep=lambda s: None,
                      who={"host": "h1", "agent": "op", "project": None}, token="tok")
        return rc, "\n".join(out), "\n".join(err)

    def moves(self):
        return [r for r in self.sent if r["op"] == OP]

    def modes(self):
        return {l: mode.read(self.home[l])["mode"] for l in self.LOGINS}


class FleetRuns(Fleet):
    def test_the_read_prints_every_accounts_mode_with_no_state_file_as_relay_record(self):
        self.put("b", "carrier-record")
        rc, out, err = self.run_ctl(["all", CARRIER_NAME])
        lines = {l.split()[0]: l for l in out.splitlines()[1:] if l.strip()}
        self.assertRegex(lines["a"], r"relay-record")
        self.assertRegex(lines["b"], r"carrier-record")
        self.assertRegex(lines["c"], r"relay-record")
        self.assertEqual(self.moves(), [])

    def test_moving_all_to_carrier_record_then_the_read_shows_it_and_names_the_account_that_did_not_answer(self):
        self.silent = {"c"}
        rc, out, err = self.run_ctl(["all", OP, "--mode", "carrier-record"])
        self.assertEqual(rc, 1, "an account that did not confirm fails the run")
        self.assertEqual(self.moves()[-1]["args"], {"mode": "carrier-record"})
        self.assertRegex(out, r"(?m)^a\s+set\s+relay-record -> carrier-record")
        self.assertRegex(out, r"(?m)^c\s+no answer")
        self.assertEqual(self.modes(), {"a": "carrier-record", "b": "carrier-record", "c": "relay-record"})
        self.silent = set()
        rc, out, err = self.run_ctl(["all", CARRIER_NAME])
        self.assertEqual({l.split()[0]: l.split()[2] for l in out.splitlines()[1:] if l.strip()}, {"a": "carrier-record", "b": "carrier-record", "c": "relay-record"})

    def test_carrier_only_is_refused_while_any_placed_account_reports_relay_record_and_nothing_is_sent(self):
        self.put("a", "carrier-record")
        self.put("b", "carrier-record")      # c has no file: relay-record
        rc, out, err = self.run_ctl(["all", OP, "--mode", "carrier-only"])
        self.assertEqual(rc, 2)
        self.assertRegex(err, r"carrier-only is refused.*c \(relay-record\)")
        self.assertNotRegex(err, r"a \(|b \(")
        self.assertEqual(self.moves(), [], "a refused move is sent to nobody")
        self.assertEqual(self.modes(), {"a": "carrier-record", "b": "carrier-record", "c": "relay-record"})

    def test_the_refusal_looks_at_the_whole_fleet_not_only_the_accounts_addressed(self):
        self.put("a", "carrier-record")
        rc, out, err = self.run_ctl(["a", OP, "--mode", "carrier-only"])
        self.assertEqual(rc, 2)
        self.assertRegex(err, r"b \(relay-record\), c \(relay-record\)")
        self.assertEqual(self.moves(), [])

    def test_an_account_that_does_not_answer_is_not_known_to_be_past_relay_record(self):
        for l in self.LOGINS:
            self.put(l, "carrier-record")
        self.silent = {"c"}
        rc, out, err = self.run_ctl(["all", OP, "--mode", "carrier-only"])
        self.assertEqual(rc, 2)
        self.assertRegex(err, r"c \(did not report a mode\)")
        self.assertEqual(self.moves(), [])

    def test_with_every_account_past_relay_record_carrier_only_is_sent_and_set(self):
        self.put("a", "carrier-record")
        self.put("b", "carrier-only")
        self.put("c", "carrier-record")
        rc, out, err = self.run_ctl(["all", OP, "--mode", "carrier-only"])
        self.assertEqual((rc, self.modes()), (0, {l: "carrier-only" for l in self.LOGINS}), err)
        self.assertEqual(len(self.moves()), 1)

    def test_the_other_modes_are_never_held_back_by_the_fleet(self):
        rc, out, err = self.run_ctl(["a", OP, "--mode", "carrier-record"])
        self.assertEqual((rc, self.modes()["a"]), (0, "carrier-record"), err)
        rc, out, err = self.run_ctl(["a", OP, "--mode", "relay-record"])
        self.assertEqual((rc, self.modes()["a"]), (0, "relay-record"), err)


if __name__ == "__main__":
    unittest.main()
