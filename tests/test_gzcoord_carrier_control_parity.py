#!/usr/bin/env python3
"""Tests for tools/fabric/gzcoord/carrier/control_parity.py — the control plane's parity computation (ADR-029 rule 18).
Built on synthetic arrival logs whose answers are known by construction: every case plants one fact (a carrier that
missed, a cause, a drill, a window edge) and reads the one number or word that fact must move."""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from gzcoord.carrier import control_parity as cp, main as carrier_main  # noqa: E402

T0 = 1_792_000_000
OP, A, B = "h/user", "h/alice", "h/bob"


def iso(s: int) -> str:
    return cp.iso(T0 + s)


def sent(rid: str, s: int, to: list[str], verdict: str = "sent") -> dict:
    return {"t": iso(s), "who": "ctl", "carrier": "relay", "kind": "request", "id": rid, "from": OP, "op": "ping", "verdict": verdict, "to": to}


def got(rid: str, frm: str, carrier: str, s: int, who: str = "ctl", verdict: str | None = None) -> dict:
    v = verdict or ("ok" if carrier == "interweave" else "unauthenticated")
    return {"t": iso(s), "who": who, "carrier": carrier, "kind": "reply", "id": f"p-{rid}-{frm}-{carrier}", "in_reply_to": rid, "from": frm, "op": None, "verdict": v}


def load(files: dict[str, list[dict]]) -> dict[str, list[dict]]:
    return {k: [{**r, "_t": cp.parse_t(r["t"])} for r in rows] for k, rows in files.items()}


def run(rows: list[dict], window=(0, 1000), drill=None, others: dict[str, list[dict]] | None = None) -> dict:
    files = load({"user": rows, **(others or {})})
    return cp.compute(files, "user", (T0 + window[0], T0 + window[1]), (T0 + drill[0], T0 + drill[1]) if drill else None)


def pair(rep: dict, rid: str, addressee: str) -> dict:
    return next(p for p in rep["pairs"] if p["id"] == rid and p["addressee"] == addressee)


def late_case(arrives: int, *, timeout_s: float | None = 20, extra: list[dict] | None = None) -> dict:
    """alice's relay copy comes at 2 s; agentd routed her InterWeave reply to nobody at `arrives` s."""
    line = {**sent("r1", 0, [A]), **({"timeout_s": timeout_s} if timeout_s is not None else {})}
    return run([line, got("r1", A, "relay", 2), got("r1", A, "interweave", arrives, who="agentd", verdict="no-waiter"), *(extra or [])])


