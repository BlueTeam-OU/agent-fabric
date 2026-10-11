#!/usr/bin/env python3
"""fleet-deck-attention s3, the harness side: hooks/context-sample.py (the status line's context window use,
kept for the control agent), the status line's call of it, and session-state.py's new `reason` and `transcript`.
Scratch state directories; time is a number the test passes; the real statusline.sh is run for the call."""
from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(HERE, "runtime", "claude-code", "hooks")


def load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HOOKS, file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cs = load("context_sample", "context-sample.py")
ss = load("session_state", "session-state.py")
T0 = 1_800_000_000.0


def status_json(pct, sid="s-one-aaaa") -> dict:
    return {"session_id": sid, "context_window": {"used_percentage": pct, "context_window_size": 200000}}


class Scratch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="context-sample-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = os.path.join(self.dir, cs.FILE)

    def doc(self) -> dict:
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)["sessions"]


class Sample(unittest.TestCase):
    def test_a_whole_percentage_in_range_is_a_sample_and_is_rounded(self):
        for given, kept in ((0, 0), (41, 41), (41.4, 41), (41.6, 42), (100, 100), (0.2, 0)):
            self.assertEqual(cs.sample_of(status_json(given)), ("s-one-aaaa", kept), given)

    def test_what_is_not_a_percentage_is_no_sample(self):
        for bad in (None, True, False, "41", [41], {}, -1, 100.5, 101, float("nan"), float("inf")):
            self.assertIsNone(cs.sample_of(status_json(bad)), repr(bad))
        for bad in (None, [], "x", {"session_id": "s"}, {"session_id": "s", "context_window": None},
                    {"session_id": "s", "context_window": 7}, {"session_id": "", "context_window": {"used_percentage": 5}},
                    {"session_id": 7, "context_window": {"used_percentage": 5}}, {"context_window": {"used_percentage": 5}}):
            self.assertIsNone(cs.sample_of(bad), repr(bad))


class Record(Scratch):
    def rec(self, pct, now, sid="s-one-aaaa") -> bool:
        return cs.record(status_json(pct, sid), self.dir, now)

    def test_the_first_sample_is_written_private_with_its_time(self):
        self.assertTrue(self.rec(41, T0))
        self.assertEqual(self.doc(), {"s-one-aaaa": {"pct": 41, "at": "2027-01-15T08:00:00Z"}})
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

    def test_zero_is_written_not_skipped(self):
        self.assertTrue(self.rec(0, T0))
        self.assertEqual(self.doc()["s-one-aaaa"]["pct"], 0)

    def test_a_move_of_less_than_five_points_inside_five_minutes_writes_nothing(self):
        self.rec(41, T0)
        before = os.stat(self.path).st_mtime_ns
        self.assertFalse(self.rec(45, T0 + 10))
        self.assertFalse(self.rec(37, T0 + 299))
        self.assertEqual((self.doc()["s-one-aaaa"]["pct"], os.stat(self.path).st_mtime_ns), (41, before))

    def test_a_move_of_five_points_or_five_minutes_writes(self):
        self.rec(41, T0)
        self.assertTrue(self.rec(46, T0 + 10))
        self.assertTrue(self.rec(44, T0 + 10 + 300), "the kept sample is five minutes old")
        self.assertEqual(self.doc()["s-one-aaaa"], {"pct": 44, "at": "2027-01-15T08:05:10Z"})

    def test_a_sample_that_is_none_leaves_the_last_one_and_its_age(self):
        self.rec(41, T0)
        for bad in (None, "x", 101, -3):
            self.assertFalse(self.rec(bad, T0 + 3600), repr(bad))
        self.assertEqual(self.doc()["s-one-aaaa"], {"pct": 41, "at": "2027-01-15T08:00:00Z"})

    def test_a_clock_that_went_back_rewrites(self):
        self.rec(41, T0)
        self.assertTrue(self.rec(41, T0 - 100))

    def test_other_sessions_are_kept_and_old_ones_dropped(self):
        self.rec(10, T0 - 25 * 3600, "s-old-aaaa")
        self.rec(20, T0 - 100, "s-two-bbbb")
        self.rec(41, T0)
        self.assertEqual(sorted(self.doc()), ["s-one-aaaa", "s-two-bbbb"])

    def test_a_file_that_is_not_ours_is_replaced_not_a_failure(self):
        for junk in ("{not json", "[]", '{"sessions": 3}', ""):
            with open(self.path, "w") as fh:
                fh.write(junk)
            self.assertTrue(self.rec(41, T0), junk)
            self.assertEqual(self.doc()["s-one-aaaa"]["pct"], 41)

    def test_a_held_lock_is_not_waited_for(self):
        with open(os.path.join(self.dir, cs.FILE + ".lock"), "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            self.assertFalse(self.rec(41, T0))
        self.assertFalse(os.path.exists(self.path))


class Command(Scratch):
    def run_cmd(self, stdin: str, **env):
        e = {"PATH": os.environ["PATH"], "AGENT_FABRIC_STATE_DIR": self.dir, "HOME": self.dir, **env}
        return subprocess.run([sys.executable, os.path.join(HOOKS, "context-sample.py")], input=stdin, text=True,
                              capture_output=True, timeout=30, env=e, check=False)

    def test_garbage_in_prints_nothing_and_exits_zero(self):
        for stdin in ("", "not json", "[1]", "{}", json.dumps(status_json("high"))):
            r = self.run_cmd(stdin)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""), stdin)
        self.assertFalse(os.path.exists(self.path))

    def test_a_sample_in_is_a_file_under_the_account_state_directory(self):
        r = self.run_cmd(json.dumps(status_json(63.2)))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        login = ss.pwd.getpwuid(os.getuid()).pw_name
        path = os.path.join(self.dir, "agents", login, cs.FILE)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["sessions"]["s-one-aaaa"]["pct"], 63)


