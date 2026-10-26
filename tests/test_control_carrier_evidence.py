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
from gzcoord.carrier import main as carrier_main, parity, record  # noqa: E402

T0 = 1_792_000_000
OP = "interweave-evidence"
SECRET = "SECRET-BODY-9f3a"      # the marker no reply, row or file may ever hold


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
        """`queued`: (mid, to, seconds, events after it); the text of each is SECRET."""
        with open(os.path.join(self.state, "interweave", "deliveries.jsonl"), "w", encoding="utf-8") as fh:
            for m, to, sec, later in queued:
                fh.write(json.dumps({"e": "queued", "mid": m, "to": to, "tmids": ["t1"], "text": SECRET, "t": iso(sec), "enc": "plain"}) + "\n")
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
        self.arrivals([arrival(m, "h/b", "interweave", 6, content=SECRET, text=SECRET, path="/home/x/.secret", body=SECRET)])
        self.deliveries([(m, "b", 5, ["posted"])], done=[{"mid": mid(1, 9), "to": "c", "enc": "plain", "queued": iso(1), "text": SECRET}])
        self.journal([(m, "inbound", SECRET, json.dumps({"TO-ROLE": "r", "NOTE": SECRET}))])
        for f in ("gzcoord-arrivals.jsonl", os.path.join("interweave", "deliveries.jsonl"), "episodic.db"):
            with open(os.path.join(self.state, f), "rb") as fh:
                self.assertIn(SECRET.encode(), fh.read(), f"positive control: {f} holds the marker")
        a, d = self.ask("arrivals", 0, 100), self.ask("deliveries", 0, 100)
        self.assertEqual((a["status"], len(a["rows"]), d["status"], len(d["rows"])), ("ok", 1, "ok", 2))
        for reply in (a, d):
            self.assertNotIn(SECRET, json.dumps(reply))
        self.assertEqual(set(a["rows"][0]), set(ev.ARRIVAL_KEYS), "an arrival row has the closed list of keys and no other")
        self.assertTrue(all(set(r) <= set(ev.DELIVERY_KEYS) for r in d["rows"]))
        self.assertEqual(a["kinds"], {m: "role"})

    def test_a_value_that_is_not_a_short_string_is_not_sent_as_one(self):
        m = mid(5, 1)
        self.arrivals([arrival(m, "h/b", "interweave", 6, verdict="ok"), {**arrival(mid(6, 2), "h/b", "interweave", 7), "verdict": {"nested": SECRET}},
                       arrival(mid(7, 3), "h/b", "interweave", 8, verdict="v" * 5000)])
        a = self.ask("arrivals", 0, 100)
        self.assertNotIn(SECRET, json.dumps(a))
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
                fh.write(json.dumps({"e": "queued", "mid": m, "to": to, "tmids": ["t"], "text": SECRET, "t": iso(sec), "enc": "plain"}) + "\n")

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
        self.assertEqual(sorted(os.listdir(d)), ["arrivals.jsonl", "deliveries.jsonl", "kinds.json", "meta.json"])
        self.assertEqual(stat.S_IMODE(os.stat(d).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(out).st_mode), 0o700)
        for f in os.listdir(d):
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(d, f)).st_mode), 0o600, f)
        for f in os.listdir(d):
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                self.assertNotIn(SECRET, fh.read(), f)
        with open(os.path.join(d, "meta.json"), encoding="utf-8") as fh:
            meta = json.load(fh)
        self.assertEqual((meta["complete"], meta["counts"], meta["login"]), (True, {"arrivals": 1, "deliveries": 1, "kinds": 0}, "a"))
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
        """alpha sent to beta a message made 10 s before the window closes; beta's interweave copy came 5 s before, its relay copy 5 s after."""
        m = mid(990, 1)
        self.beta_arrivals = [arrival(m, "h/beta", "interweave", 995), arrival(m, "h/beta", "relay", 1005)]
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
        self.assertEqual(full["carriers"]["relay"], {"delivered": 1, "missed": 0, "duplicates": 0, "mismatch": 0}, "positive control: the full files show no miss")
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
        self.assertIn("The journal could not be read on beta", text)
        self.assertNotIn("gamma:", text.split("Collected from")[1].split("Framing")[0].replace("gamma\n", ""))


class Operator(unittest.TestCase):
    ARGS = ["--since", "2026-10-26T05:20:00Z", "--until", "2026-10-27T05:20:00Z"]

    def test_the_verb_needs_a_window_and_refuses_the_options_of_other_verbs(self):
        a = ctl.parse_args(["all", OP, *self.ARGS])
        self.assertEqual((a["op"], a["since"], a["until"], a["section"], a["timeout"]), (OP, "2026-10-26T05:20:00Z", "2026-10-27T05:20:00Z", None, ev.EVIDENCE_BUDGET_S))
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
                         ("a", True, [a1], {mid(1, 1): "direct"}, {"arrivals": 1, "deliveries": 0, "kinds": 1}))
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
             "since": iso(-100), "until": iso(2000), "margin_s": parity.MARGIN_S, "pages": {"arrivals": 1, "deliveries": 1}, "skipped": 0, "undated": 0}
        a.update(over)
        a["counts"] = over.get("counts", {"arrivals": len(a["arrivals"]), "deliveries": len(a["deliveries"]), "kinds": len(a["kinds"])})
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


if __name__ == "__main__":
    unittest.main(verbosity=1)
