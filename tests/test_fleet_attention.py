#!/usr/bin/env python3
"""tools/fabric/fleet.py's `attention` section (Fleet Deck's "needs you" views; plan
fleet-deck-attention step s1): derived from the `states` and `jobs` records of one fetch.
Every source is a fake program behind Ctx.run, as in tests/test_fleet.py (the oracle for
the rest of fleet.py, unchanged). What is pinned: the three levels and which wins, the
reason from a job's own words and what is done to it, `since`, the counts, `at` as the
oldest input's, stale and failed (never `none` for what is unknown), the inputs read and
shown with it, no cache entry of its own, and the human login."""
from __future__ import annotations

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
import fleet  # noqa: E402
from test_fleet import Fleet, ctl_rows, done, rec  # noqa: E402

T0 = 1_800_000_000.0


def states_rows(**per: dict) -> str:
    """What `fabric-ctl all states --json` prints: one row per address, no `account`, no status."""
    rows = []
    for login in ("a", "b", "c"):
        row = {"address": f"h1/{login}", "ts": "2027-01-15T08:00:00.000Z", "sessions": [], "state": "none", "since": None}
        row.update(per.get(login, {}))
        rows.append(json.dumps(row))
    return "\n".join(rows) + "\n"


def job(jid: str, state: str, blocked_on: str | None = None, updated: str | None = "2027-01-15T07:00:00Z") -> dict:
    return {"id": jid, "state": state, "title": f"title {jid}", "project": None, "topic": None, "priority": "normal",
            "source": "self", "blocked_on": blocked_on, "artifacts": [], "updated": updated}


def jobs_rows(**per: list) -> str:
    """`fabric-ctl all jobs --json`: the op's {status, jobs} under the row's `jobs` key (ctl rows())."""
    return ctl_rows("jobs", **{login: {"jobs": {"status": "ok", "jobs": listed}} for login, listed in per.items()})


def attention(doc, login):
    return rec(doc, login, "attention")


class Levels(unittest.TestCase):
    def fleet(self, states: str, jobs: str) -> Fleet:
        return Fleet(self, {("fabric-ctl", "states"): done(states), ("fabric-ctl", "jobs"): done(jobs)})

    def test_a_session_waiting_on_a_person_is_needs_input_with_its_since_and_no_reason(self):
        f = self.fleet(states_rows(a={"state": "blocked", "since": "2027-01-15T07:30:00Z"}), jobs_rows(a=[job("j1", "queued"), job("j2", "queued")]))
        r = attention(f.fetch(["attention"]), "a")
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["data"], {"level": "needs_input", "reason": None, "since": "2027-01-15T07:30:00Z", "blocked": 0, "pending": 2})

    def test_needs_input_wins_over_a_blocked_job(self):
        f = self.fleet(states_rows(a={"state": "blocked", "since": "2027-01-15T07:30:00Z"}), jobs_rows(a=[job("j1", "blocked", "a review")]))
        d = attention(f.fetch(["attention"]), "a")["data"]
        self.assertEqual((d["level"], d["reason"], d["blocked"]), ("needs_input", None, 1))

    def test_a_blocked_job_is_waiting_with_its_own_words_and_its_updated_as_since(self):
        f = self.fleet(states_rows(a={"state": "idle", "since": "2027-01-15T06:00:00Z"}),
                       jobs_rows(a=[job("j1", "blocked", "owner's word on the merge", "2027-01-15T07:10:00Z"), job("j2", "queued")]))
        d = attention(f.fetch(["attention"]), "a")["data"]
        self.assertEqual(d, {"level": "waiting", "reason": "owner's word on the merge", "since": "2027-01-15T07:10:00Z", "blocked": 1, "pending": 1})

    def test_with_several_blocked_jobs_the_most_recently_updated_gives_the_reason_the_first_among_equals(self):
        jobs = [job("j1", "blocked", "older", "2027-01-15T05:00:00Z"), job("j2", "blocked", "newest", "2027-01-15T08:00:00Z"),
                job("j3", "blocked", "also newest", "2027-01-15T08:00:00Z")]
        d = attention(self.fleet(states_rows(a={"state": "working"}), jobs_rows(a=jobs)).fetch(["attention"]), "a")["data"]
        self.assertEqual((d["reason"], d["blocked"]), ("newest", 3))

    def test_a_waiting_job_with_no_words_has_a_null_reason(self):
        d = attention(self.fleet(states_rows(), jobs_rows(a=[job("j1", "blocked", None, None)])).fetch(["attention"]), "a")["data"]
        self.assertEqual((d["level"], d["reason"], d["since"]), ("waiting", None, None))

    def test_working_idle_and_no_session_with_nothing_blocked_are_none(self):
        for state in ("working", "idle", "none"):
            f = self.fleet(states_rows(a={"state": state}), jobs_rows(a=[job("j1", "active"), job("j2", "delivered")]))
            d = attention(f.fetch(["attention"]), "a")["data"]
            self.assertEqual(d, {"level": "none", "reason": None, "since": None, "blocked": 0, "pending": 0}, state)

    def test_the_counts_are_blocked_and_queued_jobs_only(self):
        jobs = [job("j1", "blocked", "x"), job("j2", "blocked", "y"), job("j3", "queued"), job("j4", "active"), job("j5", "delivered")]
        d = attention(self.fleet(states_rows(), jobs_rows(a=jobs)).fetch(["attention"]), "a")["data"]
        self.assertEqual((d["blocked"], d["pending"]), (2, 1))

    def test_a_needs_input_whose_since_is_not_a_time_string_has_a_null_since(self):
        f = self.fleet(states_rows(a={"state": "blocked", "since": 7}), jobs_rows(a=[]))
        self.assertIsNone(attention(f.fetch(["attention"]), "a")["data"]["since"])