class LateAndNoSession(unittest.TestCase):
    """j160: 680 of 727 no-waiter lines were InterWeave replies 6-99 s after the request, behind a fabric-ctl that had left
    3 s after the relay's copies. With the carrier alone fabric-ctl waits for them, so inside `timeout_s` they are no miss."""

    def test_a_reply_that_reached_agentd_inside_the_requests_timeout_is_late_and_no_miss(self):
        rep = late_case(15)
        self.assertEqual(pair(rep, "r1", A)["cause"], "late")
        self.assertEqual(pair(rep, "r1", A)["interweave_late_s"], 15)
        self.assertEqual((rep["carriers"]["interweave"]["missed"], rep["carriers"]["interweave"]["late"]), (0, 1))
        self.assertEqual(rep["causes"]["late"], 1)

    def test_a_reply_past_the_timeout_stays_a_no_waiter_and_a_miss(self):
        rep = late_case(21)
        self.assertEqual(pair(rep, "r1", A)["cause"], "no-waiter")
        self.assertEqual((rep["carriers"]["interweave"]["missed"], rep["carriers"]["interweave"]["late"]), (1, 0))

    def test_a_log_without_the_timeout_keeps_the_old_reading(self):
        rep = late_case(5, timeout_s=None)
        self.assertEqual(pair(rep, "r1", A)["cause"], "no-waiter")
        self.assertEqual(rep["carriers"]["interweave"]["missed"], 1)

    def test_a_session_lost_before_the_reply_makes_it_a_real_no_waiter_whatever_the_timeout(self):
        lost = {"t": iso(3), "who": "ctl", "carrier": "interweave", "kind": "request", "id": "r1", "from": OP, "op": "ping", "verdict": "session-lost"}
        rep = late_case(15, extra=[lost])
        self.assertEqual(pair(rep, "r1", A)["cause"], "no-waiter")
        self.assertEqual(rep["carriers"]["interweave"]["missed"], 1)

    def test_no_session_is_its_own_cause_and_no_miss(self):
        none = {"t": iso(0), "who": "ctl", "carrier": "interweave", "kind": "request", "id": "r1", "from": OP, "op": "ping", "verdict": "no-session"}
        rep = late_case(5, extra=[none])
        self.assertEqual(pair(rep, "r1", A)["cause"], "no-session")
        self.assertEqual((rep["carriers"]["interweave"]["missed"], rep["carriers"]["interweave"]["no_session"]), (0, 1))

    def test_a_reply_at_the_very_second_the_timeout_ends_is_no_late_reply(self):
        rep = late_case(20)
        self.assertEqual(pair(rep, "r1", A)["cause"], "no-waiter")
        self.assertEqual(rep["carriers"]["interweave"]["late"], 0)

    def test_a_pair_with_no_copy_in_a_run_with_no_session_is_a_timeout_and_no_interweave_miss(self):
        none = {"t": iso(0), "who": "ctl", "carrier": "interweave", "kind": "request", "id": "r1", "from": OP, "op": "ping", "verdict": "no-session"}
        rep = run([{**sent("r1", 0, [A]), "timeout_s": 20}, none])
        self.assertEqual(pair(rep, "r1", A)["cause"], "timeout")
        self.assertEqual((rep["carriers"]["interweave"]["missed"], rep["carriers"]["interweave"]["no_session"]), (0, 1))

    def test_the_markdown_says_late_and_no_session_are_in_no_missed_count(self):
        text = cp.render_markdown(late_case(15))
        self.assertIn("1 pair(s) were `late` and 0 belong to a run with no session", text)
        self.assertIn("in no `missed` count of the interweave row", text)

    def test_the_markdown_counts_the_timeout_pair_of_a_run_with_no_session_among_those_left_out_of_missed(self):
        none = {"t": iso(0), "who": "ctl", "carrier": "interweave", "kind": "request", "id": "r1", "from": OP, "op": "ping", "verdict": "no-session"}
        text = cp.render_markdown(run([{**sent("r1", 0, [A]), "timeout_s": 20}, none]))
        self.assertIn("0 pair(s) were `late` and 1 belong to a run with no session", text)
        self.assertIn("| relay | 0 | 1 |", text, "the relay row still counts that pair missed, which the sentence no longer denies")

    def test_a_non_finite_timeout_is_no_timeout_and_never_a_crash(self):
        # json.loads accepts Infinity; only a hand-made log can hold it (fabric-ctl refuses a non-finite --timeout)
        line = {**sent("r1", 0, [A]), "timeout_s": float("inf")}
        rep = run([line, got("r1", A, "relay", 2), got("r1", A, "interweave", 5, who="agentd", verdict="no-waiter")])
        self.assertEqual(pair(rep, "r1", A)["cause"], "no-waiter")
        self.assertEqual(rep["malformed_timeout"], 1)

    def test_a_present_but_unusable_timeout_is_counted_and_said_an_absent_one_is_not(self):
        for bad in ("15", 0, -3, True, None):
            rep = run([{**sent("r1", 0, [A]), "timeout_s": bad}, got("r1", A, "relay", 2)])
            self.assertEqual(rep["malformed_timeout"], 1, bad)
            self.assertIn("1 request(s) have a `timeout_s` that is present but not", cp.render_markdown(rep))
        rep = run([sent("r1", 0, [A]), got("r1", A, "relay", 2)])
        self.assertEqual(rep["malformed_timeout"], 0)
        self.assertNotIn("timeout_s", cp.render_markdown(rep))

    def test_a_relay_only_pair_of_a_run_with_no_session_is_no_session_without_an_agentd_line(self):
        none = {"t": iso(0), "who": "ctl", "carrier": "interweave", "kind": "request", "id": "r1", "from": OP, "op": "ping", "verdict": "no-session"}
        rep = run([{**sent("r1", 0, [A]), "timeout_s": 20}, got("r1", A, "relay", 2), none])
        self.assertEqual(pair(rep, "r1", A)["cause"], "no-session")
        self.assertEqual((rep["causes"]["no-session"], rep["causes"]["relay-only"]), (1, 0))

    def test_a_line_lacking_the_keys_it_is_read_by_is_skipped_never_dropped_unseen(self):
        no_to = {k: v for k, v in sent("r1", 0, [A]).items() if k != "to"}
        no_from = {k: v for k, v in got("r1", A, "relay", 2).items() if k != "from"}
        no_to_agentd = {**no_from, "who": "agentd", "carrier": "interweave"}
        rep = run([no_to, no_from, no_to_agentd])
        self.assertEqual((rep["skipped"], rep["pairs"]), (3, []))

    def test_lines_lacking_who_kind_or_a_no_session_id_are_skipped_not_read_as_an_absence(self):
        relay = got("r1", A, "relay", 2)
        base = [{**sent("r1", 0, [A]), "timeout_s": 20}]
        no_id = {"t": iso(0), "who": "ctl", "carrier": "interweave", "kind": "request", "from": OP, "op": "ping", "verdict": "no-session"}
        for bad in ({k: v for k, v in relay.items() if k != "who"}, {k: v for k, v in relay.items() if k != "kind"}, no_id):
            self.assertEqual(run(base + [bad])["skipped"], 1, bad)

    def test_lines_whose_verdict_the_report_cannot_read_are_skipped_not_read_as_an_absence(self):
        base = [{**sent("r1", 0, [A]), "timeout_s": 20}, got("r1", A, "relay", 2)]
        for bad in ({**got("r1", B, "relay", 2), "verdict": None}, {**got("r1", B, "relay", 2), "verdict": "xx"},
                    {k: v for k, v in got("r1", B, "relay", 2).items() if k != "verdict"},
                    {**sent("r2", 0, [B]), "verdict": None}, {k: v for k, v in sent("r2", 0, [B]).items() if k != "verdict"},
                    {**got("r1", A, "interweave", 5, who="agentd"), "verdict": None}):
            self.assertEqual(run(base + [bad])["skipped"], 1, bad)

    def test_a_forged_from_line_with_no_kind_is_not_a_damaged_line(self):
        forged = {"t": iso(1), "who": "agentd", "carrier": "interweave", "kind": None, "id": "x", "from": A, "verdict": "forged-from"}
        self.assertEqual(run([sent("r1", 0, [A]), forged])["skipped"], 0)

    def test_an_integer_too_large_for_a_float_is_a_malformed_timeout_never_a_crash(self):
        line = {**sent("r1", 0, [A]), "timeout_s": 10 ** 400}
        rep = run([line, got("r1", A, "relay", 2)])
        self.assertEqual(rep["malformed_timeout"], 1)

    def test_a_fractional_timeout_is_read_in_whole_seconds(self):
        # a reply at real 10.6 s against --timeout 10.5 logs as 10 s: a miss, not late
        rep = late_case(10, timeout_s=10.5)
        self.assertEqual(pair(rep, "r1", A)["cause"], "no-waiter")


