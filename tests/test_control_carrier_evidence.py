#!/usr/bin/env python3
"""Tests for the carrier's parity evidence, collected through the control plane (agent-fabric ADR-064 rule 11):
tools/fabric/control/carrier_evidence.py (what an account sends), evidence_collect.py (paging and filing), the
`interweave-evidence` verb of fabric-ctl, and `gzcoord-carrier parity --collected` (what reads it).

The accounts' files are built here in the formats the carrier writes; the journal is a table with the columns the
evidence reads. Each case names what it would let through if its guard were gone."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
import time
import unittest
import unittest.mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
from control import agentd, carrier_evidence as ev, ctl, evidence_collect as ec, ops  # noqa: E402
from control.sign import ACTION_OPS  # noqa: E402
from gzcoord.carrier import arrivals, main as carrier_main, parity, record  # noqa: E402

T0 = 1_792_000_000
OP = "interweave-evidence"
BODY_TEXT = "message-body-9f3a"      # the marker no reply, row or file may ever hold


# The committed control_carrier may be "dual" (ADR-029 rule 18): an in-process fabric-ctl run would then append
# its fixture replies to the account's real control-arrivals.jsonl and dial its live agentd when this suite runs
# alone, outside tests/run.py's own pin (#583 F1). Each in-process ctl suite sets the carrier it means, this one the
# relay; test_run_control_carrier checks.
os.environ["FABRIC_CONTROL_CARRIER"] = "relay"


def iso(s: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(T0 + s))


def mid(sec: int, n: int = 0) -> str:
    h = f"{(T0 + sec) * 1000:012x}"
    return f"{h[:8]}-{h[8:]}-7000-8000-{n:012x}"


def arrival(m: str, who: str, carrier: str, sec: int, verdict: str = "ok", **more) -> dict:
    return {"mid": m, "addressee": who, "carrier": carrier, "t": iso(sec), "verdict": verdict, **more}


def request(section: str, since: int, until: int) -> dict:
    return {"id": "q", "op": OP, "from": "h/user", "args": {"section": section, "since": iso(since), "until": iso(until)}}


class Account(unittest.TestCase):
    """One account's state directory, as the carrier leaves it."""

    def setUp(self):
        self.state = tempfile.mkdtemp(prefix="evid-", dir=os.environ.get("TMPDIR"))
        self.addCleanup(shutil.rmtree, self.state, ignore_errors=True)
        os.makedirs(os.path.join(self.state, "interweave"))

    def arrivals(self, rows: list, torn: str = "") -> None:
        with open(os.path.join(self.state, "gzcoord-arrivals.jsonl"), "w", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(r) + "\n" for r in rows) + torn)

    def deliveries(self, queued: list[tuple], done: list[dict] = ()) -> None:
        """`queued`: (mid, to, seconds, events after it); the text of each is BODY_TEXT."""
        with open(os.path.join(self.state, "interweave", "deliveries.jsonl"), "w", encoding="utf-8") as fh:
            for m, to, sec, later in queued:
                fh.write(json.dumps({"e": "queued", "mid": m, "to": to, "tmids": ["t1"], "text": BODY_TEXT, "t": iso(sec), "enc": "plain"}) + "\n")
                for e in later:
                    fh.write(json.dumps({"e": e, "mid": m, "to": to, **({"code": "UnauthorizedPeer"} if e == "blocked" else {})}) + "\n")
        with open(os.path.join(self.state, "interweave", "delivered.jsonl"), "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(d) + "\n" for d in done)

    def journal(self, rows: list[tuple]) -> str:
        path = os.path.join(self.state, "episodic.db")
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE episodes (message_id TEXT, direction TEXT, content TEXT, metadata_json TEXT)")
        con.executemany("INSERT INTO episodes VALUES (?, ?, ?, ?)", rows)
        con.commit()
        con.close()
        return path

    def ask(self, section: str, since: int, until: int) -> dict:
        return ev.carrier_evidence(request(section, since, until), state=self.state)

    # ── a body never leaves ─────────────────────────────────────────
    def test_a_body_never_leaves(self):
        m = mid(5, 1)
        self.arrivals([arrival(m, "h/b", "interweave", 6, content=BODY_TEXT, text=BODY_TEXT, path="/home/x/.secret", body=BODY_TEXT)])
        self.deliveries([(m, "b", 5, ["posted"])], done=[{"mid": mid(1, 9), "to": "c", "enc": "plain", "queued": iso(1), "text": BODY_TEXT}])
        self.journal([(m, "inbound", BODY_TEXT, json.dumps({"TO-ROLE": "r", "NOTE": BODY_TEXT}))])
        for f in ("gzcoord-arrivals.jsonl", os.path.join("interweave", "deliveries.jsonl"), "episodic.db"):
            with open(os.path.join(self.state, f), "rb") as fh:
                self.assertIn(BODY_TEXT.encode(), fh.read(), f"positive control: {f} holds the marker")
        a, d = self.ask("arrivals", 0, 100), self.ask("deliveries", 0, 100)
        self.assertEqual((a["status"], len(a["rows"]), d["status"], len(d["rows"])), ("ok", 1, "ok", 2))
        for reply in (a, d):
            self.assertNotIn(BODY_TEXT, json.dumps(reply))
        self.assertEqual(set(a["rows"][0]), set(ev.ARRIVAL_KEYS), "an arrival row has the closed list of keys and no other")
        self.assertTrue(all(set(r) <= set(ev.DELIVERY_KEYS) for r in d["rows"]))
        self.assertEqual(a["kinds"], {m: "role"})

    def test_a_value_that_is_not_a_short_string_is_not_sent_as_one(self):
        m = mid(5, 1)
        self.arrivals([arrival(m, "h/b", "interweave", 6, verdict="ok"), {**arrival(mid(6, 2), "h/b", "interweave", 7), "verdict": {"nested": BODY_TEXT}},
                       arrival(mid(7, 3), "h/b", "interweave", 8, verdict="v" * 5000)])
        a = self.ask("arrivals", 0, 100)
        self.assertNotIn(BODY_TEXT, json.dumps(a))
        self.assertEqual(a["skipped"], 1, "a row whose verdict is no string is not a row, and is counted")
        self.assertEqual(max(len(r["verdict"]) for r in a["rows"]), ev.FIELD_MAX)

    # ── the window ──────────────────────────────────────────────────
    def test_the_window_bounds_the_lines_and_is_half_open(self):
        self.arrivals([arrival(mid(s, s), "h/b", "relay", s) for s in (9, 10, 11, 19, 20, 21)])
        got = [r["t"] for r in self.ask("arrivals", 10, 20)["rows"]]
        self.assertEqual(got, [iso(10), iso(11), iso(19)], "since is in, until is out")
        self.assertEqual(self.ask("arrivals", 100, 200)["rows"], [], "positive control: an empty window is an empty page")

    def test_a_torn_line_and_a_line_with_no_time_are_counted_not_sent(self):
        self.arrivals([arrival(mid(5, 1), "h/b", "relay", 5), {"mid": "x", "addressee": "h/b", "carrier": "relay", "t": "yesterday", "verdict": "ok"}],
                      torn='{"mid": "tor')
        a = self.ask("arrivals", 0, 100)
        self.assertEqual((len(a["rows"]), a["skipped"]), (1, 2))

    def test_no_log_is_an_empty_page_not_an_error(self):
        a = self.ask("arrivals", 0, 100)
        self.assertEqual((a["status"], a["rows"], a["next"], a["journal"]), ("ok", [], None, "absent"))

    def test_deliveries_are_windowed_by_when_they_were_queued_and_undated_ones_are_counted(self):
        self.deliveries([(mid(5, 1), "b", 5, ["posted", "receipt"]), (mid(50, 2), "b", 50, ["posted", "blocked"]), (mid(500, 3), "c", 500, [])],
                        done=[{"mid": mid(1, 8), "to": "c", "enc": "chunked", "queued": iso(8)}, {"mid": mid(1, 7), "to": "c", "enc": "plain"},
                              {"mid": mid(1, 6), "to": "c", "enc": "plain", "queued": iso(9), "abandoned": True, "by": "user"}])
        d = self.ask("deliveries", 0, 100)
        self.assertEqual([(r["mid"], r["state"]) for r in d["rows"]],
                         [(mid(5, 1), "done"), (mid(1, 8), "done"), (mid(1, 6), "abandoned"), (mid(50, 2), "blocked")])
        self.assertEqual(d["undated"], 1)
        self.assertEqual(d["rows"][-1]["code"], "UnauthorizedPeer")
        self.assertEqual({r["by"] for r in d["rows"] if "by" in r}, {"user"})

    # ── the journal ─────────────────────────────────────────────────
    def test_kinds_come_from_the_journal_for_the_pages_messages_only(self):
        a, b, c = mid(5, 1), mid(6, 2), mid(7, 3)
        self.arrivals([arrival(a, "h/b", "relay", 5), arrival(b, "h/b", "relay", 6), arrival(mid(8, 4), "h/b", "relay", 8)])
        self.journal([(a, "inbound", "x", json.dumps({"BROADCAST": "true"})), (b, "inbound", "x", json.dumps({"TO": "b"})),
                      (c, "inbound", "x", json.dumps({"TO-ROLE": "r"})), (a, "outbound", "x", json.dumps({"TO-ROLE": "r"})),
                      (mid(8, 4), "inbound", "x", "not json")])
        got = self.ask("arrivals", 0, 100)
        self.assertEqual((got["kinds"], got["journal"]), ({a: "broadcast", b: "direct"}, "ok"), "a header that cannot be read is no kind, never direct")

    def test_a_journal_that_cannot_be_read_is_said_and_no_kind_is_guessed(self):
        self.arrivals([arrival(mid(5, 1), "h/b", "relay", 5)])
        with open(os.path.join(self.state, "episodic.db"), "w") as fh:
            fh.write("this is not a database")
        got = self.ask("arrivals", 0, 100)
        self.assertEqual((got["kinds"], got["journal"]), ({}, "unreadable"))

    def test_the_journal_is_opened_read_only(self):
        self.arrivals([arrival(mid(5, 1), "h/b", "relay", 5)])
        path = self.journal([])
        before = os.stat(path).st_mtime_ns
        self.ask("arrivals", 0, 100)
        self.assertEqual(os.stat(path).st_mtime_ns, before)
        self.assertEqual(sorted(os.listdir(self.state)), ["episodic.db", "gzcoord-arrivals.jsonl", "interweave"], "nothing was left beside it")

    # ── the arguments ───────────────────────────────────────────────
    def test_the_arguments_are_a_closed_set(self):
        ok = {"section": "arrivals", "since": iso(0), "until": iso(10)}
        self.assertIsNone(ev.check_args(ok))
        for args, said in (({**ok, "path": "/etc/passwd"}, "no argument 'path'"), ({**ok, "section": "bodies"}, "section is one of"),
                           ({**ok, "since": "2026-10-26"}, "YYYY-MM-DDTHH:MM:SSZ"), ({**ok, "until": iso(0)}, "since is before until"),
                           ({**ok, "until": iso(-5)}, "since is before until"), ({**ok, "since": 5}, "YYYY-MM-DDTHH:MM:SSZ"),
                           ({"section": "arrivals"}, "YYYY-MM-DDTHH:MM:SSZ"), (None, "takes the arguments"), ([], "takes the arguments"),
                           ({**ok, "since": "2026-13-45T99:99:99Z"}, "YYYY-MM-DDTHH:MM:SSZ")):
            self.assertIn(said, ev.check_args(args) or "", args)
            self.assertEqual(ev.carrier_evidence({"args": args}, state=self.state)["status"], "refused", args)

    # ── paging ──────────────────────────────────────────────────────
    def page_all(self, section: str, since: int, until: int) -> tuple[list, int]:
        rows, pages, at = [], 0, iso(since)
        while at:
            r = ev.carrier_evidence({"args": {"section": section, "since": at, "until": iso(until)}}, state=self.state)
            self.assertEqual(r["status"], "ok", r)
            rows += r["rows"]
            pages += 1
            at = r["next"]
            self.assertLess(pages, 500, "paging ends")
        return rows, pages

    def test_a_window_larger_than_a_page_is_paged_whole_with_no_row_twice_or_lost(self):
        # Several rows share each second: a page may end only between seconds.
        rows = [arrival(mid(s, s * 10 + k), f"h/a{k}", "relay" if k % 2 else "interweave", s) for s in range(0, 60) for k in range(4)]
        self.arrivals(rows)
        with unittest.mock.patch.object(ev, "PAGE_BYTES", 1500):
            got, pages = self.page_all("arrivals", 0, 100)
        self.assertGreater(pages, 5, "positive control: the small page forced paging")
        self.assertEqual(sorted(json.dumps(r, sort_keys=True) for r in got), sorted(json.dumps(r, sort_keys=True) for r in rows))
        self.assertEqual([r["t"] for r in got], sorted(r["t"] for r in got))
        with unittest.mock.patch.object(ev, "PAGE_BYTES", 1500):
            first = ev.carrier_evidence(request("arrivals", 0, 100), state=self.state)
        self.assertEqual({r["t"] for r in first["rows"]} & {first["next"]}, set(), "the next page starts at a second the page did not touch")

    def test_a_reply_is_bounded_by_the_page_size(self):
        self.arrivals([arrival(mid(s, s), "h/a", "relay", s) for s in range(3000)])
        r = self.ask("arrivals", 0, 4000)
        self.assertIsNotNone(r["next"], "positive control: 3000 rows do not fit one page")
        self.assertLessEqual(len(json.dumps(r["rows"], separators=(",", ":"))), ev.PAGE_BYTES)

    def test_a_second_with_more_rows_than_a_page_is_refused_by_name(self):
        self.arrivals([arrival(mid(5, k), "h/a", "relay", 5) for k in range(40)])
        with unittest.mock.patch.object(ev, "PAGE_BYTES", 500):
            r = self.ask("arrivals", 0, 100)
        self.assertEqual(r["status"], "refused")
        self.assertIn(iso(5), r["reason"])

    def test_deliveries_page_by_the_same_rule(self):
        self.deliveries([(mid(s, s), "b", s, ["posted", "receipt"]) for s in range(40)])
        with unittest.mock.patch.object(ev, "PAGE_BYTES", 900):
            got, pages = self.page_all("deliveries", 0, 100)
        self.assertGreater(pages, 2)
        self.assertEqual(sorted(r["mid"] for r in got), sorted(mid(s, s) for s in range(40)))


class Wiring(unittest.TestCase):
    def test_the_op_is_a_signed_operator_op_and_not_public(self):
        self.assertIn(OP, ops.OPS)
        self.assertIn(OP, ACTION_OPS, "unsigned, a relay-token holder could write an operator's address and read who talks to whom")
        self.assertNotIn(OP, ops.PUBLIC_OPS)
        self.assertEqual(ctl.ACTION_OK[OP], ["ok"])
        self.assertEqual(ctl.VERB[OP].signed, "always")

    def test_the_daemon_answers_in_the_wires_reply_shape_and_refuses_a_bad_argument(self):
        state = tempfile.mkdtemp(prefix="evid-")
        self.addCleanup(shutil.rmtree, state, ignore_errors=True)
        with open(os.path.join(state, "gzcoord-arrivals.jsonl"), "w") as fh:
            fh.write(json.dumps(arrival(mid(5, 1), "h/b", "relay", 5)) + "\n")
        ctx = {"me": {"address": "h/a"}, "started": "2026-10-26T10:00:00.000Z", "carrier_evidence_opts": {"state": state}}
        r = agentd.answer(request("arrivals", 0, 100), ctx)
        self.assertEqual((r["op"], list(r["data"]), r["data"][OP]["status"], len(r["data"][OP]["rows"])), (OP, [OP, "agentd"], "ok", 1))
        bad = agentd.answer({"id": "q", "op": OP, "from": "h/user", "args": {"section": "arrivals", "since": iso(0), "until": iso(9), "path": "/"}}, ctx)
        self.assertEqual(bad["data"][OP]["status"], "refused")
        none = agentd.answer({"id": "q", "op": OP, "from": "h/user"}, ctx)
        self.assertEqual(none["data"][OP]["status"], "refused")


class Collect(unittest.TestCase):
    """The pages of several accounts put together, against the real account side."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="evcol-", dir=os.environ.get("TMPDIR"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.states: dict[str, str] = {}

    def account(self, login: str, arrivals: list, queued: list = ()) -> None:
        state = os.path.join(self.root, "state-" + login)
        os.makedirs(os.path.join(state, "interweave"))
        self.states[login] = state
        with open(os.path.join(state, "gzcoord-arrivals.jsonl"), "w") as fh:
            fh.writelines(json.dumps(a) + "\n" for a in arrivals)
        with open(os.path.join(state, "interweave", "deliveries.jsonl"), "w") as fh:
            for m, to, sec in queued:
                fh.write(json.dumps({"e": "queued", "mid": m, "to": to, "tmids": ["t"], "text": BODY_TEXT, "t": iso(sec), "enc": "plain"}) + "\n")

    def sender(self, silent=(), calls=None):
        def send(logins, section, since, until):
            if calls is not None:
                calls.append((tuple(logins), section, since))
            out = {}
            for login in logins:
                if login in silent:
                    out[login] = {"status": "no answer"}
                    continue
                out[login] = ev.carrier_evidence({"args": {"section": section, "since": since, "until": until}}, state=self.states[login])
            return out
        return send

    def test_every_page_of_every_account_is_collected_in_the_form_parity_reads(self):
        self.account("a", [arrival(mid(s, s), "h/a", "relay", s) for s in range(30)], [(mid(2, 2), "b", 2)])
        self.account("b", [arrival(mid(s, s), "h/b", "interweave", s) for s in range(5)])
        calls: list = []
        with unittest.mock.patch.object(ev, "PAGE_BYTES", 900):
            got = ec.collect(["a", "b"], iso(0), iso(100), self.sender(calls=calls))
        self.assertTrue(got["a"]["complete"] and got["b"]["complete"])
        self.assertEqual((len(got["a"]["arrivals"]), len(got["b"]["arrivals"]), len(got["a"]["deliveries"])), (30, 5, 1))
        self.assertGreater(got["a"]["pages"]["arrivals"], 2)
        self.assertEqual(got["b"]["pages"]["arrivals"], 1, "an account with nothing more is not asked again")
        self.assertEqual(calls[0][0], ("a", "b"), "the first round asks every account at once")
        self.assertEqual([c[0] for c in calls if c[1] == "arrivals"][1:][0], ("a",), "the later pages ask only the account that has more")
        first_delivery_window = [c[2] for c in calls if c[1] == "deliveries"][0]
        self.assertEqual(first_delivery_window, iso(-ev.LOOKBACK_S), "deliveries begin a lookback before the window")
        self.assertEqual([c[2] for c in calls if c[1] == "arrivals"][0], iso(-ev.LOOKBACK_S), "and so do the arrivals")

    def test_a_silent_account_is_incomplete_with_the_section_it_stopped_in_and_the_others_go_on(self):
        self.account("a", [arrival(mid(1, 1), "h/a", "relay", 1)])
        self.account("b", [arrival(mid(1, 2), "h/b", "relay", 1)])
        got = ec.collect(["a", "b"], iso(0), iso(100), self.sender(silent=("b",)))
        self.assertEqual((got["a"]["complete"], got["b"]["complete"]), (True, False))
        self.assertIn("arrivals: no answer", got["b"]["reason"])
        self.assertEqual(len(got["a"]["deliveries"]) + got["a"]["pages"]["deliveries"], 1, "a's deliveries were still asked for")

    def test_a_refusal_is_the_accounts_reason(self):
        self.account("a", [])
        got = ec.collect(["a"], iso(0), iso(100), lambda *a: {"a": {"status": "refused", "reason": "section is one of arrivals, deliveries"}})
        self.assertFalse(got["a"]["complete"])
        self.assertIn("section is one of", got["a"]["reason"])

    def test_a_cursor_that_does_not_advance_ends_the_account_instead_of_looping(self):
        self.account("a", [])
        for bad in (iso(0), "tomorrow", iso(500)):
            stuck2 = lambda logins, section, since, until, bad=bad: {"a": {"status": "ok", "rows": [], "next": bad, "kinds": {}, "journal": "ok"}}  # noqa: E731
            got = ec.collect(["a"], iso(0), iso(100), stuck2, max_pages=50)
            self.assertFalse(got["a"]["complete"], bad)
            self.assertIn("does not advance", got["a"]["reason"])
        tick = [0]

        def endless(logins, section, since, until):
            tick[0] += 1      # always one second further: it advances, so only the page bound stops it
            return {"a": {"status": "ok", "rows": [], "next": iso(tick[0]), "kinds": {}, "journal": "ok"}}
        got = ec.collect(["a"], iso(0), iso(10 ** 6), endless, max_pages=3)
        self.assertFalse(got["a"]["complete"])
        self.assertIn("more than 3 pages", got["a"]["reason"])

    def test_filing_is_private_whole_and_the_meta_comes_last(self):
        self.account("a", [arrival(mid(1, 1), "h/a", "interweave", 1)], [(mid(1, 1), "b", 1)])
        got = ec.collect(["a"], iso(0), iso(100), self.sender())
        out = os.path.join(self.root, "out")
        d = ec.write_dir(out, "a", got["a"], iso(0), iso(100))
        self.assertEqual(sorted(os.listdir(d)), ["arrivals.jsonl", "deliveries.jsonl", "kinds.json", "meta.json", "mirror.jsonl", "shown.jsonl"])
        self.assertEqual(stat.S_IMODE(os.stat(d).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(out).st_mode), 0o700)
        for f in os.listdir(d):
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(d, f)).st_mode), 0o600, f)
        for f in os.listdir(d):
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                self.assertNotIn(BODY_TEXT, fh.read(), f)
        with open(os.path.join(d, "meta.json"), encoding="utf-8") as fh:
            meta = json.load(fh)
        self.assertEqual((meta["complete"], meta["counts"], meta["login"]), (True, {"arrivals": 1, "deliveries": 1, "kinds": 0, "shown": 0, "mirror": 0}, "a"))
        # An interrupted rewrite leaves no meta.json: a reader refuses the directory instead of reading old rows under new counts.
        with unittest.mock.patch.object(ec, "_atomic", side_effect=[None, OSError("disk full")]):
            with self.assertRaises(OSError):
                ec.write_dir(out, "a", got["a"], iso(0), iso(100))
        self.assertFalse(os.path.exists(os.path.join(d, "meta.json")))
        self.assertEqual(ec.row_of("a", "h", got["a"], iso(0), iso(100), full=False)["interweaveEvidence"].keys() & {"arrivals", "deliveries", "kinds"}, set(),
                         "a filed collection prints counts, not rows")


class Findings(Collect):
    """The cases the first review (PR 390) found: each fails when its fix is removed."""

    def straddling(self):
        """alpha sent to beta a message made 10 s before the window closes; beta's interweave copy came 5 s before, a second one 5 s after."""
        m = mid(990, 1)
        self.beta_arrivals = [arrival(m, "h/beta", "interweave", 995), arrival(m, "h/beta", "interweave", 1005)]
        self.account("beta", self.beta_arrivals)
        self.account("alpha", [], [(m, "beta", 990)])
        with open(os.path.join(self.states["alpha"], "interweave", "deliveries.jsonl"), "a") as fh:
            fh.write(json.dumps({"e": "receipt", "mid": m, "to": "beta"}) + "\n")

    def parity_of(self, got: dict, window: tuple[float, float]):
        out = os.path.join(self.root, "dir")
        for login, acct in got.items():
            ec.write_dir(out, login, acct, iso(0), iso(1000))
        ec.write_manifest(out, list(got))
        return parity.load_collected(out, window)

    def test_a_copy_just_outside_the_window_still_counts_for_its_pair(self):
        self.straddling()
        got = ec.collect(["alpha", "beta"], iso(0), iso(1000), self.sender())
        w = (T0, T0 + 1000)
        arr, senders, kinds, _ = self.parity_of(got, w)
        collected = parity.compute(arr, senders, kinds, w, host="h")
        full = parity.compute(self.beta_arrivals, {"alpha": record.read_deliveries(os.path.join(self.states["alpha"], "interweave"))}, {}, w, host="h")
        self.assertEqual(full["carriers"]["interweave"], {"delivered": 1, "missed": 0, "duplicates": 1, "mismatch": 0}, "positive control: the full files show the copy beyond the edge")
        self.assertEqual(collected["carriers"], full["carriers"])

    def test_a_collection_without_the_margin_is_refused(self):
        self.straddling()
        got = ec.collect(["alpha", "beta"], iso(0), iso(1000), self.sender())
        out = os.path.join(self.root, "dir")
        for login, acct in got.items():
            ec.write_dir(out, login, acct, iso(0), iso(1000))
            path = os.path.join(out, login, "meta.json")
            with open(path, encoding="utf-8") as fh:
                meta = json.load(fh)
            meta["margin_s"] = 0
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(meta, fh)
        ec.write_manifest(out, list(got))
        with self.assertRaisesRegex(parity.CollectedError, "beyond the window's edges"):
            parity.load_collected(out, (T0, T0 + 1000))

    def test_a_silent_account_leaves_a_directory_that_refuses_the_report_and_a_stale_one_is_refused(self):
        self.account("alpha", [])
        self.account("beta", [])
        got = ec.collect(["alpha", "beta"], iso(0), iso(1000), self.sender(silent=("beta",)))
        out = os.path.join(self.root, "dir")
        for login, acct in got.items():
            ec.write_dir(out, login, acct, iso(0), iso(1000))
        ec.write_manifest(out, ["alpha", "beta"])
        self.assertTrue(os.path.isdir(os.path.join(out, "beta")))
        with self.assertRaisesRegex(parity.CollectedError, "beta: the collection is not complete"):
            parity.load_collected(out, (T0, T0 + 1000))
        os.makedirs(os.path.join(out, "gamma"))
        with self.assertRaisesRegex(parity.CollectedError, "stale or a missing account"):
            parity.load_collected(out, (T0, T0 + 1000))
        os.rmdir(os.path.join(out, "gamma"))
        with open(os.path.join(out, "collection.json"), "w") as fh:
            json.dump({"logins": [1, "alpha"]}, fh)
        with self.assertRaisesRegex(parity.CollectedError, "stale or a missing account"):
            parity.load_collected(out, (T0, T0 + 1000))
        os.unlink(os.path.join(out, "collection.json"))
        with self.assertRaisesRegex(parity.CollectedError, "collection.json cannot be read"):
            parity.load_collected(out, (T0, T0 + 1000))

    def test_a_refused_first_page_is_an_answer_with_its_reason_in_the_table(self):
        self.account("a", [])
        got = ec.collect(["a"], iso(0), iso(100), lambda *a: {"a": {"status": "refused", "reason": "more than 65536 bytes of rows share the second X"}})
        row = ec.row_of("a", "h", got["a"], iso(0), iso(100), full=False)
        self.assertEqual(row["status"], "ok")
        line = ctl.table(OP, [row]).split("\n")[1]
        self.assertRegex(line, r"^a +incomplete ")
        self.assertIn("share the second X", line)
        silent = ec.collect(["a"], iso(0), iso(100), lambda *a: {"a": {"status": "no answer"}})
        self.assertEqual(ec.row_of("a", "h", silent["a"], iso(0), iso(100), full=False)["status"], "no answer", "positive control")

    def test_a_reply_at_the_page_bound_fits_the_relays_message_limit(self):
        state = os.path.join(self.root, "full")
        os.makedirs(state)
        rows = [arrival(mid(s // 4, s), f"h/agent-{s % 7}", "interweave" if s % 2 else "relay", s // 4, verdict="mismatch") for s in range(6000)]
        with open(os.path.join(state, "gzcoord-arrivals.jsonl"), "w") as fh:
            fh.writelines(json.dumps(r) + "\n" for r in rows)
        con = sqlite3.connect(os.path.join(state, "episodic.db"))
        con.execute("CREATE TABLE episodes (message_id TEXT, direction TEXT, content TEXT, metadata_json TEXT)")
        con.executemany("INSERT INTO episodes VALUES (?, 'inbound', 'x', ?)", [(r["mid"], json.dumps({"TO-ROLE": "r"})) for r in rows])
        con.commit()
        con.close()
        ctx = {"me": {"address": "h/a"}, "started": "2026-10-26T10:00:00.000Z", "carrier_evidence_opts": {"state": state}}
        reply = agentd.answer(request("arrivals", 0, 100000), ctx)
        self.assertIsNotNone(reply["data"][OP]["next"], "positive control: the page is full")
        posted = json.dumps({"channel": "c", "sender": "h/a", "content": json.dumps(reply)})
        self.assertLess(len(posted.encode()), 128 * 1024)

    def test_a_section_run_sends_one_request_and_collects_nothing(self):
        reg_dir = tempfile.mkdtemp(prefix="evreg-")
        self.addCleanup(shutil.rmtree, reg_dir, ignore_errors=True)
        reg = os.path.join(reg_dir, "registry.json")
        with open(reg, "w") as fh:
            json.dump({"hosts": {"h": {"operator": "user"}}, "placement": {"a": "h"}}, fh)
        sent: list = []

        def call(path, **kw):
            if path == "/api/send":
                sent.append(json.loads(json.loads(kw["body"])["content"]))
                return {"id": "x1"}
            return {"messages": []}
        clock = iter(range(0, 10 ** 6, 2))
        lines: list = []
        with unittest.mock.patch.object(ec, "collect", side_effect=AssertionError("a --section run collects nothing")), \
                unittest.mock.patch.object(ctl, "signing_key", lambda *a, **k: {"key": "k"}), \
                unittest.mock.patch.object(ctl, "sign_request", lambda r, k: r):
            rc = ctl.main(["a", OP, "--json", "--timeout", "3", "--section", "arrivals", "--since", iso(0), "--until", iso(100)],
                          registry=reg, call=call, who={"host": "h", "agent": "user"}, token="t", out=lines.append, err=lines.append,
                          sleep=lambda s: None, now=lambda: next(clock))
        self.assertEqual(rc, 1, "the account did not answer")
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["args"], {"section": "arrivals", "since": iso(0), "until": iso(100)})

    def test_an_absent_journal_is_said_as_absent(self):
        rep = parity.compute([], {}, {}, (T0, T0 + 10))
        rep["accounts"] = {"alpha": "absent", "beta": "unreadable", "gamma": "ok"}
        text = parity.render_markdown(rep)
        self.assertIn("The journal is absent on alpha", text)
        self.assertIn("further apart than that across an edge may show a miss", text, "the bound of the margin is in the report")
        self.assertIn("The journal could not be read on beta", text)
        self.assertNotIn("gamma:", text.split("Collected from")[1].split("Framing")[0].replace("gamma\n", ""))


class Operator(unittest.TestCase):
    ARGS = ["--since", "2026-10-26T05:20:00Z", "--until", "2026-10-27T05:20:00Z"]

    def test_the_verb_needs_a_window_and_refuses_the_options_of_other_verbs(self):
        a = ctl.parse_args(["all", OP, *self.ARGS])
        self.assertEqual((a["op"], a["since"], a["until"], a.get("section"), a["timeout"]), (OP, "2026-10-26T05:20:00Z", "2026-10-27T05:20:00Z", None, ev.EVIDENCE_BUDGET_S))
        for argv, said in ((["all", OP], "takes --since T and --until T"), (["all", OP, "--since", "2026-10-26T05:20:00Z"], "takes --since T and --until T"),
                           (["all", OP, "--since", "yesterday", "--until", "2026-10-27T05:20:00Z"], "--since takes YYYY"),
                           (["all", OP, "--since", "2026-10-27T05:20:00Z", "--until", "2026-10-26T05:20:00Z"], "--since is before --until"),
                           (["all", OP, *self.ARGS, "--section", "bodies"], "--section is one of"),
                           (["all", OP, *self.ARGS, "--section", "arrivals", "--out", "d"], "does not go with --section"),
                           (["all", "ping", *self.ARGS], "go with interweave-evidence only"), (["all", "interweave", "--section", "arrivals"], "go with interweave-evidence only")):
            with self.assertRaises(ctl.CtlError, msg=argv) as cm:
                ctl.parse_args(argv)
            self.assertIn(said, str(cm.exception))

    def test_the_request_is_signed_and_carries_the_section_and_the_window_only(self):
        a = ctl.parse_args(["all", OP, *self.ARGS, "--section", "deliveries"])
        req = ctl.build_request(a, id="i", from_="h/user", to="*", cfg={"ttl_s": 30})
        self.assertEqual(req["args"], {"section": "deliveries", "since": "2026-10-26T05:20:00Z", "until": "2026-10-27T05:20:00Z"})
        self.assertIn(req["op"], ACTION_OPS)
        self.assertEqual(req["ttl_s"], ev.EVIDENCE_BUDGET_S)

    def test_the_usage_and_help_say_it_is_signed_and_paged(self):
        self.assertIn(f"{OP} --since T --until T [--out <dir>]", ctl.USAGE)
        text = ctl.render_help(OP)
        self.assertIn("--section S", text)
        self.assertIn("signed", text)

    def page(self, rows, nxt=None, **more):
        return {"status": "ok", "rows": rows, "next": nxt, **more}

    def test_the_verb_pages_through_its_own_single_page_calls_and_files_the_result(self):
        a1, a2 = arrival(mid(1, 1), "h/a", "relay", 1), arrival(mid(2, 2), "h/a", "interweave", 2)
        # The second arrivals page: the fake answers by `since`.
        pages = {True: self.page([a1], iso(2), kinds={mid(1, 1): "direct"}, journal="ok", skipped=0),
                 False: self.page([a2], None, kinds={mid(2, 2): "role"}, journal="ok", skipped=0)}
        out = os.path.join(tempfile.mkdtemp(prefix="evout-"), "d")
        self.addCleanup(shutil.rmtree, os.path.dirname(out), ignore_errors=True)

        def canned_by_since(argv_):
            since = argv_[argv_.index("--since") + 1]
            return pages[since < iso(2)] if "arrivals" in argv_ else self.page([], undated=0)
        rc, lines, seen = self.run_pages(canned_by_since, ["a", "b"], ["all", OP, "--since", iso(0), "--until", iso(100), "--out", out])
        self.assertEqual(rc, 1, "b never answered: the run is not a success")
        table = "\n".join(lines)
        self.assertRegex(table, r"(?m)^a +ok +2 +0 +2 ")
        self.assertRegex(table, r"(?m)^b +no answer")
        d = os.path.join(out, "a")
        def read(name):
            with open(os.path.join(d, name), encoding="utf-8") as fh:
                return fh.read()
        self.assertEqual([json.loads(x)["mid"] for x in read("arrivals.jsonl").splitlines()], [mid(1, 1), mid(2, 2)])
        self.assertEqual(json.loads(read("kinds.json")), {mid(1, 1): "direct", mid(2, 2): "role"})
        with open(os.path.join(out, "b", "meta.json"), encoding="utf-8") as fh:
            meta_b = json.load(fh)
        self.assertEqual(meta_b["complete"], False, "an account that never answered has a directory that says so")
        with open(os.path.join(out, "collection.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"logins": ["a", "b"]})

    def run_pages(self, answer, logins, argv):
        reg_dir = tempfile.mkdtemp(prefix="evreg-")
        self.addCleanup(shutil.rmtree, reg_dir, ignore_errors=True)
        reg = os.path.join(reg_dir, "registry.json")
        with open(reg, "w") as fh:
            json.dump({"hosts": {"h": {"operator": "user"}}, "placement": {"a": "h", "b": "h"}}, fh)
        real = ctl.main
        seen: list = []

        def page_main(argv_, **kw):
            if "--section" not in argv_:
                return real(argv_, **kw)
            seen.append(argv_)
            for login in [w for w in argv_ if w in ("a", "b")]:
                row = answer(argv_) if login == "a" else None
                kw["out"](json.dumps({"account": login, "host": "h", "status": "ok", "interweaveEvidence": row} if row else {"account": login, "host": "h", "status": "no answer"}))
            return 0
        lines: list[str] = []
        with unittest.mock.patch.object(ctl, "main", page_main):
            rc = real(argv, registry=reg, who={"host": "h", "agent": "user"}, token="t", out=lines.append, err=lines.append)
        return rc, lines, seen

    def test_json_prints_the_whole_collection_in_the_form_parity_reads(self):
        a1 = arrival(mid(1, 1), "h/a", "relay", 1)
        rc, lines, seen = self.run_pages(lambda argv: self.page([a1], None, kinds={mid(1, 1): "direct"}, journal="ok", skipped=0) if "arrivals" in argv else self.page([], undated=0),
                                         ["a"], ["a", OP, "--json", "--since", iso(0), "--until", iso(100)])
        self.assertEqual(rc, 0)
        row = json.loads(lines[0])
        body = row["interweaveEvidence"]
        self.assertEqual((row["account"], body["complete"], body["arrivals"], body["kinds"], body["counts"]),
                         ("a", True, [a1], {mid(1, 1): "direct"}, {"arrivals": 1, "deliveries": 0, "kinds": 1, "shown": 0, "mirror": 0}))
        self.assertEqual(seen[0][seen[0].index("--timeout") + 1], str(ev.EVIDENCE_BUDGET_S))

    def test_one_page_with_a_section_is_sent_as_one_signed_request_and_not_collected(self):
        with unittest.mock.patch.object(ec, "collect", side_effect=AssertionError("a --section run collects nothing")):
            args = ctl.parse_args(["a", OP, *self.ARGS, "--section", "arrivals"])
        self.assertEqual(args["section"], "arrivals")


class Parity(unittest.TestCase):
    """`gzcoord-carrier parity --collected` against the report the three-argument form computes."""

    W = (T0, T0 + 1000)

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="evpar-", dir=os.environ.get("TMPDIR"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        m1, m2 = mid(10, 1), mid(20, 2)
        self.arr = {"beta": [arrival(m1, "h/beta", "relay", 11), arrival(m1, "h/beta", "interweave", 11), arrival(m2, "h/beta", "relay", 21)], "alpha": []}
        self.dels = {"alpha": [{"mid": m1, "to": "beta", "enc": "plain", "queued": iso(10), "state": "done"},
                               {"mid": m2, "to": "beta", "enc": "compressed", "queued": iso(20), "state": "blocked", "code": "UnauthorizedPeer"}], "beta": []}
        self.kinds = {"beta": {m1: "direct", m2: "role"}, "alpha": {}}

    def acct(self, login, **over):
        a = {"arrivals": self.arr[login], "deliveries": self.dels[login], "kinds": self.kinds[login], "complete": True, "reason": None, "journal": "ok",
             "shown": [], "relay_outage": {"complete": True, "reason": None},
             "mirror": [], "mirror_log": {"complete": True, "reason": None, "skipped": 0}, "since": iso(-100), "until": iso(2000), "margin_s": parity.MARGIN_S, "pages": {"arrivals": 1, "deliveries": 1}, "skipped": 0, "undated": 0}
        a.update(over)
        a["counts"] = over.get("counts", {"arrivals": len(a["arrivals"]), "deliveries": len(a["deliveries"]), "kinds": len(a["kinds"]),
                                                       "shown": len(a["shown"]), "mirror": len(a["mirror"])})
        return a

    def filed(self, **over) -> str:
        out = os.path.join(self.root, "dir")
        for login in ("alpha", "beta"):
            ec.write_dir(out, login, self.acct(login, **over.get(login, {})), over.get(login, {}).get("since", iso(-100)), over.get(login, {}).get("until", iso(2000)))
        ec.write_manifest(out, ["alpha", "beta"])
        return out

    def jsonl(self, **over) -> str:
        path = os.path.join(self.root, "all.jsonl")
        with open(path, "w") as fh:
            for login in ("alpha", "beta"):
                fh.write(json.dumps({"account": login, "host": "h", "status": "ok", "interweaveEvidence": self.acct(login, **over.get(login, {}))}) + "\n")
        return path

    def direct(self) -> dict:
        senders = {"alpha": self.dels["alpha"], "beta": []}
        return parity.compute(self.arr["beta"], senders, self.kinds["beta"], self.W, host="h")

    def report(self, path: str, *more: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = carrier_main.main(["parity", "--window", iso(0), iso(1000), "--collected", path, "--host", "h", *more])
        return rc, out.getvalue(), err.getvalue()

    def test_both_collected_forms_give_the_report_of_the_files_themselves(self):
        want = self.direct()
        for path in (self.filed(), self.jsonl()):
            rc, out, err = self.report(path)
            self.assertEqual((rc, err), (0, ""), path)
            rep = parity.compute(*parity.load_collected(path, self.W)[:3], self.W, host="h")
            self.assertEqual({k: rep[k] for k in ("pairs", "carriers", "missed", "stranded", "late", "messages")},
                             {k: want[k] for k in ("pairs", "carriers", "missed", "stranded", "late", "messages")})
            self.assertEqual(rep["carriers"]["interweave"]["missed"], 1, "positive control: the fixture has a miss to find")
            self.assertIn("UnauthorizedPeer", out)
            self.assertIn("Collected from 2 account(s)", out)

    def test_the_report_has_one_carrier_and_a_line_of_the_retired_relay_is_no_copy(self):
        rc, out, err = self.report(self.filed())
        self.assertEqual((rc, err), (0, ""))
        self.assertIn("| interweave | 1 | 1 | 0 | 0 |", out, "m1 delivered; m2 has only the relay's line, so the carrier missed it")
        self.assertNotIn("| relay |", out)
        self.assertNotIn("Rollback drill", out)
        self.assertEqual(list(parity.compute(*parity.load_collected(self.filed(), self.W)[:3], self.W, host="h")["carriers"]), ["interweave"])

    def test_a_collection_of_an_earlier_daemon_holds_sections_nothing_reads_and_they_are_ignored(self):
        # acks, backfills and watch were collected while the relay carried GZCoord. Their files, counts and meta records are filed as they were.
        old = {"acks": [{"mid": mid(10, 1), "addressee": "h/beta", "t": iso(12), "ok": True}], "backfills": [{"mid": "x", "outcome": "bogus"}],
               "watch": [{"t": "never"}], "backfill_log": {"complete": True, "reason": None, "skipped": 0, "send_rows": True},
               "watch_log": {"complete": True, "reason": None, "skipped": 0}}
        want = self.report(self.filed())
        self.assertEqual(want[0], 0)
        out_dir = self.filed()
        for login in ("alpha", "beta"):
            for name, rows in (("acks", old["acks"]), ("backfills", old["backfills"]), ("watch", old["watch"])):
                with open(os.path.join(out_dir, login, name + ".jsonl"), "w") as fh:
                    fh.write("".join(json.dumps(r) + "\n" for r in rows))
            with open(os.path.join(out_dir, login, "meta.json")) as fh:
                meta = json.load(fh)
            meta.update(backfill_log=old["backfill_log"], watch_log=old["watch_log"])
            meta["counts"].update(acks=1, backfills=1, watch=1)
            with open(os.path.join(out_dir, login, "meta.json"), "w") as fh:
                json.dump(meta, fh)
        self.assertEqual(self.report(out_dir), want)
        printed = self.report(self.jsonl(alpha=dict(old), beta=dict(old)))
        self.assertEqual(printed, want, "the printed form of the same collection")

    def test_a_miss_with_no_sender_record_names_the_senders_mirror_refusal(self):
        # m3: the relay delivered it to beta, no InterWeave copy and no delivery record anywhere, as when the carrier mirror refused the send.
        m3 = mid(30, 3)
        self.arr["beta"] = self.arr["beta"] + [arrival(m3, "h/beta", "relay", 31)]
        self.kinds["beta"][m3] = "direct"
        why = mrow(30, m3, "failed", "the InterWeave carrier refused (no roster)")
        for make in (self.filed, self.jsonl):
            rc, out, err = self.report(make(alpha={"mirror": [why]}, beta={"mirror": []}))
            self.assertEqual((rc, err), (0, ""), make.__name__)
            self.assertIn(f"{m3} to h/beta, interweave: the sender recorded no InterWeave delivery; alpha's mirror log: the carrier did not accept it "
                          f"(failed: the InterWeave carrier refused (no roster)) at {iso(30)}", out)
            self.assertNotIn("no account's mirror log holds a refusal", out.split(m3)[1].split("\n")[0])

    def test_a_primary_failure_leads_the_cause_and_a_row_without_the_field_is_a_mirror(self):
        m3 = mid(30, 3)
        self.arr["beta"] = self.arr["beta"] + [arrival(m3, "h/beta", "relay", 31)]
        self.kinds["beta"][m3] = "direct"
        why = {**mrow(30, m3, "no-answer", "the InterWeave carrier did not answer"), "as": "primary"}
        for make in (self.filed, self.jsonl):
            rc, out, err = self.report(make(alpha={"mirror": [why]}, beta={"mirror": []}))
            self.assertEqual((rc, err), (0, ""), make.__name__)
            line = out.split(m3)[1].split("\n")[0]
            self.assertIn(f"alpha's log: the carrier did not accept it at send (no-answer: the InterWeave carrier did not answer) at {iso(30)}; "
                          "the sender recorded no InterWeave delivery", line)
            self.assertLess(line.index("did not accept it at send"), line.index("recorded no InterWeave delivery"))
        old = mrow(30, m3, "failed", "refused")      # no `as`: the op from before the field
        self.assertNotIn("as", old)
        _, out, _ = self.report(self.filed(alpha={"mirror": [old]}, beta={"mirror": []}))
        line = out.split(m3)[1].split("\n")[0]
        self.assertIn("alpha's mirror log: the carrier did not accept it (failed: refused)", line)
        self.assertNotIn("at send", line)

    def test_a_miss_the_logs_do_not_explain_says_so_and_an_uncollected_log_is_not_no_refusal(self):
        m3 = mid(30, 3)
        self.arr["beta"] = self.arr["beta"] + [arrival(m3, "h/beta", "relay", 31)]
        self.kinds["beta"][m3] = "direct"
        _, out, _ = self.report(self.filed(alpha={"mirror": []}, beta={"mirror": []}))
        self.assertIn("no account's mirror log holds a refusal for it", out)
        out_dir = self.filed(alpha={"mirror": []}, beta={"mirror": []})
        os.unlink(os.path.join(out_dir, "alpha", "mirror.jsonl"))      # a collection from before the log
        with open(os.path.join(out_dir, "alpha", "meta.json")) as fh:
            meta = json.load(fh)
        meta["mirror_log"] = {"complete": False, "reason": "mirror: no answer", "skipped": 0}
        meta["counts"].pop("mirror")
        with open(os.path.join(out_dir, "alpha", "meta.json"), "w") as fh:
            json.dump(meta, fh)
        _, out, _ = self.report(out_dir)
        self.assertIn("the mirror log was not collected from 1 account(s)", out)
        self.assertNotIn("no account's mirror log holds a refusal", out)
        self.assertIn("The mirror-refusal log was not collected whole from alpha", out)

    def test_the_span_comes_from_the_latest_collected_since_less_the_margin(self):
        out = self.filed(alpha={"mirror": []}, beta={"mirror": [], "since": iso(-50)})
        self.assertEqual(parity.load_mirror(out)["began"], T0 - 50 - parity.MARGIN_S, "the later start of the two accounts")

    def test_a_mirror_row_that_is_not_what_the_op_sends_is_refused(self):
        out_dir = self.filed(alpha={"mirror": [mrow(30)]}, beta={"mirror": []})
        with open(os.path.join(out_dir, "alpha", "mirror.jsonl"), "w") as fh:
            fh.write(json.dumps({**mrow(30), "outcome": "bored"}) + "\n")
        rc, _, err = self.report(out_dir)
        self.assertEqual(rc, 2)
        self.assertIn("alpha: a mirror log row is not", err)
        for bad in ("bystander", None):       # a role the writer does not write: refused, with the field named
            with open(os.path.join(out_dir, "alpha", "mirror.jsonl"), "w") as fh:
                fh.write(json.dumps({**mrow(30), "as": bad}) + "\n")
            rc, _, err = self.report(out_dir)
            self.assertEqual(rc, 2, bad)
            self.assertIn("as: primary|mirror", err)

    def test_an_incomplete_account_refuses_the_whole_report(self):
        for make in (self.filed, self.jsonl):
            rc, out, err = self.report(make(beta={"complete": False, "reason": "arrivals: no answer"}))
            self.assertEqual((rc, out), (2, ""), make.__name__)
            self.assertIn("beta: the collection is not complete (arrivals: no answer)", err)

    def test_a_collection_that_does_not_cover_the_window_is_refused(self):
        for make in (self.filed, self.jsonl):
            for over in ({"since": iso(5)}, {"until": iso(900)}):
                rc, _, err = self.report(make(alpha=over))
                self.assertEqual(rc, 2, (make.__name__, over))
                self.assertIn("does not cover the report's window", err)

    def test_files_cut_short_or_edited_are_refused_by_their_counts(self):
        out = self.filed()
        with open(os.path.join(out, "beta", "arrivals.jsonl"), "w") as fh:
            fh.write(json.dumps(self.arr["beta"][0]) + "\n")
        rc, _, err = self.report(out)
        self.assertEqual(rc, 2)
        self.assertIn("beta: the files do not hold what the collection counted", err)

    def test_a_directory_with_no_meta_is_a_run_that_stopped(self):
        out = self.filed()
        os.unlink(os.path.join(out, "alpha", "meta.json"))
        rc, _, err = self.report(out)
        self.assertEqual(rc, 2)
        self.assertIn("alpha: cannot read its collection", err)

    def test_a_row_with_a_key_the_op_does_not_send_is_refused_so_a_body_cannot_ride_in(self):
        bad = dict(self.arr["beta"][0], content="x")
        rc, _, err = self.report(self.jsonl(beta={"arrivals": [bad, *self.arr["beta"][1:]]}))
        self.assertEqual(rc, 2)
        self.assertIn("carries a key the op does not send (content)", err)
        rc, _, err = self.report(self.jsonl(beta={"arrivals": [dict(self.arr["beta"][0], carrier="smoke-signal"), *self.arr["beta"][1:]]}))
        self.assertIn("names the carrier", err)

    def test_two_accounts_that_disagree_on_a_kind_are_refused(self):
        m = mid(10, 1)
        rc, _, err = self.report(self.jsonl(alpha={"kinds": {m: "broadcast"}, "counts": {"arrivals": 0, "deliveries": 2, "kinds": 1}}))
        self.assertEqual(rc, 2)
        self.assertIn("differs from another account's", err)

    def test_an_account_whose_journal_was_unreadable_is_named_in_the_report(self):
        rc, out, _ = self.report(self.jsonl(beta={"journal": "unreadable"}))
        self.assertEqual(rc, 0)
        self.assertIn("The journal could not be read on beta", out)

    def test_a_json_file_printed_without_its_rows_is_refused_with_the_way_out(self):
        path = os.path.join(self.root, "counts.jsonl")
        with open(path, "w") as fh:
            fh.write(json.dumps({"account": "a", "status": "ok", "interweaveEvidence": {"complete": True, "counts": {}}}) + "\n")
        rc, _, err = self.report(path)
        self.assertEqual(rc, 2)
        self.assertIn("was it printed with --out?", err)

    def test_the_old_form_still_works_and_the_two_forms_do_not_mix(self):
        rc, _, err = self.report(self.filed(), "--arrivals", "x")
        self.assertEqual(rc, 1)
        self.assertIn("does not go with", err)
        out, err_ = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err_):
            rc = carrier_main.main(["parity", "--window", iso(0), iso(1000)])
        self.assertEqual(rc, 1)
        self.assertIn("--collected PATH, or --arrivals and --senders", err_.getvalue())

    def test_the_old_form_reads_a_malformed_journal_row_as_unknown_still(self):
        db = os.path.join(self.root, "j.db")
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE episodes (message_id TEXT, direction TEXT, metadata_json TEXT)")
        con.executemany("INSERT INTO episodes VALUES (?, 'inbound', ?)", [("m1", json.dumps({"TO-ROLE": "r"})), ("m2", "not json"), ("m3", "[1]")])
        con.commit()
        con.close()
        self.assertEqual(parity.kinds_from_journal(db), {"m1": "role"})


class ShownAccount(Account):
    """The shown ledger's section (the carrier-outage drill's), as an account sends it."""

    def files(self, shown: list) -> None:
        with open(os.path.join(self.state, "gzcoord-shown.jsonl"), "w", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(r) + "\n" for r in shown))

    def test_shown_rows_leave_without_the_text_hash_and_with_their_flags(self):
        m = mid(5, 1)
        self.files([{"mid": m, "via": "interweave", "t": iso(10), "h": "hash-9f3a", "pending": True},
                    {"mid": m, "via": "interweave", "t": iso(10), "h": "hash-9f3a"},
                    {"mid": m, "via": "relay", "t": iso(20), "flagged": True, "pending": False, "extra": "x"}])
        r = ev.carrier_evidence(request("shown", 0, 100), state=self.state)
        self.assertEqual((r["status"], r["next"], r["skipped"]), ("ok", None, 0))
        self.assertEqual(r["rows"], [{"mid": m, "via": "interweave", "t": iso(10), "pending": True},
                                     {"mid": m, "via": "interweave", "t": iso(10)},
                                     {"mid": m, "via": "relay", "t": iso(20), "flagged": True}])
        self.assertNotIn("hash-9f3a", json.dumps(r))

    def test_a_mid_built_from_a_hash_of_the_text_does_not_leave_and_is_not_an_unreadable_line(self):
        self.files([{"mid": "sha256:" + "ab" * 32, "via": "relay", "t": iso(10)}, {"mid": mid(1), "via": "relay", "t": iso(11)}])
        r = ev.carrier_evidence(request("shown", 0, 100), state=self.state)
        self.assertEqual((len(r["rows"]), r["skipped"]), (1, 0))
        self.assertNotIn("sha256:", json.dumps(r))

    def test_the_drill_sections_are_windowed_and_a_missing_file_is_an_empty_page(self):
        r = ev.carrier_evidence(request("shown", 0, 100), state=self.state)
        self.assertEqual((r["status"], r["rows"]), ("ok", []))
        self.files([{"mid": mid(1), "via": "relay", "t": iso(99)}, {"mid": mid(2), "via": "relay", "t": iso(100)}])
        self.assertEqual([x["mid"] for x in ev.carrier_evidence(request("shown", 0, 100), state=self.state)["rows"]], [mid(1)])

    def test_the_drill_sections_reach_beyond_the_window_like_the_arrivals(self):
        self.assertEqual(ev.window_for("shown", iso(0), iso(100)), ev.window_for("arrivals", iso(0), iso(100)))
        self.assertEqual(ev.ALL_SECTIONS, ("arrivals", "deliveries", "shown", "mirror"), "the relay's acknowledgement, backfill and watch sections are not served")
        for gone in ("acks", "backfills", "watch"):
            self.assertIn("section is one of", ev.carrier_evidence(request(gone, 0, 100), state=self.state)["reason"], gone)


class ShownCollect(Collect):
    def drill_account(self, login: str, shown: list) -> None:
        self.account(login, [])
        with open(os.path.join(self.states[login], "gzcoord-shown.jsonl"), "w") as fh:
            fh.writelines(json.dumps(x) + "\n" for x in shown)

    def test_the_drill_sections_are_collected_and_filed(self):
        m = mid(1, 1)
        self.drill_account("a", [{"mid": m, "via": "interweave", "t": iso(5)}])
        got = ec.collect(["a"], iso(0), iso(100), self.sender())
        self.assertEqual((len(got["a"]["shown"]), got["a"]["relay_outage"]), (1, {"complete": True, "reason": None, "skipped": 0}))
        d = ec.write_dir(os.path.join(self.root, "out"), "a", got["a"], iso(0), iso(100))
        with open(os.path.join(d, "meta.json")) as fh:
            meta = json.load(fh)
        self.assertEqual((meta["counts"]["shown"], meta["relay_outage"]["complete"]), (1, True))

    def test_unreadable_drill_lines_are_carried_to_meta_and_a_drill_report_refuses_them(self):
        self.drill_account("a", [{"mid": mid(1, 1), "via": "interweave", "t": iso(5)}])
        with open(os.path.join(self.states["a"], "gzcoord-shown.jsonl"), "a") as fh:
            fh.write('{"mid": ')      # the watch died while writing a showing's line
        got = ec.collect(["a"], iso(0), iso(100), self.sender())
        self.assertEqual((got["a"]["complete"], got["a"]["relay_outage"]["complete"], got["a"]["relay_outage"]["skipped"]), (True, True, 1))
        # One unreadable line, several pages: each page repeats the file's count, which is not summed.
        self.drill_account("b", [{"mid": mid(s, s), "via": "interweave", "t": iso(s)} for s in range(30)])
        with open(os.path.join(self.states["b"], "gzcoord-shown.jsonl"), "a") as fh:
            fh.write('{"mid": ')
        with unittest.mock.patch.object(ev, "PAGE_BYTES", 900):
            got = ec.collect(["b"], iso(0), iso(100), self.sender())
        self.assertGreater(got["b"]["pages"]["shown"], 2)
        self.assertEqual(got["b"]["relay_outage"]["skipped"], 1)

    def test_a_table_row_says_when_the_shown_ledger_is_missing_and_the_report_stands(self):
        row = {"account": "a", "host": "h", "status": "ok", "interweaveEvidence": {
            "complete": True, "reason": None, "counts": {"arrivals": 1}, "journal": "ok", "relay_outage": {"complete": False, "reason": "shown: section is one of arrivals, deliveries"}}}
        self.assertIn("shown ledger: shown: section is one of", "\n".join(ctl._table_carrier_evidence([row])))

    def test_an_account_that_cannot_send_the_drill_sections_stays_complete_for_the_report_it_had(self):
        self.account("a", [arrival(mid(1, 1), "h/a", "relay", 1)])
        old = self.sender()

        def send(logins, section, since, until):
            if section in ev.DRILL_SECTIONS:      # a daemon from before the sections: the closed set refuses them
                return {x: {"status": "refused", "reason": f"section is one of {', '.join(ev.SECTIONS)}"} for x in logins}
            return old(logins, section, since, until)
        got = ec.collect(["a"], iso(0), iso(100), send)
        self.assertTrue(got["a"]["complete"], "the arrivals and deliveries are whole: the rollback report still stands")
        self.assertFalse(got["a"]["relay_outage"]["complete"])
        self.assertIn("shown: section is one of", got["a"]["relay_outage"]["reason"])
        self.assertEqual(got["a"]["shown"], [], "no rows are claimed for it")


class OutboxFixture(unittest.TestCase):
    """Collections of accounts built from what the carrier keeps, as the carrier-outage drill reads them: alpha sends to beta."""

    W = (T0, T0 + 1000)
    M, M2 = mid(110, 1), mid(120, 2)

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="evbf-", dir=os.environ.get("TMPDIR"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def acct(self, login: str, mids: tuple, sent: tuple | None = None) -> dict:
        """`login` received each of `mids` by the carrier and sent `sent` (alpha: the two messages of the class, to beta)."""
        sent = (self.M, self.M2) if sent is None and login == "alpha" else sent or ()
        dels = [{"mid": m, "to": "beta", "enc": "plain", "queued": iso(110), "state": "done"} for m in sent]
        arr = [arrival(m, f"h/{login}", "interweave", 111) for m in mids]
        return {"arrivals": arr, "deliveries": dels, "kinds": {}, "shown": [],
                "complete": True, "reason": None, "journal": "ok", "relay_outage": {"complete": True, "reason": None, "skipped": 0},
                "pages": {}, "skipped": 0, "undated": 0, "mirror": [], "mirror_log": {"complete": True, "reason": None, "skipped": 0},
                "counts": {"arrivals": len(arr), "deliveries": len(dels), "kinds": 0, "shown": 0, "mirror": 0}}

    def collect(self, accounts: dict) -> str:
        self.n = getattr(self, "n", 0) + 1
        out = os.path.join(self.root, f"dir{self.n}")      # one directory per collection: a leftover account is a refusal
        for login, acct in accounts.items():
            ec.write_dir(out, login, acct, iso(-100), iso(2000))
        ec.write_manifest(out, list(accounts))
        return out


def mrow(sec: int, m: str | None = None, outcome: str = "no-answer", reason: str = "the InterWeave carrier did not answer (timed out)") -> dict:
    return {"mid": m or mid(sec, 9), "t": iso(sec), "outcome": outcome, "reason": reason}


class MirrorAccount(ShownAccount):
    """gzcoord-mirror.jsonl, the sender's line for each send the carrier mirror did not accept (carrier/arrivals.MirrorLog)."""

    def log(self, rows: list, torn: str = "") -> None:
        with open(os.path.join(self.state, "gzcoord-mirror.jsonl"), "w", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(r) + "\n" for r in rows) + torn)

    def test_rows_leave_key_by_key_and_every_outcome_is_sent(self):
        rows = [mrow(10 + i, outcome=o) for i, o in enumerate(ev.MIRROR_OUTCOMES)]
        rows[0] = {**rows[0], "text": BODY_TEXT, "path": "/home/x/.secret"}
        self.log(rows)
        r = ev.carrier_evidence(request("mirror", 0, 100), state=self.state)
        self.assertEqual((r["status"], r["next"], r["skipped"]), ("ok", None, 0))
        self.assertEqual([x["outcome"] for x in r["rows"]], list(ev.MIRROR_OUTCOMES))
        self.assertEqual(set(r["rows"][0]), {"mid", "t", "outcome", "reason", "as"})
        self.assertEqual({x["as"] for x in r["rows"]}, {"mirror"}, "a line written before the field reads as a mirror's")
        self.assertNotIn(BODY_TEXT, json.dumps(r))
        self.assertNotIn(".secret", json.dumps(r))

    def test_a_failing_trim_says_the_line_was_written_and_a_mid_that_is_not_a_message_id_does_not_leave(self):
        path = os.path.join(self.state, "gzcoord-mirror.jsonl")
        log = arrivals.MirrorLog(path, iso_now=lambda: iso(5))
        err = io.StringIO()
        with unittest.mock.patch.object(arrivals.MirrorLog, "MAX_BYTES", 10), unittest.mock.patch.object(arrivals, "_rewrite", side_effect=OSError(28, "No space left")), \
                contextlib.redirect_stderr(err):
            log.append_refused(mid(1, 1), "absent", "x")
        self.assertIn("written but could not be trimmed (No space left)", err.getvalue())
        with open(path, encoding="utf-8") as fh:
            self.assertEqual([json.loads(x)["mid"] for x in fh], [mid(1, 1)])
        self.log([mrow(10, "/home/x/secret"), mrow(11, "alpha-0001"), mrow(12, "0190f000-0000-4000-8000-000000000000"), mrow(13)])
        r = ev.carrier_evidence(request("mirror", 0, 100), state=self.state)
        self.assertEqual((len(r["rows"]), r["skipped"]), (1, 0), "an id that is not a message id stays in the account and is not an unreadable line")

    def test_a_torn_line_and_a_line_of_the_wrong_shape_are_counted_and_not_sent(self):
        bad = [{**mrow(30), "outcome": "bored"}, {**mrow(30), "t": "yesterday"}, {**mrow(30), "reason": None}, {**mrow(30), "mid": ""},
               {"mid": mid(1, 1)}, [1]]
        self.log([mrow(31)] + bad)
        with open(os.path.join(self.state, "gzcoord-mirror.jsonl"), "a", encoding="utf-8") as fh:
            fh.write('{"mid": ')
        r = ev.carrier_evidence(request("mirror", 0, 100), state=self.state)
        self.assertEqual((len(r["rows"]), r["skipped"]), (1, len(bad) + 1))

    def test_the_section_is_windowed_and_a_missing_file_is_an_empty_page(self):
        r = ev.carrier_evidence(request("mirror", 0, 100), state=self.state)
        self.assertEqual((r["status"], r["rows"], r["skipped"]), ("ok", [], 0))
        self.log([mrow(99), mrow(100)])
        self.assertEqual([x["t"] for x in ev.carrier_evidence(request("mirror", 0, 100), state=self.state)["rows"]], [iso(99)])

    def test_it_is_a_section_the_op_knows_and_reaches_beyond_the_window(self):
        self.assertIsNone(ev.check_args({"section": "mirror", "since": iso(0), "until": iso(100)}))
        self.assertEqual(ev.window_for("mirror", iso(0), iso(100)), ev.window_for("arrivals", iso(0), iso(100)))

    def test_what_the_writer_writes_is_what_the_op_reads(self):
        # The writer's own class, not a hand-made line: a field the writer renames must break this.
        log = arrivals.MirrorLog(os.path.join(self.state, "gzcoord-mirror.jsonl"), iso_now=lambda: iso(50))
        for o in arrivals.MirrorLog.OUTCOMES:
            log.append_refused(mid(1, 1), o, "why\nit\tfailed")
        r = ev.carrier_evidence(request("mirror", 0, 100), state=self.state)
        self.assertEqual(([x["outcome"] for x in r["rows"]], r["skipped"]), (list(arrivals.MirrorLog.OUTCOMES), 0))
        self.assertEqual(r["rows"][0]["reason"], "why it failed")

    def test_a_primary_line_is_sent_as_primary_and_an_unknown_role_is_skipped(self):
        log = arrivals.MirrorLog(os.path.join(self.state, "gzcoord-mirror.jsonl"), iso_now=lambda: iso(50))
        log.append_refused(mid(1, 1), "failed", "x", "primary")
        log.append_refused(mid(1, 2), "failed", "x", "mirror")
        log.append_refused(mid(1, 3), "failed", "x")   # the carrier is the primary (W15): a line that names no role is its own
        with open(log.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({**mrow(51), "as": "bystander"}) + "\n")
        r = ev.carrier_evidence(request("mirror", 0, 100), state=self.state)
        self.assertEqual(([x["as"] for x in r["rows"]], r["skipped"]), (["primary", "mirror", "primary"], 1))

    def test_a_path_in_the_carriers_own_error_does_not_leave_the_account(self):
        self.log([mrow(10, reason="only 1 of 2 recipients recorded: beta: [Errno 13] Permission denied: '/home/x/.local/state/interweave/deliveries.jsonl'")])
        r = ev.carrier_evidence(request("mirror", 0, 100), state=self.state)
        self.assertNotIn("/home", json.dumps(r))
        self.assertIn("<path>", r["rows"][0]["reason"])
        self.assertIn("Permission denied", r["rows"][0]["reason"], "positive control: the rest of the words stay")

    def test_an_append_waits_for_the_lock_file_and_never_for_the_log_it_may_replace(self):
        # A trim replaces the log by rename: a lock on the log's own inode would let a second appender write into an unlinked file.
        import fcntl
        import threading
        path = os.path.join(self.state, "gzcoord-mirror.jsonl")
        log = arrivals.MirrorLog(path, iso_now=lambda: iso(1))
        held = os.open(path + ".lock", os.O_WRONLY | os.O_CREAT, 0o600)
        fcntl.flock(held, fcntl.LOCK_EX)
        t = threading.Thread(target=log.append_refused, args=(mid(1, 1), "absent", "x"))
        t.start()
        t.join(0.5)
        blocked = t.is_alive()
        fcntl.flock(held, fcntl.LOCK_UN)
        os.close(held)
        t.join(10)
        self.assertTrue(blocked, "the appender waits for the lock file")
        with open(path, encoding="utf-8") as fh:
            self.assertEqual([json.loads(x)["mid"] for x in fh], [mid(1, 1)])

    def test_the_log_is_bounded_and_keeps_the_newest_whole_lines(self):
        # A sender with no carrier at all writes a line per send: the file may not grow without end.
        path = os.path.join(self.state, "gzcoord-mirror.jsonl")
        tick = iter(range(1000))
        log = arrivals.MirrorLog(path, iso_now=lambda: iso(next(tick)))
        with unittest.mock.patch.object(arrivals.MirrorLog, "MAX_BYTES", 2000):
            for n in range(60):
                log.append_refused(mid(n, n), "absent", "no InterWeave carrier is running")
        with open(path, encoding="utf-8") as fh:
            kept = [json.loads(x) for x in fh]
        self.assertLessEqual(os.path.getsize(path), 2000 + 200)
        self.assertGreater(len(kept), 5)
        self.assertLess(len(kept), 60)
        self.assertEqual(kept[-1]["mid"], mid(59, 59), "the newest line survives")
        self.assertEqual([k["mid"] for k in kept], [mid(n, n) for n in range(60 - len(kept), 60)], "a contiguous newest run, whole lines")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)


class MirrorSpan(unittest.TestCase):
    def test_a_message_made_before_the_collected_span_does_not_say_no_refusal(self):
        old, new = mid(-5000, 1), mid(10, 2)
        arr = [arrival(old, "h/beta", "relay", 11), arrival(new, "h/beta", "relay", 12)]
        mirror = {"rows": {}, "uncollected": [], "began": T0 - 3700}
        rep = parity.compute(arr, {}, {}, (T0, T0 + 1000), host="h", mirror=mirror)
        said = {x["mid"]: x["cause"] for x in rep["missed"] if x["carrier"] == "interweave"}
        self.assertIn("made before the span the mirror logs were collected over", said[old])
        self.assertIn("no account's mirror log holds a refusal for it", said[new], "positive control: a message inside the span")


class MirrorCollect(Collect):
    def mirror_account(self, login: str, rows: list) -> None:
        self.account(login, [])
        with open(os.path.join(self.states[login], "gzcoord-mirror.jsonl"), "w") as fh:
            fh.writelines(json.dumps(x) + "\n" for x in rows)

    def test_the_log_is_collected_filed_counted_and_printed(self):
        self.mirror_account("a", [mrow(10), mrow(20, outcome="absent", reason="no InterWeave carrier is running")])
        got = ec.collect(["a"], iso(0), iso(100), self.sender())
        self.assertEqual((len(got["a"]["mirror"]), got["a"]["mirror_log"]), (2, {"complete": True, "reason": None, "skipped": 0}))
        d = ec.write_dir(os.path.join(self.root, "out"), "a", got["a"], iso(0), iso(100))
        with open(os.path.join(d, "mirror.jsonl")) as fh:
            filed = [json.loads(x) for x in fh]
        with open(os.path.join(d, "meta.json")) as fh:
            meta = json.load(fh)
        self.assertEqual((filed, meta["counts"]["mirror"], meta["mirror_log"]["complete"]), (got["a"]["mirror"], 2, True))
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(d, "mirror.jsonl")).st_mode), 0o600)
        body = ec.row_of("a", "h", got["a"], iso(0), iso(100), full=True)["interweaveEvidence"]
        self.assertEqual(body["mirror"], got["a"]["mirror"])

    def test_an_account_that_cannot_send_the_section_stays_complete_and_is_not_filed_as_having_none(self):
        self.account("a", [arrival(mid(1, 1), "h/a", "relay", 1)])
        old = self.sender()

        def send(logins, section, since, until):
            if section == "mirror":      # a daemon from before the section: the closed set refuses it
                return {x: {"status": "refused", "reason": "section is one of arrivals"} for x in logins}
            return old(logins, section, since, until)
        got = ec.collect(["a"], iso(0), iso(100), send)
        self.assertTrue(got["a"]["complete"])
        self.assertFalse(got["a"]["mirror_log"]["complete"])
        self.assertIn("mirror: section is one of", got["a"]["mirror_log"]["reason"])
        d = ec.write_dir(os.path.join(self.root, "out"), "a", got["a"], iso(0), iso(100))
        self.assertFalse(os.path.exists(os.path.join(d, "mirror.jsonl")), "an absent log is not an empty one")
        self.assertNotIn("mirror", ec.row_of("a", "h", got["a"], iso(0), iso(100), full=True)["interweaveEvidence"])

    def test_the_table_says_when_only_the_mirror_log_is_missing(self):
        row = {"account": "a", "host": "h", "status": "ok", "interweaveEvidence": {
            "complete": True, "reason": None, "counts": {"arrivals": 1}, "journal": "ok", "relay_outage": {"complete": True},
            "mirror_log": {"complete": False, "reason": "mirror: section is one of arrivals"}}}
        self.assertIn("mirror log: mirror: section is one of", "\n".join(ctl._table_carrier_evidence([row])))


class CarrierDrill(OutboxFixture):
    """`parity --carrier-drill START END LOGIN` (gate 2): one account's carrier stopped for the window; what the senders' outboxes held is
    delivered by the carrier once after it (a second copy fails) and shown once. alpha sends to beta; the drill is [T0+100, T0+200)."""

    M3, M4 = mid(130, 3), mid(140, 4)

    def build(self, arrivals: dict, shown: list, sent: tuple | None = None, extra: dict | None = None) -> str:
        """`arrivals`: {mid: [(carrier, second)]} as beta received them; `shown`: beta's ledger lines; `sent`: what alpha recorded sending."""
        sent = (self.M, self.M2, self.M3, self.M4) if sent is None else sent
        alpha = self.acct("alpha", (), sent=sent)
        beta = self.acct("beta", ())
        beta["arrivals"] = [arrival(m, "h/beta", c, sec) for m, got in arrivals.items() for c, sec in got]
        beta["shown"] = shown
        beta["counts"].update(arrivals=len(beta["arrivals"]), shown=len(shown))
        return self.collect({"alpha": alpha, "beta": beta, **(extra or {})})

    def run_report(self, path: str, login: str = "beta", s: int = 100, e: int = 200) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = carrier_main.main(["parity", "--window", iso(0), iso(1000), "--collected", path, "--host", "h", "--carrier-drill", iso(s), iso(e), login])
        return rc, out.getvalue(), err.getvalue()

    @staticmethod
    def seen(m: str, n: int = 1, sec: int = 210, pending: bool = True) -> list:
        return [{"mid": m, "via": "interweave", "t": iso(sec), **({"pending": True} if pending else {})}, *[{"mid": m, "via": "interweave", "t": iso(sec)} for _ in range(n)]]

    def section(self, path: str, **kw) -> list[str]:
        out = self.run_report(path, **kw)[1]
        return out.split("## Carrier-outage drill")[1].splitlines()

    def test_every_pair_held_by_the_outbox_delivered_once_after_the_end_and_shown_once_holds(self):
        path = self.build({self.M: [("interweave", 210)], self.M2: [("interweave", 230)]}, self.seen(self.M) + self.seen(self.M2, sec=230), sent=(self.M, self.M2))
        rc, out, err = self.run_report(path)
        self.assertEqual((rc, err), (0, ""))
        lines = self.section(path)
        self.assertIn(f"of beta ({iso(100)} to {iso(200)}): every message held arrived once by the carrier and was shown once", lines[0])
        self.assertIn(f"- {self.M}: held by alpha's outbox (done); delivered after the window's end ({iso(210)}); 1 copy(ies); shown once", out)
        self.assertNotIn("FAILS", out.split("## Carrier-outage drill")[1])

    def test_a_pair_shown_twice_fails_and_says_how_often(self):
        path = self.build({self.M: [("interweave", 210)]}, self.seen(self.M, n=2))
        out = self.run_report(path)[1]
        self.assertIn("A PROPERTY FAILED", out)
        self.assertIn("shown 2 times -- FAILS", out)

    def test_a_pair_never_delivered_fails(self):
        path = self.build({self.M: [("interweave", 210)]}, self.seen(self.M))      # M2 was held and never arrived
        out = self.run_report(path)[1]
        self.assertIn("A PROPERTY FAILED", out)
        self.assertIn(f"- {self.M2}: held by alpha's outbox (done); never delivered by the report's end; 0 copy(ies); not shown -- FAILS", out)

    def test_a_second_copy_fails(self):
        path = self.build({self.M: [("interweave", 210), ("interweave", 260)]}, self.seen(self.M), sent=(self.M,))
        self.assertIn("2 copy(ies); shown once -- FAILS", self.run_report(path)[1])

    def test_a_copy_before_the_window_ended_or_no_outbox_row_means_the_pair_is_not_exercised(self):
        path = self.build({self.M: [("interweave", 150)], self.M2: [("interweave", 210)]}, self.seen(self.M, sec=150) + self.seen(self.M2), sent=(self.M,))
        out = self.run_report(path)[1]
        self.assertIn("a copy reached the account before the window ended, so the carrier did not hold it alone; it does not count", out)
        self.assertIn("no sender in the collection recorded a delivery to the account; it does not count", out)
        self.assertIn(": no message in the collection was held by a sender's outbox", out)

    def test_a_showing_cut_off_before_its_final_line_is_unsettled_and_a_failure_beats_it(self):
        pending = [{"mid": self.M, "via": "interweave", "t": iso(210), "pending": True}]
        path = self.build({self.M: [("interweave", 210)]}, pending, sent=(self.M,))
        out = self.run_report(path)[1]
        self.assertIn("UNSETTLED, none failed and 1 pair(s) cannot be told yet", out)
        self.assertIn("shown: unknown (a showing was interrupted) -- UNKNOWN", out)
        path = self.build({self.M: [("interweave", 210)]}, pending, sent=(self.M, self.M2))
        self.assertIn("A PROPERTY FAILED", self.run_report(path)[1])

    def test_pairs_to_another_login_or_made_outside_the_window_are_not_in_it(self):
        outside = mid(300, 9)
        path = self.build({self.M: [("interweave", 210)], outside: [("interweave", 310)]}, self.seen(self.M) + self.seen(outside, sec=310), sent=(self.M, outside))
        out = self.run_report(path)[1]
        self.assertNotIn(outside, out.split("## Carrier-outage drill")[1])
        self.assertIn(self.M, out.split("## Carrier-outage drill")[1])
        # alpha as the drilled login: the messages were sent by it, none was addressed to it
        self.assertIn("no pair was made inside the drill", self.run_report(path, login="alpha")[1].split("## Carrier-outage drill")[1])

    def test_without_the_flag_nothing_of_the_section_appears_and_with_it_nothing_else_changes(self):
        path = self.build({self.M: [("interweave", 210)]}, self.seen(self.M), sent=(self.M,))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            carrier_main.main(["parity", "--window", iso(0), iso(1000), "--collected", path, "--host", "h"])
        plain = out.getvalue()
        self.assertNotIn("Carrier-outage", plain)
        with_flag = self.run_report(path)[1]
        self.assertEqual(with_flag[:with_flag.index("\n## Carrier-outage drill")].rstrip("\n"), plain.rstrip("\n"))

    def test_a_collection_without_the_account_or_its_shown_ledger_is_refused_not_read_as_never_shown(self):
        path = self.build({self.M: [("interweave", 210)]}, self.seen(self.M), sent=(self.M,))
        rc, out, err = self.run_report(path, login="gamma")
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("the collection has no account gamma", err)
        with open(os.path.join(path, "beta", "meta.json")) as fh:
            meta = json.load(fh)
        meta["relay_outage"] = {"complete": False, "reason": "shown: no answer", "skipped": 0}
        with open(os.path.join(path, "beta", "meta.json"), "w") as fh:
            json.dump(meta, fh)
        rc, out, err = self.run_report(path)
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("beta: the shown ledger was not collected whole (shown: no answer)", err)

    def test_the_flag_needs_a_collection(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = carrier_main.main(["parity", "--window", iso(0), iso(100), "--arrivals", "x", "--senders", "y", "--carrier-drill", iso(1), iso(2), "beta"])
        self.assertEqual((rc, out.getvalue()), (1, ""))
        self.assertIn("--carrier-drill reads the account's shown ledger, which only --collected holds", err.getvalue())

    def test_a_collection_made_before_the_shown_ledger_is_refused(self):
        path = self.build({self.M: [("interweave", 210)]}, self.seen(self.M), sent=(self.M,))
        os.unlink(os.path.join(path, "beta", "shown.jsonl"))
        rc, out, err = self.run_report(path)
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("beta: the collection has no shown ledger", err)

    def test_shown_ledger_cut_short_is_refused_by_its_count(self):
        path = self.build({self.M: [("interweave", 210)]}, self.seen(self.M), sent=(self.M,))
        with open(os.path.join(path, "beta", "shown.jsonl"), "w") as fh:
            fh.write("")
        rc, out, err = self.run_report(path)
        self.assertEqual(rc, 2)
        self.assertIn("beta: the files do not hold what the collection counted of the shown ledger", err)


if __name__ == "__main__":
    unittest.main(verbosity=1)
