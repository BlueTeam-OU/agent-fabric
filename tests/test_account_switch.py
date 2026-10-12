#!/usr/bin/env python3
"""tools/fabric/control/account_switch.py, switch_policy.py and switch_log.py: the account-switch controller
of agent-fabric ADR-052 §5. Every rule is driven by a table of readings -> decision; advise is shown never to
reach the assign path; the policy's judge and its lint rule, and the move log's format. Fixtures only: the
policy, templates and fleet rows are built here, never this checkout's live files, and fabric-ctl, gh and a
gateway are never called (the fleet reads and the assign path are fakes)."""
from __future__ import annotations

import copy
import inspect
import json
import os
import stat
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import account_switch as sw, switch_log, switch_policy  # noqa: E402
from control.account_switch import View  # noqa: E402

NOW = 1_800_000_000.0
H = 3600.0
D = 86400.0
POLICY = {
    "version": 1, "description": "a fixture", "mode": "advise",
    "pool": {"name": "claude", "accounts": ["acct-a", "acct-b", "acct-c"]},
    "land": {"five_hour": 0.90, "seven_day": 0.97}, "eject": {"five_hour": 0.97, "seven_day": 0.995},
    "perishable": {"within_hours": 24, "max_utilization": 0.60, "min_interval_s": 1800},
    "min_stay_s": 7200, "reading_max_age_s": 600, "probe_min_interval_s": 1800, "interval_s": 300,
    "why": {k: "because" for k in switch_policy.REASONED},
}
FPS = {"acct-a": "aaaaaaaaaaaa", "acct-b": "bbbbbbbbbbbb", "acct-c": "cccccccccccc", "own": "000000000000"}


def reading(u5=0.2, u7=0.3, *, r5=NOW + 3 * H, r7=NOW + 5 * D, status="allowed", age=30.0, mark=None,
            transient=0, status_reset=None, via="gateway"):
    return {"five_hour": {"utilization": u5, "reset": r5}, "seven_day": {"utilization": u7, "reset": r7},
            "status": status, "status_reset": status_reset, "exhausted": mark, "transient_429": transient,
            "read_at": NOW - age, "via": via, "from": "x"}


def login(name, account="acct-a", *, state="idle", idle_for=600.0, gateway=True, other=0, known=True, kinds_ok=True):
    return {"login": name, "account": account, "fingerprint": FPS.get(account), "gateway": gateway,
            "kinds": {"status": "ok", "gateway": 1, "other": other} if kinds_ok else {"status": "unknown"},
            "sessions": [{"session": f"s-{name}", "state": state, "since": sw.iso(NOW - idle_for)}],
            "state_known": known}


def views(readings, policy=POLICY):
    return {a: View(a, readings.get(a), NOW, policy["reading_max_age_s"]) for a in policy["pool"]["accounts"]}


def decide(readings, logins, history=(), policy=POLICY):
    return sw.decide(policy, views(readings, policy), logins, list(history), NOW)


def of(decisions, name):
    got = [d for d in decisions if d["login"] == name]
    assert len(got) <= 1, got
    return got[0] if got else {}


HEALTHY = {"acct-a": reading(0.5, 0.5), "acct-b": reading(0.2, 0.3, r7=NOW + 3 * D), "acct-c": reading(0.3, 0.4, r7=NOW + 4 * D)}