class Pairs(unittest.TestCase):
    def test_a_reply_by_both_carriers_is_both_and_each_carriers_latency_counts(self):
        rep = run([sent("r1", 10, [A]), got("r1", A, "relay", 12), got("r1", A, "interweave", 11)])
        p = pair(rep, "r1", A)
        self.assertEqual((p["outcome"], p["relay_s"], p["interweave_s"], p["carriers"]), ("both", 2.0, 1.0, ["interweave", "relay"]))
        self.assertEqual((rep["carriers"]["relay"]["delivered"], rep["carriers"]["interweave"]["delivered"]), (1, 1))
        self.assertEqual((rep["carriers"]["relay"]["missed"], rep["carriers"]["interweave"]["missed"]), (0, 0))

    def test_p50_and_p95_are_nearest_rank_per_carrier(self):
        rows = []
        for i in range(20):
            rows += [sent(f"r{i}", 0, [A]), got(f"r{i}", A, "interweave", i + 1), got(f"r{i}", A, "relay", 2 * i + 1)]
        rep = run(rows)
        self.assertEqual((rep["carriers"]["interweave"]["p50_s"], rep["carriers"]["interweave"]["p95_s"]), (10.0, 19.0))
        self.assertEqual((rep["carriers"]["relay"]["p50_s"], rep["carriers"]["relay"]["p95_s"]), (19.0, 37.0))
        self.assertIsNone(run([sent("x", 0, [A])])["carriers"]["relay"]["p50_s"], "no delivery is no latency, never 0")

    def test_the_first_copy_of_a_carrier_is_its_latency_and_a_part_row_is_no_second_delivery(self):
        rep = run([sent("r1", 0, [A]), got("r1", A, "interweave", 3), got("r1", A, "interweave", 9), got("r1", A, "relay", 4)])
        self.assertEqual(pair(rep, "r1", A)["interweave_s"], 3.0)
        self.assertEqual(rep["carriers"]["interweave"]["delivered"], 1)

    def test_every_addressee_of_a_request_is_a_pair_and_one_that_never_answered_is_a_timeout(self):
        rep = run([sent("r1", 0, [A, B]), got("r1", A, "relay", 1), got("r1", A, "interweave", 1)])
        p = pair(rep, "r1", B)
        self.assertEqual((p["outcome"], p["cause"], p["carriers"]), ("none", "timeout", []))
        self.assertEqual(rep["causes"]["timeout"], 1)
        self.assertEqual((rep["carriers"]["interweave"]["missed"], rep["carriers"]["relay"]["missed"]), (1, 1))

    def test_a_reply_only_the_relay_brought_is_relay_only_and_names_a_cause(self):
        rep = run([sent("r1", 0, [A]), got("r1", A, "relay", 1)])
        p = pair(rep, "r1", A)
        self.assertEqual((p["outcome"], p["cause"]), ("relay-only", "relay-only"))
        self.assertEqual(rep["carriers"]["interweave"]["missed"], 1)

    def test_no_waiter_is_the_cause_when_the_operators_agentd_routed_it_to_nobody(self):
        agentd = {**got("r1", OP, "interweave", 1, who="agentd", verdict="no-waiter")}
        rep = run([sent("r1", 0, [OP]), got("r1", OP, "relay", 1), agentd])
        self.assertEqual(pair(rep, "r1", OP)["cause"], "no-waiter")

    def test_a_reply_still_held_at_the_end_of_the_log_was_never_collected_and_is_a_no_waiter(self):
        held = got("r1", OP, "interweave", 0, who="agentd", verdict="held")
        rep = run([sent("r1", 0, [OP]), got("r1", OP, "relay", 1), held])
        self.assertEqual(pair(rep, "r1", OP)["cause"], "no-waiter")

    def test_an_unrecorded_reply_only_interweave_brought_is_no_relay_miss(self):
        rep = run([got("old", A, "interweave", 5)])
        self.assertEqual((rep["carriers"]["relay"]["missed"], pair(rep, "old", A)["outcome"]), (0, "interweave-only"))

    def test_a_held_reply_that_was_then_delivered_is_no_miss(self):
        rows = [sent("r1", 0, [OP]), got("r1", OP, "relay", 1), got("r1", OP, "interweave", 1),
                got("r1", OP, "interweave", 0, who="agentd", verdict="held"), got("r1", OP, "interweave", 1, who="agentd", verdict="ok")]
        rep = run(rows)
        self.assertEqual((pair(rep, "r1", OP)["outcome"], rep["causes"]["no-waiter"]), ("both", 0))

    def test_a_held_reply_that_agentd_also_delivered_is_no_no_waiter_even_when_ctl_was_shown_no_second_copy(self):
        # held then ok in agentd's log: the waiter came, so `held` is no cause. The outcome stays relay-only (ctl was
        # shown no InterWeave copy), which is the only way to reach the cause branch with both verdicts present.
        rows = [sent("r1", 0, [OP]), got("r1", OP, "relay", 1),
                got("r1", OP, "interweave", 0, who="agentd", verdict="held"), got("r1", OP, "interweave", 1, who="agentd", verdict="ok")]
        p = pair(run(rows), "r1", OP)
        self.assertEqual((p["outcome"], p["cause"]), ("relay-only", "relay-only"))
        # Positive control: the same log without the `ok` line is the no-waiter of the test above.
        self.assertEqual(pair(run(rows[:3]), "r1", OP)["cause"], "no-waiter")

    def test_a_refused_request_copy_is_no_cause_of_a_miss(self):
        # agentd answers on both carriers whichever copy it took, so a `seen` line says nothing of a lost reply. The line
        # is in the OPERATOR's file: compute reads no other account's file, so a line in alice's would prove nothing.
        seen = {"t": iso(1), "who": "agentd", "carrier": "interweave", "kind": "request", "id": "r1", "verdict": "seen"}
        rep = run([sent("r1", 0, [A]), got("r1", A, "relay", 2), seen])
        self.assertEqual(pair(rep, "r1", A)["cause"], "relay-only")

    def test_a_reply_only_interweave_brought_is_a_relay_miss_and_not_a_cause(self):
        rep = run([sent("r1", 0, [A]), got("r1", A, "interweave", 1)])
        self.assertEqual((pair(rep, "r1", A)["outcome"], rep["carriers"]["relay"]["missed"], rep["causes"]), ("interweave-only", 1, {c: 0 for c in cp.CAUSES}))

    def test_with_the_second_carrier_alone_the_relays_silence_is_no_miss(self):
        rep = run([sent("r1", 0, [A], "sent-alone"), got("r1", A, "interweave", 1)])
        self.assertEqual((rep["carriers"]["relay"]["missed"], rep["carriers"]["interweave"]["missed"]), (0, 0))
        rep = run([sent("r2", 0, [A], "sent-alone")])
        self.assertEqual((pair(rep, "r2", A)["cause"], rep["carriers"]["relay"]["missed"]), ("timeout", 0))

    def test_a_reply_with_no_request_line_is_a_pair_marked_unrecorded_and_counts_no_interweave_miss(self):
        rep = run([got("old", A, "relay", 5)])
        self.assertEqual((rep["unrecorded"], pair(rep, "old", A)["unrecorded"], rep["carriers"]["interweave"]["missed"]), (1, True, 0))
        self.assertEqual(sum(rep["causes"].values()), 0, "the causes never add up to more than the misses")