@unittest.skipUnless(shutil.which("jq") and shutil.which("timeout"), "statusline.sh needs jq and timeout, as the harness host has")
class StatusLine(Scratch):
    def draw(self, payload: dict) -> subprocess.CompletedProcess:
        env = {"PATH": os.environ["PATH"], "HOME": self.dir, "AGENT_FABRIC_STATE_DIR": self.dir,
               "XDG_CACHE_HOME": os.path.join(self.dir, "cache")}
        return subprocess.run(["bash", os.path.join(HOOKS, "statusline.sh")], input=json.dumps(payload), text=True,
                              capture_output=True, timeout=60, env=env, check=False)

    def sample_path(self) -> str:
        return os.path.join(self.dir, "agents", ss.pwd.getpwuid(os.getuid()).pw_name, cs.FILE)

    def test_drawing_the_line_keeps_the_sample_and_the_line_is_unchanged_by_it(self):
        payload = {**status_json(37), "workspace": {"current_dir": self.dir}, "model": {"display_name": "M"}, "version": "9.9.9"}
        r = self.draw(payload)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("9.9.9", r.stdout)
        with open(self.sample_path(), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["sessions"]["s-one-aaaa"]["pct"], 37)
        self.assertEqual(r.stdout, self.draw(payload).stdout)

    def test_a_line_without_a_sample_is_drawn_and_writes_nothing(self):
        r = self.draw({"workspace": {"current_dir": self.dir}, "model": {"display_name": "M"}})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.strip())
        self.assertFalse(os.path.exists(self.sample_path()))