class Rules(unittest.TestCase):
    """§5 as a table: (what the readings say, the logins) -> the one decision for the login under test."""

    def table(self, rows):
        for name, readings, logins, history, want in rows:
            with self.subTest(name):
                d = of(decide(readings, logins, history), "x")
                got = {k: d.get(k) for k in want}
                self.assertEqual(got, want, f"{name}: {d}")

    def test_the_table(self):
        exhausted_a = {**HEALTHY, "acct-a": reading(0.5, 0.5, status="rejected", status_reset=NOW + H)}
        self.table([
            # rule 3: sticky — a better account is no reason
            ("a healthy account keeps its session, whatever is better", HEALTHY, [login("x")], [], {"outcome": None}),
            # rule 2 and 4: each signal of exhaustion moves at once, to the soonest seven-day reset (rule 6)
            ("status rejected moves at once, while working", exhausted_a, [login("x", state="working")], [],
             {"outcome": "move", "rule": 4, "reason": "exhausted", "to": "acct-b", "relaxed": False, "tell": False}),
            ("status rate_limited too", {**HEALTHY, "acct-a": reading(status="rate_limited", status_reset=NOW + H)},
             [login("x", state="blocked")], [], {"outcome": "move", "rule": 4, "to": "acct-b"}),
            ("a utilisation of 1 is exhaustion", {**HEALTHY, "acct-a": reading(1.0, 0.5)}, [login("x")], [],
             {"outcome": "move", "reason": "exhausted"}),
            ("a 429 the gateway classified exhausted", {**HEALTHY, "acct-a": reading(0.5, 0.5, mark={"at": NOW - 10, "reset": NOW + 600})},
             [login("x", state="working")], [], {"outcome": "move", "reason": "exhausted"}),
            ("a transient 429 moves nothing", {**HEALTHY, "acct-a": reading(0.5, 0.5, transient=7)}, [login("x")], [],
             {"outcome": None}),
            ("an exhaustion mark whose reset has passed moves nothing", {**HEALTHY, "acct-a": reading(0.5, 0.5, mark={"at": NOW - 900, "reset": NOW - 1})},
             [login("x")], [], {"outcome": None}),
            ("a stale refusing status with a reset still ahead is still exhaustion",
             {**HEALTHY, "acct-a": reading(0.5, 0.5, status="rejected", status_reset=NOW + H, age=3 * H)}, [login("x")], [],
             {"outcome": "move", "reason": "exhausted"}),
            # rule 1: stale and null are unknown, and a decision needing them is not taken
            ("a stale reading at the eject threshold moves nothing", {**HEALTHY, "acct-a": reading(0.99, 0.5, age=2 * H)},
             [login("x")], [], {"outcome": None}),
            ("a null five-hour utilisation decides no five-hour eject", {**HEALTHY, "acct-a": reading(None, 0.5)},
             [login("x")], [], {"outcome": None}),
            ("a window that has reset since the reading is unknown, not its old share",
             {**HEALTHY, "acct-a": reading(0.99, 0.5, r5=NOW - 60)}, [login("x")], [], {"outcome": None}),
            # hysteresis: between land and eject nothing moves
            ("above land, below eject: stays", {**HEALTHY, "acct-a": reading(0.93, 0.98)}, [login("x")], [], {"outcome": None}),
            # rule 5 and 8: eject at idle only
            ("eject-5h at idle", {**HEALTHY, "acct-a": reading(0.97, 0.5)}, [login("x")], [],
             {"outcome": "move", "rule": 5, "reason": "eject-5h", "to": "acct-b"}),
            ("eject-7d at idle", {**HEALTHY, "acct-a": reading(0.5, 0.996)}, [login("x")], [],
             {"outcome": "move", "rule": 5, "reason": "eject-7d"}),
            ("an eject waits while the login is working", {**HEALTHY, "acct-a": reading(0.98, 0.5)}, [login("x", state="working")], [],
             {"outcome": "defer", "rule": 5, "to": None}),
            ("an eject waits while it is blocked", {**HEALTHY, "acct-a": reading(0.98, 0.5)}, [login("x", state="blocked")], [],
             {"outcome": "defer"}),
            ("an eject waits while its state is unknown", {**HEALTHY, "acct-a": reading(0.98, 0.5)}, [login("x", known=False)], [],
             {"outcome": "defer"}),
            # rule 6: the target
            ("soonest seven-day reset first", {**exhausted_a, "acct-b": reading(0.2, 0.3, r7=NOW + 3 * D), "acct-c": reading(0.2, 0.9, r7=NOW + 2 * D)},
             [login("x")], [], {"to": "acct-c"}),
            ("a tie on the reset goes to the lower seven-day use",
             {**exhausted_a, "acct-b": reading(0.2, 0.8, r7=NOW + 3 * D), "acct-c": reading(0.2, 0.7, r7=NOW + 3 * D)},
             [login("x")], [], {"to": "acct-c"}),
            ("over a land threshold is not a target while another is under",
             {**exhausted_a, "acct-b": reading(0.95, 0.3, r7=NOW + D), "acct-c": reading(0.2, 0.3, r7=NOW + 3 * D)},
             [login("x")], [], {"to": "acct-c", "relaxed": False}),
            ("none under land: the most headroom, relaxed, the owner told",
             {**exhausted_a, "acct-b": reading(0.95, 0.5, r7=NOW + D), "acct-c": reading(0.92, 0.5, r7=NOW + 3 * D)},
             [login("x")], [], {"outcome": "move", "to": "acct-c", "relaxed": True, "tell": True}),
            ("every account exhausted: nothing moves, the owner told",
             {"acct-a": reading(status="rejected", status_reset=NOW + H), "acct-b": reading(1.0, 0.4), "acct-c": reading(0.4, 1.2)},
             [login("x")], [], {"outcome": "hold", "to": None, "tell": True}),
            ("no other account known: nothing moves, the owner told", {"acct-a": reading(1.0, 0.5)}, [login("x")], [],
             {"outcome": "hold", "to": None, "tell": True}),
            # rule 13: scope
            ("a plain-claude login on an exhausted account is not moved", exhausted_a, [login("x", gateway=False)], [],
             {"outcome": "skip"}),
            ("a plain-claude session beside the gateway: not moved", exhausted_a, [login("x", other=1)], [], {"outcome": "skip"}),
            ("sessions that cannot be told apart: not moved", exhausted_a, [login("x", kinds_ok=False)], [], {"outcome": "skip"}),
        ])

    def test_a_logins_own_sign_in_or_an_account_outside_the_pool_is_never_a_target(self):
        everyone_out = {"acct-a": reading(1.0, 0.5), "acct-b": reading(1.0, 0.5), "acct-c": reading(status="rejected", status_reset=NOW + H),
                        "own": reading(0.0, 0.0, r7=NOW + H)}
        d = of(decide(everyone_out, [login("x")]), "x")
        self.assertEqual((d["outcome"], d["to"]), ("hold", None), "the roomy account outside the pool is never chosen")
        self.assertIn("never its own sign-in", d["why"])
        self.assertEqual(of(decide(HEALTHY, [login("x", account="own")]), "x")["outcome"], "skip",
                         "a login on an account outside the pool is not the pool's to move")
        target, _ = sw.choose_target(views(everyone_out), POLICY["pool"]["accounts"], "acct-a", POLICY["land"])
        self.assertIsNone(target)

    def test_a_relaxed_target_with_no_more_room_than_the_ejected_account_is_no_move(self):
        r = {**HEALTHY, "acct-a": reading(0.975, 0.5), "acct-b": reading(0.99, 0.5), "acct-c": reading(0.98, 0.5)}
        d = of(decide(r, [login("x")]), "x")
        self.assertEqual((d["outcome"], d["tell"]), ("hold", True), d)

    def test_perishable_moves_one_idle_session_and_the_rate_limit_holds_the_second(self):
        r = {"acct-a": reading(0.3, 0.5, r7=NOW + 5 * D), "acct-b": reading(0.3, 0.5, r7=NOW + 6 * D),
             "acct-c": reading(0.1, 0.3, r7=NOW + 10 * H)}
        ds = decide(r, [login("x", idle_for=600), login("y", account="acct-b", idle_for=3000)])
        y, x = of(ds, "y"), of(ds, "x")
        self.assertEqual((y["outcome"], y["rule"], y["reason"], y["to"]), ("move", 7, "perishable", "acct-c"),
                         "the one idle longest goes first (rule 8)")
        self.assertEqual((x["outcome"], x["to"]), ("hold", "acct-c"), x)
        self.assertIn("one perishable move per pool per 1800 s", x["why"])
        recent = [{"at": sw.iso(NOW - 600), "login": "z", "reason": "perishable", "pool": "claude", "outcome": "would"}]
        ds = decide(r, [login("x"), login("y", account="acct-b")], recent)
        self.assertEqual({d["outcome"] for d in ds}, {"hold"}, "a perishable move 10 minutes ago holds both")
        later = [{**recent[0], "at": sw.iso(NOW - 1900)}]
        self.assertIn("move", {d["outcome"] for d in decide(r, [login("x")], later)}, "after the interval one moves again")

    def test_perishable_needs_idle_a_window_due_and_unused_and_respects_min_stay(self):
        due = {"acct-a": reading(0.3, 0.5, r7=NOW + 5 * D), "acct-b": reading(0.3, 0.5, r7=NOW + 6 * D),
               "acct-c": reading(0.1, 0.3, r7=NOW + 10 * H)}
        self.assertEqual(of(decide(due, [login("x", state="working")]), "x")["outcome"], "defer")
        stayed = [{"at": sw.iso(NOW - 3600), "login": "x", "reason": "exhausted", "pool": "claude", "outcome": "would"}]
        self.assertEqual(of(decide(due, [login("x")], stayed), "x")["outcome"], "skip", "moved an hour ago: min_stay_s holds it")
        for name, c in (("resets in 30 h", reading(0.1, 0.3, r7=NOW + 30 * H)), ("used 0.7", reading(0.1, 0.7, r7=NOW + 10 * H)),
                        ("over the five-hour land", reading(0.95, 0.3, r7=NOW + 10 * H)), ("its seven-day use unknown", reading(0.1, None, r7=NOW + 10 * H))):
            with self.subTest(name):
                self.assertEqual(decide({**due, "acct-c": c}, [login("x")]), [], name)
        sooner = {**due, "acct-a": reading(0.3, 0.5, r7=NOW + 5 * H)}
        self.assertEqual(decide(sooner, [login("x")]), [], "its own quota perishes sooner: not moved off it")

    def test_an_exhaustion_move_is_not_counted_against_the_perishable_rate(self):
        r = {"acct-a": reading(1.0, 0.5), "acct-b": reading(0.3, 0.5, r7=NOW + 6 * D), "acct-c": reading(0.1, 0.3, r7=NOW + 10 * H)}
        recent = [{"at": sw.iso(NOW - 60), "login": "z", "reason": "perishable", "pool": "claude", "outcome": "would"}]
        self.assertEqual(of(decide(r, [login("x")], recent), "x")["outcome"], "move")

    def test_stale_and_absent_accounts_are_probed_at_most_once_per_interval(self):
        v = views({"acct-a": reading(), "acct-b": reading(age=2 * H)})
        self.assertEqual(sw.probe_due(v, POLICY["pool"]["accounts"], {}, NOW, 1800), ["acct-b", "acct-c"])
        self.assertEqual(sw.probe_due(v, POLICY["pool"]["accounts"], {"acct-b": NOW - 60}, NOW, 1800), ["acct-c"])


