#!/usr/bin/env python3
"""tools/fabric/reflect_jobs.py (fabric-reflect-jobs) with a fake fabric-ctl
runner: no relay, no agentd. Each case states the behaviour it pins."""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import reflect_jobs as rj  # noqa: E402

PLACED = [{"login": "dev-01", "host": "h", "address": "h/dev-01", "kind": "agent"},
          {"login": "dev-02", "host": "h", "address": "h/dev-02", "kind": "agent"},
          {"login": "dev-03", "host": "h", "address": "h/dev-03", "kind": "agent"},
          {"login": "alice", "host": "h", "address": "h/alice", "kind": "human"}]


class Fleet:
    """A fake fabric-ctl: per login, its open jobs, or a status that is not ok; calls are recorded."""

    def __init__(self, jobs=None, silent=(), refuse=()):
        self.jobs, self.silent, self.refuse, self.calls = jobs or {}, set(silent), set(refuse), []

    def __call__(self, argv):
        self.calls.append(argv)
        login, op = argv[1], argv[2]
        assert argv[0] == rj.FABRIC_CTL and "--json" in argv
        if login in self.silent:
            row = {"account": login, "status": "silent"}
        elif op == "jobs":
            row = {"account": login, "status": "ok", "jobs": {"status": "ok", "jobs": self.jobs.get(login, [])}}
        elif login in self.refuse:
            row = {"account": login, "status": "ok", "jobsAdd": {"status": "refused", "reason": "no answer within 15 s"}}
        else:
            row = {"account": login, "status": "ok", "jobsAdd": {"status": "added", "job": "j7"}}
        return subprocess.CompletedProcess(argv, 0 if row["status"] == "ok" else 1, json.dumps(row) + "\n", "")

    def adds(self):
        return [c for c in self.calls if c[2] == "jobs-add"]


NOW = lambda: datetime.datetime(2026, 10, 15, 12, tzinfo=datetime.timezone.utc)  # noqa: E731


def go(fleet, *argv):
    out: list[str] = []
    rc = rj.main(list(argv), run=fleet, placed=lambda: PLACED, now=NOW, out=out.append)
    return rc, out