class Window(unittest.TestCase):
    ROWS = [sent("in", 100, [A]), got("in", A, "relay", 101), got("in", A, "interweave", 101),
            sent("early", 99, [A]), sent("edge", 200, [A])]

    def test_a_pair_belongs_by_its_request_time_in_a_window_open_at_the_end(self):
        rep = run(self.ROWS, window=(100, 200))
        self.assertEqual([p["id"] for p in rep["pairs"]], ["in"])

    def test_the_end_is_the_next_windows_start(self):
        self.assertEqual([p["id"] for p in run(self.ROWS, window=(200, 300))["pairs"]], ["edge"])


class Drill(unittest.TestCase):
    ROWS = [sent("d", 50, [A]), got("d", A, "relay", 51), sent("o", 150, [A]), got("o", A, "relay", 151), got("o", A, "interweave", 151)]

    def test_a_pair_inside_the_drill_is_listed_apart_and_counted_in_no_carriers_row(self):
        rep = run(self.ROWS, drill=(0, 100))
        self.assertEqual([(p["id"], p["outcome"]) for p in rep["in_drill"]], [("d", "relay-only")])
        self.assertEqual([p["id"] for p in rep["pairs"]], ["o"])
        self.assertEqual((rep["carriers"]["relay"]["delivered"], rep["carriers"]["interweave"]["missed"]), (1, 0))

    def test_a_drill_pair_the_second_carrier_still_delivered_says_both(self):
        rep = run([sent("d", 50, [A]), got("d", A, "relay", 51), got("d", A, "interweave", 51), sent("e", 60, [A]), got("e", A, "interweave", 61)], drill=(0, 100))
        self.assertEqual({p["id"]: p["outcome"] for p in rep["in_drill"]}, {"d": "both", "e": "interweave-only"})

    def test_the_drill_is_open_at_its_end_and_a_pair_with_no_copy_in_it_says_none(self):
        rep = run([sent("d", 100, [A]), sent("e", 99, [A])], drill=(0, 100))
        self.assertEqual([(p["id"], p["outcome"]) for p in rep["in_drill"]], [("e", "none")])
        self.assertEqual([p["id"] for p in rep["pairs"]], ["d"])

    def test_without_a_drill_nothing_is_marked(self):
        self.assertEqual(run(self.ROWS)["in_drill"], [])