class Readings(unittest.TestCase):
    ENTRY = {"source": {"token_file": "/t"}, "generation": {"device": 1, "inode": 2, "mtime_sec": 3, "mtime_nsec": 4},
             "read_at": int(NOW) - 30,
             "usage": {"five_hour": {"utilization": 0.42, "reset": int(NOW) + 3600, "surpassed_threshold": None},
                       "seven_day": {"utilization": 0.9, "reset": int(NOW) + 86400, "surpassed_threshold": 0.75},
                       "status": "allowed_warning", "reset": int(NOW) + 3600},
             "exhausted": None, "transient_429": 2}

    def test_a_gateway_entry_and_a_probe_row_read_alike(self):
        g = sw.reading_from_gateway(self.ENTRY, "x")
        self.assertEqual((g["five_hour"]["utilization"], g["seven_day"]["reset"], g["status"], g["transient_429"]),
                         (0.42, NOW + 86400, "allowed_warning", 2))
        p = sw.reading_from_probe({"status": "ok", "usage_status": "ok", "five_hour": {"utilization": 42, "resets_at": sw.iso(NOW + 3600)},
                                   "seven_day": {"utilization": 90.5, "resets_at": sw.iso(NOW + 86400)}}, "x", NOW)
        self.assertEqual((p["five_hour"]["utilization"], p["seven_day"]["utilization"], p["seven_day"]["reset"], p["via"]),
                         (0.42, 0.905, NOW + 86400, "probe"))
        self.assertIsNone(sw.reading_from_probe({"status": "ok", "usage_status": "read-failed"}, "x", NOW))
        empty = sw.reading_from_gateway({"source": {"token_file": "/t"}, "usage": None, "read_at": None}, "x")
        self.assertIsNone(empty["five_hour"]["utilization"], "null is unknown, never 0")

    def test_the_freshest_reading_counts_and_an_exhaustion_mark_is_kept(self):
        old = {**reading(0.9, 0.9, age=500), "exhausted": {"at": NOW - 400, "reset": NOW + 600}}
        new = reading(0.1, 0.1, age=10)
        got = sw.freshest([old, new], NOW)
        self.assertEqual(got["five_hour"]["utilization"], 0.1)
        self.assertTrue(View("a", got, NOW, 600).exhausted)

    def test_gather_joins_generations_to_templates_and_reads_the_session_kinds(self):
        templates = [{"account": a, "token_sha256_12": fp} for a, fp in FPS.items() if a != "own"]
        rows = {
            ("all", "identity"): [{"account": "gw", "status": "ok", "email": "setup-token aaaaaaaaaaaa"},
                                  {"account": "plain", "status": "ok", "email": "setup-token bbbbbbbbbbbb"},
                                  {"account": "silent", "status": "no answer"}],
            ("all", "gateway"): [{"account": "gw", "status": "ok", "gateway": {
                "status": "ok", "usage": {"status": "ok", "credentials": [self.ENTRY, {**self.ENTRY, "generation": None}]},
                "setup_tokens": ["aaaaaaaaaaaa", None], "sessions": {"status": "ok", "gateway": 1, "other": 0}}},
                {"account": "plain", "status": "ok", "gateway": {"status": "absent"}}],
            ("all", "states"): [{"address": "h/gw", "state": "idle", "sessions": [{"session": "s1", "state": "idle", "since": "2026-10-12T10:00:00.000Z"}]},
                                {"address": "h/plain", "state": "unknown", "sessions": [], "why": "no record for two heartbeats"}],
        }
        readings, logins = sw.gather(lambda args: rows[tuple(args)], templates)
        self.assertEqual(list(readings), ["acct-a"], "only the joined generation is a reading, and under its account")
        by = {lg["login"]: lg for lg in logins}
        self.assertEqual((by["gw"]["account"], by["gw"]["gateway"], by["gw"]["state_known"]), ("acct-a", True, True))
        self.assertEqual((by["plain"]["account"], by["plain"]["gateway"], by["plain"]["state_known"]), ("acct-b", False, False))
        self.assertIsNone(by["silent"]["account"])