class Times(unittest.TestCase):
    """`since` is a time or null; the job that gives the reason is chosen by times that are times."""

    def test_a_since_that_is_not_a_time_is_null_not_the_text_of_whoever_posted_it(self):
        for bad in ("evil\u202etext", "yesterday", "2027-01-15 07:30:00", "２０２７-01-15T07:30:00Z", 7, None, ""):
            f = Fleet(self, {("fabric-ctl", "states"): done(states_rows(a={"state": "blocked", "since": bad})), ("fabric-ctl", "jobs"): done(jobs_rows(a=[]))})
            self.assertIsNone(attention(f.fetch(["attention"]), "a")["data"]["since"], bad)

    def test_the_times_producers_write_pass(self):
        for good in ("2027-01-15T07:30:00Z", "2027-01-15T07:30:00.123Z"):
            f = Fleet(self, {("fabric-ctl", "states"): done(states_rows(a={"state": "blocked", "since": good})), ("fabric-ctl", "jobs"): done(jobs_rows(a=[]))})
            self.assertEqual(attention(f.fetch(["attention"]), "a")["data"]["since"], good)

    def test_a_job_whose_updated_is_not_a_time_cannot_outrank_one_whose_is(self):
        jobs = [job("j1", "blocked", "the real one", "2027-01-15T07:00:00Z"), job("j2", "blocked", "forged", "zzzz")]
        d = attention(Fleet(self, {("fabric-ctl", "states"): done(states_rows()), ("fabric-ctl", "jobs"): done(jobs_rows(a=jobs))}).fetch(["attention"]), "a")["data"]
        self.assertEqual((d["reason"], d["since"]), ("the real one", "2027-01-15T07:00:00Z"))


class Reason(unittest.TestCase):
    def test_control_format_and_surrogate_characters_become_spaces_and_white_space_collapses(self):
        self.assertEqual(fleet.attention_text("a\n\tb\x1b[31mc\u202ed\ud800e\u200bf  g\u2028h"), "a b [31mc d e f g h")

    def test_text_is_cut_at_eighty_characters_with_an_ellipsis_and_not_before(self):
        self.assertEqual(len(fleet.attention_text("x" * 80)), 80)
        self.assertEqual(fleet.attention_text("x" * 80), "x" * 80)
        cut = fleet.attention_text("y" * 81)
        self.assertEqual((len(cut), cut[-1]), (80, "…"))
        self.assertEqual(fleet.attention_text("z" * 78 + " " + "w" * 10), "z" * 78 + "…", "the cut does not leave a trailing space")

    def test_blank_looking_fillers_become_spaces_so_a_reason_made_of_them_is_none(self):
        self.assertEqual(fleet.attention_text("a\u3164\u2800b\u034fc"), "a b c")
        self.assertIsNone(fleet.attention_text("\u3164\u2800\u115f"))

    def test_what_is_not_text_or_has_no_text_is_none(self):
        for v in (None, 7, [], "", "   ", "\x00\x1b\u200b"):
            self.assertIsNone(fleet.attention_text(v), v)

    def test_a_reason_with_a_lone_surrogate_leaves_the_record_encodable(self):
        f = Fleet(self, {("fabric-ctl", "states"): done(states_rows()), ("fabric-ctl", "jobs"): done(jobs_rows(a=[job("j1", "blocked", "wait\ud800 here")]))})
        doc = f.fetch(["attention"])
        json.dumps(attention(doc, "a"), ensure_ascii=False).encode("utf-8")
        self.assertEqual(attention(doc, "a")["data"]["reason"], "wait here")


