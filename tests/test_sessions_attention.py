#!/usr/bin/env python3
"""fleet-deck-attention s3 on the account side: control/sessions.py's rows carry a blocked session's `reason`
(from the hook), the status line's `context` sample and the transcript's `activity`; control/ctl.py's state row
and record check carry them to the deck. Each is optional and absent where unknown (never 0, never "quiet"),
so a row without any of them stays what it was. Files are written under a scratch directory; time is a number
the test passes."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import ctl, sessions  # noqa: E402

NOW_MS = 1_800_000_000_000.0
SINCE = "2027-01-15T07:55:00Z"
AT = "2027-01-15T07:56:00.500Z"


def iso(ms: float) -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ms / 1000))


class Account(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="sessions-attention-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.file = os.path.join(self.dir, "session-state.json")

    def write(self, name: str, doc) -> str:
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(doc if isinstance(doc, str) else json.dumps(doc))
        return path

    def state(self, **entry) -> None:
        # No pid: the entry is believed within NO_PROCESS_FRESH_MS of its `since`.
        self.write("session-state.json", {"sessions": {"s-one-aaaa": {"state": "blocked", "since": iso(NOW_MS - 60_000), **entry}}})

    def row(self) -> dict:
        rows = sessions.read_sessions(self.file, now_ms=NOW_MS)
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    def transcript(self, age_s: float) -> str:
        path = os.path.join(self.dir, "t.jsonl")
        with open(path, "w") as fh:
            fh.write("{}\n")
        os.utime(path, (NOW_MS / 1000 - age_s,) * 2)
        return path


class Reason(Account):
    def test_a_blocked_session_carries_the_kind_the_hook_recorded(self):
        for kind in ("permission", "question"):
            self.state(reason=kind)
            self.assertEqual(self.row()["reason"], kind)

    def test_a_reason_outside_the_vocabulary_or_on_a_session_not_blocked_is_left_out(self):
        for bad in ("stuck", "Permission", 7, None, ["question"]):
            self.state(reason=bad)
            self.assertNotIn("reason", self.row(), repr(bad))
        self.state(state="working", reason="permission")
        self.assertNotIn("reason", self.row())

    def test_a_row_with_none_of_the_extras_is_the_three_keys_it_always_was(self):
        self.state()
        self.assertEqual(self.row(), {"session": "s-one-aaaa", "state": "blocked", "since": iso(NOW_MS - 60_000)})


class Context(Account):
    def sample(self, doc) -> None:
        self.write(sessions.CONTEXT_FILE, doc)

    def test_the_sample_beside_the_state_file_is_carried_for_its_session(self):
        self.state()
        self.sample({"sessions": {"s-one-aaaa": {"pct": 41, "at": AT}, "s-two-bbbb": {"pct": 90, "at": AT}}})
        self.assertEqual(self.row()["context"], {"pct": 41, "at": AT})

    def test_zero_percent_is_a_sample(self):
        self.state()
        self.sample({"sessions": {"s-one-aaaa": {"pct": 0, "at": AT}}})
        self.assertEqual(self.row()["context"], {"pct": 0, "at": AT})

    def test_no_file_an_unreadable_one_or_one_of_another_shape_is_no_sample_not_a_failure(self):
        self.state()
        self.assertNotIn("context", self.row())
        for doc in ("{not json", "[]", {"sessions": []}, {"sessions": {"s-one-aaaa": 41}}, b"\xff\xfe".decode("latin-1")):
            self.sample(doc)
            self.assertNotIn("context", self.row(), repr(doc))

    def test_a_value_that_is_not_a_percentage_with_a_time_is_left_out(self):
        self.state()
        for bad in ({"pct": 101, "at": AT}, {"pct": -1, "at": AT}, {"pct": 41.5, "at": AT}, {"pct": True, "at": AT},
                    {"pct": "41", "at": AT}, {"pct": 41}, {"pct": 41, "at": "yesterday"}, {"pct": 41, "at": 7}, {"pct": None, "at": AT}):
            self.sample({"sessions": {"s-one-aaaa": bad}})
            self.assertNotIn("context", self.row(), repr(bad))

    def test_the_sample_is_read_beside_the_state_file_not_in_its_parent_or_the_working_directory(self):
        # The state file lives one level down, so its parent and the working directory are scratch places of this test.
        os.mkdir(os.path.join(self.dir, "state"))
        self.file = os.path.join(self.dir, "state", "session-state.json")
        self.write("state/session-state.json", {"sessions": {"s-one-aaaa": {"state": "blocked", "since": iso(NOW_MS - 60_000)}}})
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        os.chdir(self.dir)
        self.write(sessions.CONTEXT_FILE, {"sessions": {"s-one-aaaa": {"pct": 77, "at": AT}}})
        self.assertNotIn("context", self.row())
        self.write("state/" + sessions.CONTEXT_FILE, {"sessions": {"s-one-aaaa": {"pct": 12, "at": AT}}})
        self.assertEqual(self.row()["context"]["pct"], 12, "positive control: beside the state file it is read")

    def test_a_sample_time_in_a_form_fleet_would_drop_is_left_out_here_too(self):
        self.state()
        for at in ("2027-01-15", "2027-01-15T07:56:00+01:00", "2027-01-15T07:56:00", "２０２７-01-15T07:56:00Z"):
            self.write(sessions.CONTEXT_FILE, {"sessions": {"s-one-aaaa": {"pct": 5, "at": at}}})
            self.assertNotIn("context", self.row(), at)


class Activity(Account):
    def test_a_transcript_written_in_the_last_thirty_seconds_is_recent_and_an_older_one_quiet(self):
        self.state(transcript=self.transcript(5))
        self.assertEqual(self.row()["activity"], "recent")
        self.state(transcript=self.transcript(30))
        self.assertEqual(self.row()["activity"], "recent", "the boundary is inside the window")
        self.state(transcript=self.transcript(31))
        self.assertEqual(self.row()["activity"], "quiet")

    def test_what_cannot_be_told_is_not_quiet(self):
        gone = os.path.join(self.dir, "never-written.jsonl")
        for bad in (gone, "relative/t.jsonl", "", None, 7, ["x"], self.dir + "/nul\0.jsonl", self.transcript(-3600)):
            self.state(transcript=bad)
            self.assertNotIn("activity", self.row(), repr(bad))

    def test_a_relative_path_is_not_resolved_against_whatever_directory_the_agent_runs_in(self):
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        self.transcript(1)
        os.chdir(self.dir)             # "t.jsonl" now exists relative to the agent's directory
        self.assertTrue(os.path.exists("t.jsonl"))
        self.state(transcript="t.jsonl")
        self.assertNotIn("activity", self.row())

    def test_only_the_modification_time_is_read(self):
        path = self.transcript(600)
        os.chmod(path, 0o000)          # stat needs no read permission on the file itself
        try:
            self.state(transcript=path)
            self.assertEqual(self.row()["activity"], "quiet")
        finally:
            os.chmod(path, 0o600)

    def test_a_clock_a_little_ahead_is_still_recent(self):
        self.state(transcript=self.transcript(-5))
        self.assertEqual(self.row()["activity"], "recent")


class Watcher(Account):
    def test_the_record_is_posted_again_when_the_activity_flips_and_not_when_nothing_changed(self):
        posted = []
        clock = [NOW_MS]
        w = sessions.StateWatcher(address="h/a", post=posted.append, file=self.file, now=lambda: clock[0])
        self.state(transcript=self.transcript(5))
        self.assertTrue(w.tick())
        self.assertFalse(w.tick(), "unchanged: no post")
        clock[0] += 40_000
        self.assertTrue(w.tick(), "the transcript is now older than the window")
        self.assertEqual([r["sessions"][0]["activity"] for r in posted], ["recent", "quiet"])


class Ctl(unittest.TestCase):
    def row_of(self, sessions_: list) -> dict:
        rec = {"v": 1, "kind": "state", "from": "h/a", "ts": iso(NOW_MS), "sessions": sessions_}
        return ctl.state_row("h/a", rec, NOW_MS)

    S = {"session": "s-one-aaaa", "since": SINCE}

    def test_the_row_carries_the_top_sessions_facts_not_another_sessions(self):
        top = {**self.S, "state": "blocked", "reason": "question", "context": {"pct": 40, "at": AT}, "activity": "quiet"}
        low = {"session": "s-two-bbbb", "state": "working", "since": SINCE, "context": {"pct": 99, "at": AT}, "activity": "recent"}
        row = self.row_of([low, top])
        self.assertEqual((row["state"], row["reason"], row["context"], row["activity"]), ("blocked", "question", {"pct": 40, "at": AT}, "quiet"))

    def test_a_row_without_them_has_no_such_keys(self):
        row = self.row_of([{**self.S, "state": "idle"}])
        for key in ("reason", "context", "activity"):
            self.assertNotIn(key, row)

    def test_an_unknown_state_row_carries_nothing_of_them(self):
        rec = {"v": 1, "kind": "state", "from": "h/a", "ts": "2020-01-01T00:00:00.000Z",
               "sessions": [{**self.S, "state": "blocked", "reason": "question", "activity": "quiet"}]}
        row = ctl.state_row("h/a", rec, NOW_MS)
        self.assertEqual(row["state"], "unknown")
        self.assertNotIn("reason", row)
        self.assertNotIn("activity", row)

    def follow(self, as_json: bool) -> list:
        """The lines `states --follow` prints for a snapshot and then a record that differs only in `activity` and `context`."""
        class Stop(BaseException):
            pass

        def rec(id_: str, **extra) -> dict:
            body = {"v": 1, "kind": "state", "from": "h/a", "ts": iso(NOW_MS), "sessions": [{**self.S, "state": "working", **extra}]}
            return {"id": id_, "content": json.dumps(body)}
        script = iter([{"messages": [rec("1", activity="recent")]}, {"messages": [rec("2", activity="quiet", context={"pct": 50, "at": AT})]}])

        def call(_path, **_kw):
            try:
                return next(script)
            except StopIteration:
                raise Stop() from None
        out: list = []
        with self.assertRaises(Stop):
            ctl.states({"json": as_json, "follow": True}, [{"address": "h/a"}], call=call,
                       cfg={"channel": "c", "state_channel": "c:state", "relay_url": "x"}, out=out.append, err=lambda _m: None,
                       now=lambda: NOW_MS, sleep=lambda _s: None)
        return out

    def test_text_follow_prints_no_second_line_for_what_it_does_not_show_and_json_prints_it(self):
        self.assertEqual(len(self.follow(False)), 1)
        self.assertEqual(len(self.follow(True)), 2)

    def checked(self, session: dict):
        rec = {"v": 1, "kind": "state", "from": "h/a", "ts": iso(NOW_MS), "sessions": [{**self.S, "state": "blocked", **session}]}
        return ctl.state_record_of({"content": json.dumps(rec)}, {"h/a"})

    def test_the_record_check_takes_the_shapes_agentd_writes(self):
        for good in ({}, {"reason": "permission"}, {"activity": "recent"}, {"context": {"pct": 0, "at": AT}}, {"context": {"pct": 100, "at": AT}},
                      {"reason": None}, {"activity": None}, {"context": None}):
            self.assertIsNotNone(self.checked(good), good)

    def test_the_record_check_refuses_a_forged_shape(self):
        for bad in ({"reason": "stuck"}, {"reason": 7}, {"activity": "busy"}, {"context": 62}, {"context": {"pct": 101, "at": AT}},
                    {"context": {"pct": True, "at": AT}}, {"context": {"pct": 62}}, {"context": {"pct": 62, "at": 7}},
                    {"context": {"pct": 62, "at": "2027-01-15"}}, {"context": {"pct": 62, "at": "2027-01-15T07:56:00+01:00"}}):
            self.assertIsNone(self.checked(bad), bad)


if __name__ == "__main__":
    unittest.main()