class Ahead(unittest.TestCase):
    """A stamp ahead of the controller's clock is no reading (F1)."""

    def test_a_reading_from_the_future_is_unknown_and_probed(self):
        future = reading(1.0, 0.5, r5=None, age=-3600)
        self.assertEqual(of(decide({**HEALTHY, "acct-a": future}, [login("x")]), "x"), {}, "no rule-4 move on it")
        v = views({**HEALTHY, "acct-a": future})
        self.assertIn("acct-a", sw.probe_due(v, POLICY["pool"]["accounts"], {}, NOW, 1800))
        real = reading(0.2, 0.3, age=100)
        self.assertIs(sw.freshest([future, real], NOW), real, "it does not outrank a real reading")
        self.assertEqual(sw.freshest([reading(0.2, 0.3, age=-30)], NOW)["read_at"], NOW + 30, "within the skew it counts")

    def test_an_exhaustion_mark_from_the_future_is_no_exhaustion(self):
        r = reading(0.2, 0.3, mark={"at": NOW + 3600, "reset": None})
        self.assertFalse(View("a", r, NOW, 600).exhausted)
        self.assertFalse(View("a", sw.freshest([r], NOW), NOW, 600).exhausted)


class Untrusted(unittest.TestCase):
    """What another account relayed is data: a value that is not a finite, sane number is unknown (F3)."""

    def entry(self, five=None, seven=None):
        return {"source": {"token_file": "/t"}, "read_at": int(NOW) - 30,
                "usage": {"five_hour": five or {"utilization": 0.2, "reset": int(NOW) + 3600},
                          "seven_day": seven or {"utilization": 0.3, "reset": int(NOW) + 5 * 86400}, "status": "allowed"}}

    def test_bad_numbers_read_as_unknown(self):
        for bad in (float("inf"), float("nan"), -5, 1e300, True, "0.5"):
            with self.subTest(utilization=bad):
                r = sw.reading_from_gateway(self.entry(five={"utilization": bad, "reset": int(NOW) + 3600}), "x")
                self.assertIsNone(r["five_hour"]["utilization"])
            with self.subTest(reset=bad):
                r = sw.reading_from_gateway(self.entry(seven={"utilization": 0.3, "reset": bad}), "x")
                self.assertIsNone(r["seven_day"]["reset"])
        self.assertIsNone(sw.epoch_s(10 ** 400), "an integer past a double")
        self.assertIsNone(sw.epoch_s("9999-12-31T23:59:59Z"))

    def test_bad_numbers_neither_move_nor_become_a_target(self):
        inf = json.loads('{"utilization": Infinity, "reset": %d}' % (NOW + 3600))
        nan = json.loads('{"utilization": NaN, "reset": %d}' % (NOW + 3600))
        a_inf = sw.reading_from_gateway({**self.entry(five=inf), "read_at": int(NOW) - 30}, "x")
        self.assertEqual(of(decide({**HEALTHY, "acct-a": a_inf}, [login("x")]), "x"), {}, "Infinity is not exhaustion")
        exhausted = {**HEALTHY, "acct-a": reading(1.0, 0.5),
                     "acct-b": sw.reading_from_gateway(self.entry(five=nan), "x"),
                     "acct-c": sw.reading_from_gateway(self.entry(seven={"utilization": 0.3, "reset": -5}), "x")}
        d = of(decide(exhausted, [login("x")]), "x")
        self.assertNotEqual(d.get("to"), "acct-b", "a NaN utilisation is no relaxed target")
        self.assertNotEqual((d.get("to"), d.get("relaxed")), ("acct-c", False), "a reset of -5 is not the soonest")

    def test_one_accounts_overflowing_reset_does_not_stop_the_run(self):
        bad = {**EXHAUSTED, "seven_day": {"utilization": 0.5, "reset": 1e300}}
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "p.json")
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(TWO, fh)
            out = []
            rc = sw.run(record=True, root=d, state=d, policy_file=p, ctl=Fleet(bad),
                        templates=lambda: [{"account": a, "token_sha256_12": FPS[a]} for a in ("acct-a", "acct-b")],
                        make_assign=lambda root: 1 / 0, now=lambda: NOW, say=out.append)
            self.assertEqual(rc, 0, out)
            self.assertEqual(switch_log.tail(d)[-1]["outcome"], "would", "the exhausted login is still decided")