class ReflectJobs(unittest.TestCase):
    def test_every_placed_agent_gets_the_pass_and_a_human_does_not(self):
        f = Fleet()
        rc, out = go(f)
        self.assertEqual(rc, 0)
        self.assertEqual(out, ["dev-01: added j7", "dev-02: added j7", "dev-03: added j7"])
        self.assertEqual([c[1] for c in f.adds()], ["dev-01", "dev-02", "dev-03"])
        argv = f.adds()[0]
        self.assertEqual(argv[3:11], ["--topic", "reflection", "--project", "agent-fabric", "--priority", "normal", "--json", "--"])
        title = argv[11]
        self.assertTrue(title.startswith("Reflection pass 2026-W42 (ADR-058): run fabric-reflect"), title)
        self.assertTrue(len(title) <= 300 and "\n" not in title)

    def test_an_open_reflection_job_skips_the_login_and_is_named(self):
        f = Fleet({"dev-02": [{"id": "j3", "title": "something else"}, {"id": "j9", "title": "Reflection pass 2026-W41 (ADR-058): x"}]})
        rc, out = go(f)
        self.assertEqual(rc, 0)
        self.assertEqual(out[1], "dev-02: skipped (open j9)")
        self.assertEqual([c[1] for c in f.adds()], ["dev-01", "dev-03"])
        # positive control: a title that merely contains the words is not a pass
        f2 = Fleet({"dev-01": [{"id": "j1", "title": "Prepare a Reflection pass later"}]})
        go(f2, "dev-01")
        self.assertEqual(len(f2.adds()), 1)

    def test_a_failed_login_does_not_stop_the_others_and_makes_exit_1(self):
        f = Fleet(silent=["dev-01"], refuse=["dev-02"])
        rc, out = go(f)
        self.assertEqual(rc, 1)
        self.assertEqual(out[0], "dev-01: failed: dev-01 did not answer: silent")
        self.assertEqual(out[1], "dev-02: failed: no answer within 15 s")
        self.assertEqual(out[2], "dev-03: added j7")

    def test_a_runner_that_raises_is_a_failure_of_that_login_only(self):
        calls = []

        def run(argv):
            calls.append(argv[1])
            if argv[1] == "dev-01":
                raise subprocess.TimeoutExpired(argv, 120)
            return Fleet()(argv)
        out: list[str] = []
        rc = rj.main([], run=run, placed=lambda: PLACED, now=NOW, out=out.append)
        self.assertEqual(rc, 1)
        self.assertIn("dev-01: failed: no answer within 120 s", out)
        self.assertIn("dev-03: added j7", out)

    def test_unparseable_output_is_a_failure_never_an_empty_list(self):
        run = lambda argv: subprocess.CompletedProcess(argv, 0, "not json\n", "")  # noqa: E731
        out: list[str] = []
        rc = rj.main(["dev-01"], run=run, placed=lambda: PLACED, now=NOW, out=out.append)
        self.assertEqual(rc, 1)
        self.assertTrue(out[0].startswith("dev-01: failed: fabric-ctl printed a line that is not JSON"), out)

    def test_dry_run_asks_the_lists_and_adds_nothing(self):
        f = Fleet({"dev-02": [{"id": "j9", "title": "Reflection pass 2026-W41"}]})
        rc, out = go(f, "--dry-run")
        self.assertEqual(rc, 0)
        self.assertEqual(out, ["dev-01: would add", "dev-02: skipped (open j9)", "dev-03: would add"])
        self.assertEqual(f.adds(), [])
        self.assertEqual(len(f.calls), 3)

    def test_json_is_the_same_as_a_list(self):
        rc, out = go(Fleet({"dev-02": [{"id": "j9", "title": "Reflection pass x"}]}, silent=["dev-03"]), "--json")
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out[0]), [
            {"login": "dev-01", "result": "added", "job": "j7"},
            {"login": "dev-02", "result": "skipped", "job": "j9"},
            {"login": "dev-03", "result": "failed", "reason": "dev-03 did not answer: silent"}])

    def test_week_is_validated_and_names_the_title(self):
        f = Fleet()
        self.assertEqual(go(f, "--week", "2026-W05", "dev-01")[0], 0)
        self.assertIn("Reflection pass 2026-W05 (ADR-058)", f.adds()[0][11])
        for bad in ("2026-W5", "2026-W00", "2026-W54", "2025-W53", "26-W05", "2026W05", "2026-W05\n", ""):
            f = Fleet()
            rc, out = go(f, "--week", bad)
            self.assertEqual((rc, f.calls), (2, []), bad)
        self.assertEqual(go(Fleet(), "--week", "2026-W53", "dev-01")[0], 0, "2026 has 53 ISO weeks")
        self.assertEqual(go(Fleet(), "--week")[0], 2)

    def test_a_human_or_an_unplaced_login_is_refused_with_nothing_run(self):
        for bad in ("alice", "ghost"):
            f = Fleet()
            self.assertEqual(go(f, "dev-01", bad)[0], 2)
            self.assertEqual(f.calls, [], bad)

    def test_the_logins_given_are_the_only_ones_asked_once_each(self):
        f = Fleet()
        rc, out = go(f, "dev-03", "dev-03")
        self.assertEqual((rc, out), (0, ["dev-03: added j7"]))

    def test_control_characters_from_an_account_are_shown_escaped(self):
        f = Fleet({"dev-01": [{"id": "j\x1b[2J", "title": "Reflection pass x"}]})
        rc, out = go(f, "dev-01")
        self.assertEqual(out, ["dev-01: skipped (open j\\x1b[2J)"])
        self.assertEqual(rj.line_of({"login": "a", "result": "failed", "reason": "x\x7fy\x9bz"}), "a: failed: x\\x7fy\\x9bz", "DEL and C1 too")

    def test_no_placed_agent_says_so_on_stderr_and_exits_0(self):
        import contextlib, io
        err, out = io.StringIO(), []
        with contextlib.redirect_stderr(err):
            rc = rj.main([], run=Fleet(), placed=lambda: [PLACED[3]], now=NOW, out=out.append)
        self.assertEqual((rc, out), (0, []))
        self.assertIn("nothing to do", err.getvalue())

    def test_an_unknown_option_is_usage(self):
        self.assertEqual(go(Fleet(), "--all")[0], 2)

    def test_the_iso_week_is_the_year_of_the_week_not_the_calendar_year(self):
        d = datetime.datetime(2027, 1, 1, tzinfo=datetime.timezone.utc)
        self.assertEqual(rj.iso_week(d), "2026-W53")


if __name__ == "__main__":
    unittest.main()