class Files(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cp-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def write(self, name: str, lines: list) -> str:
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("".join((l if isinstance(l, str) else json.dumps(l)) + "\n" for l in lines))
        return path

    def test_lines_that_are_not_readable_are_counted_and_never_read_as_an_absence(self):
        path = self.write("a.jsonl", [sent("r1", 0, [A]), "{not json", json.dumps([1]), {"t": "yesterday"}, {"no": "t"}])
        rows, skipped = cp.read_lines(path)
        self.assertEqual((len(rows), skipped), (1, 4))

    def test_a_missing_file_is_refused_not_an_empty_log(self):
        with self.assertRaises(cp.InputError):
            cp.read_lines(os.path.join(self.dir, "nope.jsonl"))

    def test_the_operators_file_must_be_among_those_given_and_a_login_once(self):
        with self.assertRaises(cp.InputError):
            cp.compute({"alice": []}, "user", (0, 1))
        p = self.write("a.jsonl", [])
        with self.assertRaises(cp.InputError):
            cp.parse_files([f"user={p}", f"user={p}"])
        with self.assertRaises(cp.InputError):
            cp.parse_files([p])

    def cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = carrier_main.main(["control-parity", *args])
        return rc, out.getvalue(), err.getvalue()

    def test_the_command_prints_the_report_and_the_json_form_and_refuses_bad_input_with_a_line(self):
        path = self.write("u.jsonl", [sent("r1", 5, [A]), got("r1", A, "relay", 6)])
        base = ["--window", iso(0), iso(100), "--operator", "user", "--arrivals", f"user={path}"]
        rc, out, err = self.cli(*base)
        self.assertEqual(rc, 0, err)
        self.assertIn("| interweave | 0 | 1 |", out)
        self.assertIn("relay-only", out)
        rc, out, _ = self.cli(*base, "--json")
        self.assertEqual((rc, json.loads(out)["causes"]["relay-only"]), (0, 1))
        rc, out, err = self.cli("--window", iso(100), iso(0), "--operator", "user", "--arrivals", f"user={path}")
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("control-parity:", err)
        self.assertNotIn("Traceback", err)
        rc, _, err = self.cli("--window", iso(0), iso(1), "--operator", "user", "--arrivals", f"user={self.dir}/nope")
        self.assertEqual(rc, 2)
        self.assertIn("nope", err)

    def test_the_drill_is_marked_in_the_markdown(self):
        path = self.write("u.jsonl", [sent("d", 5, [A]), got("d", A, "relay", 6)])
        rc, out, _ = self.cli("--window", iso(0), iso(100), "--operator", "user", "--arrivals", f"user={path}", "--drill", iso(0), iso(10))
        self.assertEqual(rc, 0)
        self.assertIn("InterWeave-stop drill", out)
        self.assertIn("`d` → h/alice: relay", out)


if __name__ == "__main__":
    unittest.main()