class Fleet:
    """The three fleet reads and the probe, as fabric-ctl --json rows; records what was asked."""

    def __init__(self, a_reading: dict, state="idle"):
        self.asked = []
        self.entry = {"source": {"token_file": "/t"}, "generation": {"device": 1, "inode": 1, "mtime_sec": 1, "mtime_nsec": 0},
                      "read_at": int(NOW) - 30, "usage": a_reading, "exhausted": None, "transient_429": 0}
        self.state = state

    def __call__(self, args):
        self.asked.append(args)
        if args == ["all", "identity"]:
            return [{"account": "gw", "status": "ok", "email": "setup-token aaaaaaaaaaaa"},
                    {"account": "onb", "status": "ok", "email": "setup-token bbbbbbbbbbbb"}]
        if args == ["all", "gateway"]:
            return [{"account": "gw", "status": "ok", "gateway": {"usage": {"status": "ok", "credentials": [self.entry]},
                                                                 "setup_tokens": ["aaaaaaaaaaaa"],
                                                                 "sessions": {"status": "ok", "gateway": 1, "other": 0}}},
                    {"account": "onb", "status": "ok", "gateway": {"status": "absent"}}]
        if args == ["all", "states"]:
            return [{"address": "h/gw", "state": self.state, "sessions": [{"session": "s1", "state": self.state, "since": sw.iso(NOW - 900)}]},
                    {"address": "h/onb", "state": "idle", "sessions": [{"session": "s2", "state": "idle", "since": sw.iso(NOW - 900)}]}]
        if args == ["onb", "usage"]:
            return [{"account": "onb", "status": "ok", "usage_status": "ok", "five_hour": {"utilization": 10, "resets_at": sw.iso(NOW + H)},
                     "seven_day": {"utilization": 20, "resets_at": sw.iso(NOW + 3 * D)}}]
        return []