class Freshness(unittest.TestCase):
    def setUp(self):
        self.f = Fleet(self, {("fabric-ctl", "states"): done(states_rows(a={"state": "idle"})), ("fabric-ctl", "jobs"): done(jobs_rows(a=[job("j1", "queued")]))})

    def test_at_is_the_oldest_inputs_read_time(self):
        self.f.fetch(["jobs"])                    # jobs read at T0, cached for 30 s
        self.f.t += 10                            # states (5 s) is read again, jobs (30 s) is not
        doc = self.f.fetch(["attention"])
        self.assertEqual(rec(doc, "a", "jobs")["at"], fleet.stamp(T0))
        self.assertEqual(rec(doc, "a", "states")["at"], fleet.stamp(T0 + 10))
        self.assertEqual(attention(doc, "a")["at"], fleet.stamp(T0))

    def test_when_an_input_could_not_be_refreshed_the_record_is_stale_with_the_oldest_age_and_the_last_good_values(self):
        self.f.fetch(["attention"])
        self.f.handlers[("fabric-ctl", "states")] = done("", "no relay", 1)
        self.f.t += 20
        r = attention(self.f.fetch(["attention"]), "a")
        self.assertEqual(r["status"], "stale")
        self.assertEqual(r["age_s"], 20)
        self.assertIn("states:", r["why"])
        self.assertEqual(r["data"]["level"], "none")
        self.assertEqual(r["at"], fleet.stamp(T0), "the oldest read time, the states' last good one")

    def test_with_both_inputs_stale_the_age_is_the_older_and_both_whys_are_said(self):
        self.f.fetch(["attention"])                       # both read at T0
        self.f.t += 3
        self.f.fetch(["jobs"], max_age=0)                 # jobs read again at T0+3
        self.f.handlers[("fabric-ctl", "states")] = done("", "no relay", 1)
        self.f.handlers[("fabric-ctl", "jobs")] = done("", "no relay either", 1)
        self.f.t += 40                                    # past jobs' TTL (30 s), inside the stale window (600 s)
        r = attention(self.f.fetch(["attention"]), "a")
        self.assertEqual((r["status"], r["age_s"]), ("stale", 43), "states was last read 43 s ago, jobs 40 s ago")
        self.assertTrue("states:" in r["why"] and "jobs:" in r["why"], r["why"])

    def test_an_input_past_its_stale_window_makes_it_failed(self):
        self.f.fetch(["attention"])
        self.f.handlers[("fabric-ctl", "states")] = done("", "no relay", 1)
        self.f.t += 1000
        r = attention(self.f.fetch(["attention"]), "a")
        self.assertEqual(r["status"], "failed")
        self.assertIn("no relay", r["why"])

    def test_it_has_no_cache_entry_of_its_own(self):
        self.f.fetch(["attention"])
        cached = sorted(os.listdir(os.path.join(self.f.xdg, "fabric-fleet")))
        self.assertEqual(cached, ["jobs.json", "states.json"])


class Unknown(unittest.TestCase):
    def test_no_row_for_the_agent_is_failed_never_none(self):
        f = Fleet(self, {("fabric-ctl", "states"): done(states_rows()), ("fabric-ctl", "jobs"): done(jobs_rows(a=[], b=[], c=[]))})
        doc = f.fetch(["attention"])
        self.assertEqual(attention(doc, "a")["status"], "ok", "positive control: the others are answered")
        f2 = Fleet(self, {("fabric-ctl", "states"): done("".join(ln for ln in states_rows().splitlines(True) if "h1/c" not in ln)),
                          ("fabric-ctl", "jobs"): done(jobs_rows(a=[], b=[], c=[]))})
        r = attention(f2.fetch(["attention"]), "c")
        self.assertEqual(r["status"], "failed")
        self.assertIn("no row for this agent", r["why"])

    def test_an_account_whose_state_is_unknown_is_failed_with_the_states_own_why(self):
        f = Fleet(self, {("fabric-ctl", "states"): done(states_rows(a={"state": "unknown", "why": "no record for two heartbeats"})),
                         ("fabric-ctl", "jobs"): done(jobs_rows(a=[job("j1", "blocked", "x")]))})
        r = attention(f.fetch(["attention"]), "a")
        self.assertEqual(r["status"], "failed")
        self.assertIn("no record for two heartbeats", r["why"])
        self.assertNotIn("data", r)

    def test_a_failed_jobs_read_is_failed_even_when_the_session_state_is_known(self):
        f = Fleet(self, {("fabric-ctl", "states"): done(states_rows(a={"state": "blocked", "since": "2027-01-15T07:30:00Z"})),
                         ("fabric-ctl", "jobs"): done(ctl_rows("jobs", a={"jobs": {"status": "failed", "error": "EACCES jobs.json"}}))})
        r = attention(f.fetch(["attention"]), "a")
        self.assertEqual(r["status"], "failed")
        self.assertIn("EACCES", r["why"])

    def test_a_jobs_answer_that_is_not_a_list_is_failed(self):
        f = Fleet(self, {("fabric-ctl", "states"): done(states_rows()), ("fabric-ctl", "jobs"): done(ctl_rows("jobs", a={"jobs": {"status": "ok", "jobs": "none"}}))})
        r = attention(f.fetch(["attention"]), "a")
        self.assertEqual(r["status"], "failed")
        self.assertIn("no list of jobs", r["why"])

    def test_a_human_login_is_failed_naming_each_input_that_could_not_be_read(self):
        f = Fleet(self, {("fabric-ctl", "states"): done(states_rows()), ("fabric-ctl", "jobs"): done(jobs_rows(a=[], b=[], c=[]))})
        r = attention(f.fetch(["attention"]), "hum")
        self.assertEqual(r["status"], "failed")
        self.assertEqual(r["why"].count(fleet.HUMAN), 2)
        self.assertTrue(r["why"].startswith("states: ") and "; jobs: " in r["why"], r["why"])