class Hook(Scratch):
    def hook(self, event: str, sid: str = "s-one-aaaa", now: float = T0, **fields) -> bool:
        return ss.record({"hook_event_name": event, "session_id": sid, **fields}, self.dir, now, process=(4242, 7))

    def entry(self, sid: str = "s-one-aaaa") -> dict:
        with open(os.path.join(self.dir, ss.FILE), encoding="utf-8") as fh:
            return json.load(fh)["sessions"][sid]

    def test_which_event_is_which_reason(self):
        for payload, want in (
            ({"hook_event_name": "PermissionRequest"}, "permission"),
            ({"hook_event_name": "Notification", "notification_type": "permission_prompt"}, "permission"),
            ({"hook_event_name": "Notification", "notification_type": "worker_permission_prompt"}, "permission"),
            ({"hook_event_name": "Notification", "notification_type": "elicitation_dialog"}, "question"),
            ({"hook_event_name": "Notification", "notification_type": "elicitation_url_dialog"}, "question"),
            ({"hook_event_name": "Notification", "notification_type": "agent_needs_input"}, "question"),
            ({"hook_event_name": "Notification", "notification_type": "idle_prompt"}, None),
            ({"hook_event_name": "Notification", "notification_type": "auth_success"}, None),
            ({"hook_event_name": "Notification"}, None),
            ({"hook_event_name": "PreToolUse"}, None),
            ({"hook_event_name": "Stop", "notification_type": "permission_prompt"}, None),
        ):
            self.assertEqual(ss.reason_of(payload), want, payload)

    def test_a_blocked_entry_records_its_reason_and_a_working_one_none(self):
        self.hook("PermissionRequest")
        self.assertEqual(self.entry()["reason"], "permission")
        self.hook("PreToolUse", now=T0 + 5)
        self.assertNotIn("reason", self.entry())
        self.hook("Notification", now=T0 + 9, notification_type="elicitation_dialog")
        self.assertEqual((self.entry()["state"], self.entry()["reason"]), ("blocked", "question"))

    def test_a_new_reason_in_the_same_state_is_written_and_since_stays(self):
        self.hook("PermissionRequest")
        since = self.entry()["since"]
        self.assertTrue(self.hook("Notification", now=T0 + 30, notification_type="elicitation_dialog"))
        self.assertEqual((self.entry()["reason"], self.entry()["since"]), ("question", since))
        self.assertFalse(self.hook("Notification", now=T0 + 60, notification_type="elicitation_dialog"), "nothing changed")

    def test_the_transcript_path_is_kept_across_events_that_do_not_carry_one(self):
        path = "/home/x/.claude/projects/p/s.jsonl"
        self.hook("UserPromptSubmit", transcript_path=path)
        self.assertEqual(self.entry()["transcript"], path)
        self.assertFalse(self.hook("PreToolUse", now=T0 + 1), "same state: no write")
        self.hook("Stop", now=T0 + 2)
        self.assertEqual(self.entry()["transcript"], path)
        self.hook("Stop", now=T0 + 3, transcript_path="relative/s.jsonl")
        self.assertEqual(self.entry()["transcript"], path, "a path that is not absolute is not taken")

    def test_the_first_write_of_the_transcript_is_not_a_new_state(self):
        self.hook("UserPromptSubmit")
        since = self.entry()["since"]
        self.assertTrue(self.hook("PreToolUse", now=T0 + 90, transcript_path="/a/s.jsonl"))
        self.assertEqual(self.entry()["since"], since)

    def test_an_entry_without_the_new_fields_is_what_it_was(self):
        self.hook("UserPromptSubmit")
        self.assertEqual(sorted(self.entry()), ["pid", "since", "start", "state"])


class Join(Hook):
    """What the account's control agent reads is what these two write: the contract between them, end to end."""

    def test_the_rows_agentd_reads_from_what_the_hook_and_the_status_line_wrote(self):
        sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
        from control import sessions
        transcript = os.path.join(self.dir, "t.jsonl")
        with open(transcript, "w") as fh:
            fh.write("{}\n")
        self.hook("Notification", now=T0, notification_type="elicitation_dialog", transcript_path=transcript)
        cs.record(status_json(58.0), self.dir, T0)
        os.utime(transcript, (T0, T0))
        # The hook recorded process (4242, start 7); a /proc where pid 4242 started at 7 makes it the session's own.
        proc = os.path.join(self.dir, "proc")
        os.makedirs(os.path.join(proc, "4242"))
        with open(os.path.join(proc, "4242", "stat"), "w") as fh:
            fh.write("4242 (claude) " + " ".join(["S", "1", *["0"] * 17, "7", "0", "0"]) + "\n")
        rows = sessions.read_sessions(os.path.join(self.dir, ss.FILE), proc=proc, now_ms=T0 * 1000 + 1000)
        self.assertEqual(rows, [{"session": "s-one-aaaa", "state": "blocked", "since": "2027-01-15T08:00:00Z", "reason": "question",
                                 "context": {"pct": 58, "at": "2027-01-15T08:00:00Z"}, "activity": "recent"}])


if __name__ == "__main__":
    unittest.main()