EXHAUSTED = {"five_hour": {"utilization": 1.0, "reset": int(NOW) + 3600}, "seven_day": {"utilization": 0.5, "reset": int(NOW) + 5 * 86400},
             "status": "rejected", "reset": int(NOW) + 3600}
TWO = {**POLICY, "pool": {"name": "claude", "accounts": ["acct-a", "acct-b"]}}


class Runs(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.dir.name, "state")
        self.out: list[str] = []

    def tearDown(self):
        self.dir.cleanup()

    def policy(self, **over) -> str:
        doc = copy.deepcopy(TWO)
        doc.update(over)
        p = os.path.join(self.dir.name, "account-switch.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        return p

    def run_once(self, fleet, *, record=True, make_assign=None, **policy):
        def refuse(root):
            raise AssertionError("the assign path was built")
        return sw.run(record=record, root=self.dir.name, state=self.state, policy_file=self.policy(**policy), ctl=fleet,
                      templates=lambda: [{"account": "acct-a", "token_sha256_12": FPS["acct-a"]},
                                         {"account": "acct-b", "token_sha256_12": FPS["acct-b"]}],
                      make_assign=make_assign or refuse, now=lambda: NOW, say=self.out.append)

    def log(self):
        return switch_log.tail(self.state, 100)

    def test_advise_decides_and_logs_and_never_reaches_assign(self):
        fleet = Fleet(EXHAUSTED)
        self.assertEqual(self.run_once(fleet), 0, self.out)
        lines = self.log()
        self.assertEqual(len(lines), 1, lines)
        e = lines[0]
        self.assertEqual((e["mode"], e["outcome"], e["login"], e["rule"], e["reason"], e["from"], e["to"]),
                         ("advise", "would", "gw", 4, "exhausted", {"account": "acct-a", "fingerprint": FPS["acct-a"]},
                          {"account": "acct-b", "fingerprint": FPS["acct-b"]}))
        self.assertNotIn("assign", e)
        self.assertIn(["onb", "usage"], fleet.asked, "the account with no gateway reading was probed (rule 1)")
        self.assertEqual(e["readings"]["acct-b"]["via"], "probe")
        self.assertEqual(self.run_once(Fleet(EXHAUSTED)), 0)
        self.assertEqual(len(self.log()), 1, "a decision that holds is logged once")

    def test_advise_cannot_hold_the_assign_path(self):
        self.assertNotIn("assign", inspect.signature(sw.would).parameters)
        src = inspect.getsource(sw.run)
        self.assertEqual(src.count("make_assign("), 1, "the assign path is built in one place")
        self.assertRegex(src, r'if mode == "act":\s*\n(\s*#.*\n)*\s*logged = act\(lines, make_assign\(root\)\)',
                         "and only under act")

    def test_act_moves_by_the_assign_path_and_logs_the_verdict(self):
        calls = []

        def make(root):
            def assign(login_, account):
                calls.append((login_, account))
                return {"exit": 0, "output": ["gw  acct-a -> acct-b  written", "running (gateway): token file replaced"]}
            return assign
        self.assertEqual(self.run_once(Fleet(EXHAUSTED), make_assign=make, mode="act"), 0, self.out)
        self.assertEqual(calls, [("gw", "acct-b")])
        e = self.log()[-1]
        self.assertEqual((e["mode"], e["outcome"], e["assign"]["exit"]), ("act", "did", 0))

    def test_act_says_a_failed_assign_and_assumes_nothing(self):
        make = lambda root: (lambda lg, a: {"exit": 1, "output": ["failed"]})  # noqa: E731
        self.assertEqual(self.run_once(Fleet(EXHAUSTED), make_assign=make, mode="act"), 1)
        self.assertEqual(self.log()[-1]["outcome"], "failed")

    def test_the_assign_path_is_fabric_accounts_assign_with_no_restart(self):
        seen = []

        class R:
            returncode, stdout, stderr = 0, b"row\n", b""
        got = sw.assign_path("/fabric", run=lambda cmd, **kw: seen.append(cmd) or R())("gw", "acct-b")
        self.assertEqual(seen, [["/fabric/bin/fabric-accounts", "assign", "gw", "acct-b", "--no-restart"]])
        self.assertEqual(got, {"exit": 0, "output": ["row"]})

    def test_off_decides_nothing_and_a_dry_run_logs_nothing(self):
        fleet = Fleet(EXHAUSTED)
        self.assertEqual(self.run_once(fleet, mode="off"), 0)
        self.assertEqual((fleet.asked, self.log()), ([], []))
        self.assertEqual(self.run_once(Fleet(EXHAUSTED), record=False), 0)
        self.assertEqual(self.log(), [], "`fabric-accounts switch` prints, it never logs")
        self.assertTrue(any("gw" in line and "acct-b" in line for line in self.out), self.out)

    def test_one_run_at_a_time(self):
        fd = sw.take_lock(self.state)
        try:
            fleet = Fleet(EXHAUSTED)
            self.assertEqual(self.run_once(fleet), 1)
            self.assertEqual(fleet.asked, [], "the second run asks nothing")
        finally:
            os.close(fd)

    def test_a_policy_that_does_not_pass_its_judge_runs_nothing(self):
        fleet = Fleet(EXHAUSTED)
        self.assertEqual(self.run_once(fleet, land={"five_hour": 0.99, "seven_day": 0.97}), 2)
        self.assertEqual(fleet.asked, [])

    def test_the_log_format(self):
        self.run_once(Fleet(EXHAUSTED))
        with open(switch_log.path(self.state), encoding="utf-8") as fh:
            raw = fh.read()
        self.assertEqual(stat.S_IMODE(os.stat(switch_log.path(self.state)).st_mode), 0o600)
        self.assertTrue(raw.endswith("\n") and raw.count("\n") == 1, "one JSON object a line")
        e = json.loads(raw)
        self.assertEqual(list(e)[:len(switch_log.KEYS)], list(switch_log.KEYS))
        self.assertEqual(e["v"], 1)
        self.assertIn(e["outcome"], switch_log.OUTCOMES)
        self.assertIn(e["reason"], switch_log.REASONS)
        self.assertEqual(sorted(e["readings"]), ["acct-a", "acct-b"])
        self.assertEqual(sorted(e["readings"]["acct-a"]), ["age_s", "exhausted", "five_hour", "read_at", "seven_day", "status", "via"])
        self.assertEqual(e["readings"]["acct-a"]["five_hour"]["utilization"], 1.0)
        self.assertNotIn("/t", raw, "no source path, token or header beyond the parsed fields")
        self.assertIn("would", switch_log.words(e))

    def test_an_all_exhausted_pool_is_logged_once_and_told(self):
        fleet = Fleet(EXHAUSTED)
        orig = fleet.__call__

        def both_out(args):
            if args == ["onb", "usage"]:
                return [{"account": "onb", "status": "ok", "usage_status": "ok", "five_hour": {"utilization": 100, "resets_at": sw.iso(NOW + H)},
                         "seven_day": {"utilization": 20, "resets_at": sw.iso(NOW + 3 * D)}}]
            return orig(args)
        self.run_once(both_out)
        e = self.log()[-1]
        self.assertEqual((e["outcome"], e["to"], e["tell"]), ("held", None, True))
        self.assertIn("TOLD", switch_log.words({**e, "outcome": "would"}))


class Policy(unittest.TestCase):
    def test_the_judge(self):
        self.assertEqual(switch_policy.problems(POLICY), [])
        cases = [
            ("mode", {"mode": "auto"}, "mode must be one of"),
            ("land at eject", {"land": {"five_hour": 0.97, "seven_day": 0.97}}, "land.five_hour must be below eject.five_hour"),
            ("eject above 1", {"eject": {"five_hour": 1.2, "seven_day": 0.995}}, "eject.five_hour must be a share"),
            ("a pool of one", {"pool": {"name": "claude", "accounts": ["acct-a"]}}, "at least two"),
            ("twice", {"pool": {"name": "claude", "accounts": ["acct-a", "acct-a"]}}, "listed twice"),
            ("not a slug", {"pool": {"name": "claude", "accounts": ["acct-a", "Not A Slug"]}}, "not a template slug"),
            ("no reason", {"why": {k: "x" for k in switch_policy.REASONED if k != "eject"}}, "no reason for eject"),
            ("a window past a week", {"perishable": {"within_hours": 200, "max_utilization": 0.6, "min_interval_s": 1800}}, "within_hours"),
            ("seconds", {"interval_s": 5}, "interval_s must be"),
        ]
        for name, over, want in cases:
            with self.subTest(name):
                got = switch_policy.problems({**POLICY, **over})
                self.assertTrue(any(want in p for p in got), got)

    def test_lint_judges_the_file_with_the_schema_and_the_same_judge(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("lint_under_test", os.path.join(HERE, "tools", "fabric", "lint.py"))
        lint = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lint)
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "routing", "schemas"))
            with open(os.path.join(HERE, "routing", "schemas", "account-switch.schema.json"), encoding="utf-8") as fh:
                schema = fh.read()
            with open(os.path.join(d, "routing", "schemas", "account-switch.schema.json"), "w", encoding="utf-8") as fh:
                fh.write(schema)
            p = os.path.join(d, "policy.json")
            self.assertEqual(lint.account_switch_findings(d, p), [], "no file: not judged")
            for doc, want in ((POLICY, None), ({**POLICY, "extra": 1}, "extra"), ({**POLICY, "mode": "auto"}, "mode"),
                              ({**POLICY, "land": {"five_hour": 0.98, "seven_day": 0.97}}, "below eject")):
                with open(p, "w", encoding="utf-8") as fh:
                    json.dump(doc, fh)
                got = lint.account_switch_findings(d, p)
                if want is None:
                    self.assertEqual(got, [])
                else:
                    self.assertTrue(got and all(f.startswith("routing/policies/account-switch.json: ") for f in got)
                                    and any(want in f for f in got), got)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("{not json")
            self.assertTrue(any("not valid JSON" in f for f in lint.account_switch_findings(d, p)))