class Output(unittest.TestCase):
    def test_the_command_prints_utf_8_whatever_the_locale_says(self):
        import subprocess
        code = ("import sys; sys.path.insert(0, %r); import fleet\n"
                "fleet.fetch = lambda *a, **k: {'schema': 1, 'note': '\\u00e9\\u6f22 \\ud800'}\n"
                "sys.exit(fleet.main(['--json']))\n") % os.path.join(HERE, "tools", "fabric")
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=60, env={**os.environ, "PYTHONIOENCODING": "ascii"})
        self.assertEqual(r.returncode, 0, r.stderr[-300:])
        self.assertEqual(json.loads(r.stdout.decode("utf-8"))["note"], "\u00e9\u6f22 \ufffd")

    def test_a_lone_surrogate_anywhere_in_the_document_prints_as_u_fffd_and_the_rest_is_untouched(self):
        doc = {"schema": 1, "agents": [{"login": "a\udcff", "sections": {"jobs": {"data": {"jobs": {"jobs": [{"blocked_on": "wait\ud800 here — é"}]}}}}}]}
        text = fleet.dumps(doc)
        text.encode("utf-8")
        self.assertEqual(json.loads(text)["agents"][0]["login"], "a\ufffd")
        self.assertEqual(json.loads(text)["agents"][0]["sections"]["jobs"]["data"]["jobs"]["jobs"][0]["blocked_on"], "wait\ufffd here — é")

    def test_a_document_with_none_is_what_json_dumps_gave_before(self):
        doc = {"schema": 1, "at": "x", "agents": [{"login": "a", "note": "é漢字 \"q\" \\"}]}
        self.assertEqual(fleet.dumps(doc), json.dumps(doc, ensure_ascii=False))


class Document(unittest.TestCase):
    def setUp(self):
        self.f = Fleet(self, {("fabric-ctl", "states"): done(states_rows()), ("fabric-ctl", "jobs"): done(jobs_rows(a=[], b=[], c=[]))})

    def test_naming_it_reads_and_shows_its_inputs(self):
        doc = self.f.fetch(["attention"])
        self.assertEqual(doc["sections"], ["attention", "states", "jobs"])
        for a in doc["agents"]:
            self.assertEqual(sorted(a["sections"]), ["attention", "jobs", "states"])
        self.assertEqual(attention(doc, "a")["src"], "derived:states+jobs")

    def test_naming_its_inputs_too_does_not_read_them_twice(self):
        self.f.fetch(["jobs", "states", "attention"])
        self.assertEqual((len(self.f.ctl_calls("jobs")), len(self.f.ctl_calls("states"))), (1, 1))

    def test_it_is_in_the_default_sections_and_in_cost_class_c1(self):
        self.assertIn("attention", fleet.DEFAULT_SECTIONS)
        self.assertEqual(fleet.SECTIONS["attention"].cost, "C1")
        self.assertIn("attention", fleet.expand("C1"))
        self.assertEqual(fleet.expand("attention"), ["attention"])

    def test_every_derived_section_has_a_reader(self):
        self.assertEqual(set(fleet.DERIVERS), {n for n, s in fleet.SECTIONS.items() if s.derives})

    def test_one_agent_asked_is_one_agents_record(self):
        doc = self.f.fetch(["attention"], agent="b")
        self.assertEqual([a["login"] for a in doc["agents"]], ["b"])
        self.assertEqual(attention(doc, "b")["status"], "ok")


if __name__ == "__main__":
    unittest.main()