class Surfaces(unittest.TestCase):
    """Where the log is read (rule 12): the control agent's `switch` read and its fabric-ctl table, the
    fabric-status line, and the timer that runs the controller only on an operator's account."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.state = os.path.join(self.dir.name, "state")
        self.policy = os.path.join(self.dir.name, "account-switch.json")
        with open(self.policy, "w", encoding="utf-8") as fh:
            json.dump(TWO, fh)
        self.entry = switch_log.line(
            v=1, at=sw.iso(NOW), mode="advise", outcome="would", pool="claude", login="gw", sessions=["s1"], rule=5,
            reason="eject-5h", relaxed=True, **{"from": {"account": "acct-a", "fingerprint": FPS["acct-a"]}},
            to={"account": "acct-b", "fingerprint": FPS["acct-b"]}, readings={}, tell=True, why="w")

    def test_the_control_agents_read_and_its_table(self):
        from control import ctl, ops
        self.assertIn("switch", ops.OPS)
        self.assertNotIn("switch", ops.PUBLIC_OPS, "an operator's read, like gateway")
        self.assertEqual(ctl.parse_args(["user", "switch"])["op"], "switch")
        ctx = {"switch_opts": {"state": self.state, "policy": self.policy}}
        self.assertEqual(ops.collect("switch", ctx), {"switch": {"status": "none", "mode": "advise", "lines": []}})
        switch_log.append(self.state, [self.entry])
        got = ops.collect("switch", ctx)["switch"]
        self.assertEqual((got["status"], got["lines"]), ("ok", [self.entry]))
        lines = ctl.table("switch", [{"account": "user", "status": "ok", "switch": got},
                                     {"account": "other", "status": "ok", "switch": {"status": "none", "mode": "advise", "lines": []}},
                                     {"account": "silent", "status": "no answer"}]).split("\n")
        self.assertIn("advise", lines[1])
        self.assertIn("would  gw  acct-a -> acct-b  (eject-5h, relaxed)  TOLD", lines[2])
        self.assertIn("no move logged", lines[3])
        self.assertIn("no answer", lines[4])

    def test_the_status_line(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("status_under_test", os.path.join(HERE, "tools", "fabric", "status.py"))
        status = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(status)
        self.assertIsNone(status.account_switch(HERE, self.state, self.policy), "an account with no log prints no line")
        switch_log.append(self.state, [self.entry])
        got = status.account_switch(HERE, self.state, self.policy)
        self.assertEqual(got["status"], "ok")
        self.assertTrue(got["detail"].startswith("advise; last "), got)
        self.assertIn("acct-a -> acct-b", got["told"])
        out = status.render({"agent": "a", "host": "h", "role": None, "launched_role": None, "drift": None, "project": None,
                             "working_copy": None, "session": None, "binding_updated": None, "jobs": {"error": "x"},
                             "api": {"provider": "anthropic", "path": "p", "session_model": "m", "launch_profile": None, "pins": "none",
                                     "credentials": "none", "claude_sign_in": "x"},
                             "capabilities": {}, "routing_check": "clean", "undrained_memories": None,
                             "host_tools": {"moveto": {"installed": False}, "account_switch": got}, "control_plane": "/r"}, None)
        self.assertTrue(any(line.startswith("switch       advise; last ") for line in out), out)
        self.assertTrue(any(line.startswith("switch told  ") for line in out), out)

    def test_the_timer_starts_only_with_a_policy_it_can_run_on(self):
        started = []

        class T:
            def __init__(self, name, fn, every, first_s=0):
                started.append((name, every, first_s))

            def start(self):
                return self
        said = []
        orig = sw._policy_file
        try:
            sw._policy_file = lambda root: self.policy
            sw.start(T, said.append)
            self.assertEqual(started, [("account switch", 300, sw.FIRST_TICK_S)])
            sw._policy_file = lambda root: os.path.join(self.dir.name, "absent.json")
            sw.start(T, said.append)
            self.assertEqual(len(started), 1)
            self.assertIn("not started", said[-1])
        finally:
            sw._policy_file = orig

    def test_agentd_runs_it_only_on_an_operators_account(self):
        with open(os.path.join(HERE, "tools", "fabric", "control", "agentd.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertRegex(src, r'if me\["address"\] in operator_addresses\(\):\s*\n\s*from control import account_switch\s*\n\s*account_switch\.start\(Ticker, _stderr\)')


if __name__ == "__main__":
    unittest.main()
