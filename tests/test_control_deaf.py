#!/usr/bin/env python3
"""A session idle with no inbox watch while work waits (tools/fabric/control/deaf.py, deaf_alarm.py; j188).

Every case runs the real section over a scratch state directory and a fake /proc whose cmdlines are written to files; nothing
reads this host's processes, relay or jobs. Each negative case has its positive control: the same account, one fact changed,
is flagged."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import deaf, deaf_alarm  # noqa: E402
from control.ops import SECTIONS, _wants  # noqa: E402
from control import ctl  # noqa: E402

NOW = 1_800_000_000.0
UID = os.getuid()


def iso(offset_s: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(NOW + offset_s, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class Scratch(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="deaf-test-")
        self.addCleanup(self._tmp.cleanup)
        self.state = os.path.join(self._tmp.name, "state")
        self.proc = os.path.join(self._tmp.name, "proc")
        os.makedirs(self.state)
        os.makedirs(self.proc)

    def log(self, *lines: dict) -> None:
        with open(os.path.join(self.state, deaf.WATCH_LOG), "w", encoding="utf-8") as fh:
            for line in lines:
                fh.write(json.dumps(line) + "\n")

    def process(self, pid: int, *argv: str) -> None:
        d = os.path.join(self.proc, str(pid))
        os.makedirs(d)
        with open(os.path.join(d, "cmdline"), "wb") as fh:
            fh.write(b"\0".join(a.encode() for a in argv) + b"\0")

    def run_section(self, *, online: bool = True, since: str | None = None, unread: int = 0, queued_requests: int = 0,
                    inbox: dict | None = None, jobs: dict | None = None) -> dict:
        # the sender half's job (jobs-add, source "owner"): what a deaf account's list holds for a REQUEST that came after its watch died
        job_list = [{"id": f"j{i}", "state": "queued", "source": "owner", "title": f"do it (REQUEST 01a2180d-ab5f-7fd1-82dd-a3347d5076f{i})"}
                    for i in range(queued_requests)]
        ctx = {"deaf_opts": {"now": NOW, "state": self.state, "uid": UID, "proc": self.proc,
                             "is_watch": lambda argv: "gzcoord-inbox" in os.path.basename(argv[0]) and "--until-delivery" in argv}}
        return deaf.section(ctx, presence=lambda: {"status": "ok", "online": online, "sessions": int(online), "since": since},
                            inbox=lambda: inbox if inbox is not None else {"status": "ok", "source": "interweave", "unread": unread},
                            jobs=lambda: jobs if jobs is not None else {"status": "ok", "jobs": job_list})


END5 = {"event": "end", "pid": 11, "reason": "gave-up", "code": 5}


class Section(Scratch):
    def test_watch_ended_code_5_with_a_queued_request_is_deaf(self) -> None:
        self.log({"t": iso(-3600), "event": "start", "pid": 11}, {**END5, "t": iso(-3000)})
        r = self.run_section(queued_requests=1)
        self.assertEqual((r["status"], r["deaf"], r["watch"], r["pending"]), ("ok", True, "end code 5 (gave-up)", {"unread": 0, "queued_requests": 1}))
        self.assertEqual(r["age_s"], 3000)
        self.assertEqual(r["episode"], f"end@{iso(-3000)}")

    def test_any_end_code_counts(self) -> None:
        self.log({"t": iso(-3000), "event": "end", "pid": 11, "reason": "delivery", "code": 0})
        self.assertTrue(self.run_section(unread=2)["deaf"])

    def test_a_start_with_no_end_and_no_live_watch_is_deaf(self) -> None:
        # the watch was killed outright: it writes no end line, so the process table is what says it is gone
        self.log({"t": iso(-4000), "event": "start", "pid": 11})
        r = self.run_section(unread=1)
        self.assertTrue(r["deaf"])
        self.assertEqual(r["watch"], "start, no live watch (pid 11)")

    def test_a_live_watch_is_not_deaf(self) -> None:
        self.log({"t": iso(-4000), "event": "start", "pid": 11})
        self.assertTrue(self.run_section(unread=1)["deaf"])   # the control
        self.process(11, "gzcoord-inbox", "--until-delivery")
        r = self.run_section(unread=1, queued_requests=1)
        self.assertEqual((r["deaf"], r["why"]), (False, "a watch runs"))

    def test_another_login_s_watch_is_not_ours(self) -> None:
        self.log({"t": iso(-4000), "event": "start", "pid": 11})
        self.process(11, "gzcoord-inbox", "--until-delivery")
        real = os.stat
        other = os.getuid() + 1
        orig = deaf.os.stat

        class Stat:
            def __init__(self, st): self.st_uid = other
        deaf.os.stat = lambda p, *a, **k: Stat(real(p)) if str(p).startswith(self.proc) else orig(p, *a, **k)
        self.addCleanup(setattr, deaf.os, "stat", orig)
        self.assertTrue(self.run_section(unread=1)["deaf"])

    def test_no_work_waiting_is_not_alarmed(self) -> None:
        self.log({**END5, "t": iso(-3000)})
        r = self.run_section(unread=0, queued_requests=0)
        self.assertEqual((r["deaf"], r["why"]), (False, "no work is waiting"))
        self.assertTrue(self.run_section(unread=1)["deaf"])   # the control

    def test_the_relay_s_channel_wide_unread_is_not_this_accounts_work(self) -> None:
        # drift.inbox counts every message of the channel past the cursor, which a dead watch stops: busy channel, "unread" for all
        self.log({**END5, "t": iso(-3000)})
        relay = {"status": "ok", "unread": 40, "capped": True}
        # nothing but the channel-wide count: not "no work" (a REQUEST from a non-operator leaves no job) and not deaf: unknown
        r = self.run_section(inbox=relay)
        self.assertEqual(r["status"], "unknown")
        self.assertIn("channel-wide", r["reason"])
        r = self.run_section(inbox={"status": "ok", "unread": 0})   # a relay reading of nothing unread is "no work"
        self.assertEqual((r["deaf"], r["why"]), (False, "no work is waiting"))
        r = self.run_section(inbox=relay, queued_requests=1)   # the control: a queued REQUEST job is this account's own work
        self.assertEqual((r["deaf"], r["pending"]), (True, {"unread": None, "queued_requests": 1}))

    def test_a_reader_that_raises_is_unknown_with_its_reason(self) -> None:
        self.log({**END5, "t": iso(-3000)})
        ctx = {"deaf_opts": {"now": NOW, "state": self.state}}
        pres = lambda: {"status": "ok", "online": True, "since": None}  # noqa: E731

        def boom():
            raise OSError("relay unreachable")
        for kw in ({"inbox": boom, "jobs": lambda: {"status": "ok", "jobs": []}}, {"inbox": lambda: {"status": "ok", "unread": 0}, "jobs": boom}):
            r = deaf.section(ctx, presence=pres, **kw)
            self.assertEqual(r["status"], "unknown")
            self.assertIn("relay unreachable", r["reason"])

    def test_the_op_wires_each_reader_to_its_own_section(self) -> None:
        from unittest import mock
        from control import ops
        self.log({**END5, "t": iso(-3000)})
        ctx = {"root": HERE, "deaf_opts": {"now": NOW, "state": self.state, "uid": UID, "proc": self.proc, "is_watch": lambda argv: False}}
        with mock.patch.object(ops, "presence", lambda **k: {"status": "ok", "online": True, "since": None}), \
                mock.patch.object(ops, "_inbox", lambda c: {"status": "ok", "source": "interweave", "unread": 3}), \
                mock.patch.object(ops, "_jobs", lambda c: {"status": "ok", "jobs": []}):
            got = ops.collect("deaf", ctx)["deaf"]
        # a swap of the inbox and jobs readers would read the jobs dict as an inbox: unknown, not these counts
        self.assertEqual((got["deaf"], got["pending"]), (True, {"unread": 3, "queued_requests": 0}))

    def test_a_request_job_counts_whatever_its_source_and_a_marker_in_the_middle_does_not(self) -> None:
        self.log({**END5, "t": iso(-3000)})
        req = "(REQUEST 01a2180d-ab5f-7fd1-82dd-a3347d5076f8)"
        for source in ("owner", "request"):
            jobs = {"status": "ok", "jobs": [{"id": "j1", "state": "queued", "source": source, "title": f"x {req}"}]}
            self.assertTrue(self.run_section(jobs=jobs)["deaf"], source)
        jobs = {"status": "ok", "jobs": [{"id": "j1", "state": "queued", "source": "owner", "title": f"x {req} and more"}]}
        self.assertFalse(self.run_section(jobs=jobs)["deaf"])

    def test_a_queued_job_that_is_not_from_a_request_is_not_work(self) -> None:
        self.log({**END5, "t": iso(-3000)})
        req = "(REQUEST 01a2180d-ab5f-7fd1-82dd-a3347d5076f8)"
        jobs = {"status": "ok", "jobs": [{"id": "j1", "state": "queued", "source": "self", "title": "a plain job"},
                                          {"id": "j2", "state": "active", "source": "request", "title": f"taken {req}"}]}
        self.assertFalse(self.run_section(jobs=jobs)["deaf"])

    def test_under_ten_minutes_is_not_deaf_and_over_is(self) -> None:
        self.log({**END5, "t": iso(-deaf.MIN_AGE_S)})
        self.assertFalse(self.run_section(unread=1)["deaf"])
        self.log({**END5, "t": iso(-deaf.MIN_AGE_S - 1)})
        self.assertTrue(self.run_section(unread=1)["deaf"])

    def test_a_session_newer_than_the_line_starts_the_clock_at_its_own_start(self) -> None:
        self.log({**END5, "t": iso(-9000)})
        self.assertFalse(self.run_section(unread=1, since=iso(-60))["deaf"])
        self.assertTrue(self.run_section(unread=1, since=iso(-700))["deaf"])

    def test_no_session_no_line_are_not_deaf(self) -> None:
        self.log({**END5, "t": iso(-3000)})
        self.assertEqual(self.run_section(online=False, unread=1)["why"], "no session runs")
        os.unlink(os.path.join(self.state, deaf.WATCH_LOG))
        self.assertEqual(self.run_section(unread=1)["why"], "no watch log line yet")

    def test_what_cannot_be_read_is_unknown_never_not_deaf(self) -> None:
        self.log({**END5, "t": iso(-3000)})
        for kw in ({"inbox": {"status": "failed"}}, {"inbox": {"status": "unknown"}}, {"jobs": {"status": "failed", "error": "x"}}):
            r = self.run_section(**kw)
            self.assertEqual(r["status"], "unknown", kw)
            self.assertNotIn("deaf", r)
        self.assertTrue(self.run_section(unread=1)["deaf"])   # the control: the same log, work readable
        self.assertEqual(self.run_section(unread=1, since=None, online=True)["status"], "ok")
        ctx = {"deaf_opts": {"now": NOW, "state": self.state}}
        self.assertEqual(deaf.section(ctx, presence=lambda: {"status": "failed"}, inbox=lambda: {}, jobs=lambda: {})["status"], "unknown")

    def test_a_log_that_cannot_be_read_is_unknown(self) -> None:
        os.mkdir(os.path.join(self.state, deaf.WATCH_LOG))   # a directory: open() raises IsADirectoryError, not FileNotFoundError
        r = self.run_section(unread=1)
        self.assertEqual(r["status"], "unknown")

    def test_a_torn_last_line_is_skipped_for_the_one_before(self) -> None:
        self.log({**END5, "t": iso(-3000)})
        with open(os.path.join(self.state, deaf.WATCH_LOG), "a", encoding="utf-8") as fh:
            fh.write('{"t": "2026-11-2')
        self.assertTrue(self.run_section(unread=1)["deaf"])

    def test_a_watch_after_the_end_is_the_newer_episode(self) -> None:
        self.log({**END5, "t": iso(-3000)}, {"t": iso(-100), "event": "start", "pid": 12})
        self.process(12, "gzcoord-inbox", "--until-delivery")
        self.assertFalse(self.run_section(unread=1)["deaf"])

    def test_a_process_table_that_cannot_be_read_is_unknown_not_no_watch(self) -> None:
        self.log({"t": iso(-4000), "event": "start", "pid": 11})
        self.assertTrue(self.run_section(unread=1)["deaf"])   # the control: a readable table with no watch
        ctx = {"deaf_opts": {"now": NOW, "state": self.state, "uid": UID, "proc": os.path.join(self.proc, "absent"), "is_watch": lambda argv: False}}
        r = deaf.section(ctx, presence=lambda: {"status": "ok", "online": True, "since": None},
                         inbox=lambda: {"status": "ok", "unread": 1}, jobs=lambda: {"status": "ok", "jobs": []})
        self.assertEqual(r["status"], "unknown")

    def test_the_real_predicate_reads_a_fake_proc(self) -> None:
        self.process(21, "/usr/bin/python3", "/x/bin/gzcoord-inbox", "--until-delivery")
        is_watch = deaf.load_is_watch(HERE)
        self.assertTrue(deaf.live_watch(UID, is_watch, self.proc))
        os.rename(os.path.join(self.proc, "21"), os.path.join(self.proc, "22"))
        with open(os.path.join(self.proc, "22", "cmdline"), "wb") as fh:
            fh.write(b"grep\0gzcoord-inbox --until-delivery\0")   # one argument holding a space is not a watch
        self.assertFalse(deaf.live_watch(UID, is_watch, self.proc))

    def test_the_section_is_registered_and_in_status(self) -> None:
        self.assertIn("deaf", SECTIONS)
        self.assertIn("deaf", _wants("status"))
        self.assertEqual(_wants("deaf"), ["deaf"])


def row(account: str, episode: str | None, status: str = "ok", deaf_status: str = "ok") -> dict:
    d: dict = {"status": deaf_status}
    if deaf_status == "ok":
        d.update(deaf=episode is not None, why="x")
        if episode:
            d.update(episode=episode, watch="end code 5 (gave-up)", age_s=3000, since="2026-11-26T10:00:00Z", pending={"unread": 1, "queued_requests": 1})
    return {"account": account, "host": "h", "status": status, "deaf": d}


class Alarm(unittest.TestCase):
    def poll(self, rows: list[dict], ledger: dict, sent: list, fail: set = frozenset(), dry_run: bool = False):
        def send_one(account, d, to):
            if account in fail:
                raise RuntimeError("relay down")
            sent.append((account, to, d["episode"]))
        return deaf_alarm.alarm(rows, ledger, "h/user", dry_run, send_one)

    def test_one_message_per_episode_not_per_poll(self) -> None:
        sent: list = []
        ledger, said, failed = self.poll([row("a", "end@1"), row("b", None)], {}, sent)
        self.assertEqual((sent, failed, ledger), ([("a", "h/user", "end@1")], [], {"a": "end@1"}))
        for _ in range(3):   # the same deafness on later polls
            ledger, said, failed = self.poll([row("a", "end@1"), row("b", None)], ledger, sent)
            self.assertEqual(said, [])
        self.assertEqual(len(sent), 1)

    def test_a_new_episode_is_a_new_message_and_a_recovery_clears_the_ledger(self) -> None:
        sent: list = []
        ledger, _, _ = self.poll([row("a", "end@1")], {}, sent)
        ledger, _, _ = self.poll([row("a", "end@2")], ledger, sent)
        self.assertEqual([s[2] for s in sent], ["end@1", "end@2"])
        ledger, _, _ = self.poll([row("a", None)], ledger, sent)
        self.assertEqual(ledger, {})
        ledger, _, _ = self.poll([row("a", "end@2")], ledger, sent)   # even the same line, after a recovery, is said again
        self.assertEqual(len(sent), 3)

    def test_unknown_and_unanswered_keep_the_entry(self) -> None:
        sent: list = []
        ledger = {"a": "end@1", "b": "end@1"}
        ledger, said, _ = self.poll([row("a", None, deaf_status="unknown"), row("b", None, status="no answer")], ledger, sent)
        self.assertEqual(ledger, {"a": "end@1", "b": "end@1"})
        ledger, said, _ = self.poll([row("a", "end@1"), row("b", "end@1")], ledger, sent)
        self.assertEqual((sent, said), ([], []))   # back, same episode: not said again

    def test_a_failed_send_is_not_recorded_and_the_others_go(self) -> None:
        sent: list = []
        ledger, said, failed = self.poll([row("a", "end@1"), row("b", "end@1")], {}, sent, fail={"a"})
        self.assertEqual((ledger, [s[0] for s in sent], len(failed)), ({"b": "end@1"}, ["b"], 1))
        ledger, said, failed = self.poll([row("a", "end@1"), row("b", "end@1")], ledger, sent)
        self.assertEqual([s[0] for s in sent], ["b", "a"])   # the retry sends a, never b again

    def test_dry_run_sends_and_records_nothing(self) -> None:
        sent: list = []
        ledger, said, _ = self.poll([row("a", "end@1")], {}, sent, dry_run=True)
        self.assertEqual((sent, ledger, len(said)), ([], {}, 1))

    def test_ledger_round_trip_and_a_corrupt_one_is_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="deaf-test-") as d:
            path = os.path.join(d, "sub", deaf_alarm.LEDGER)
            self.assertEqual(deaf_alarm.read_ledger(path), {})
            deaf_alarm.write_ledger(path, {"a": "end@1"})
            self.assertEqual(deaf_alarm.read_ledger(path), {"a": "end@1"})
            self.assertEqual(os.listdir(os.path.dirname(path)), [deaf_alarm.LEDGER])   # no temp file left
            with open(path, "w") as fh:
                fh.write("[1]")
            with self.assertRaises(ValueError):
                deaf_alarm.read_ledger(path)

    def test_send_composes_then_sends_one_info_with_the_facts(self) -> None:
        calls: list = []

        def run(argv, **kw):
            calls.append(argv)
            if argv[0] == "gzcoord-compose":
                with open(argv[argv.index("-o") + 1], "w") as fh:
                    fh.write("[GZCOORD/1] INFO\nTO: h/user\nSUBJECT: s\n\nCONTEXT:\n\nNOTES:\n\nREFERENCES:\n")
            else:
                with open(argv[1]) as fh:
                    self.sent_text = fh.read()
            self.assertEqual(kw["timeout"] > 0 and kw["stdin"], subprocess.DEVNULL)
            return subprocess.CompletedProcess(argv, 0, "", "")
        d = row("a", "end@1")["deaf"]
        deaf_alarm.send("a", d, "h/user", run)
        self.assertEqual([c[0] for c in calls], ["gzcoord-compose", "gzcoord-send"])
        self.assertIn("end code 5 (gave-up)", self.sent_text)
        self.assertIn("1 unread message(s) of its own and 1 queued job(s)", self.sent_text)
        self.assertFalse(os.path.exists(calls[1][1]))   # the scratch file is gone

    def test_a_send_that_exited_3_is_posted_again_as_the_same_file(self) -> None:
        # j190: exit 3 may mean "the carrier delivered it"; a fresh compose would be a second message with a new id
        composed, posted = [], []
        fail = [True]

        def run(argv, **kw):
            if argv[0] == "gzcoord-compose":
                composed.append(1)
                with open(argv[argv.index("-o") + 1], "w") as fh:
                    fh.write("[GZCOORD/1] INFO\nTO: h/user\nSUBJECT: s\n\nCONTEXT:\n\nNOTES:\n\nREFERENCES:\n")
                return subprocess.CompletedProcess(argv, 0, "", "")
            with open(argv[1]) as fh:
                posted.append((argv[1], fh.read()))
            if fail[0]:
                with open(argv[1], "a") as fh:
                    fh.write("MESSAGE-ID: written-by-send\n")   # what gzcoord-send does before it posts
            return subprocess.CompletedProcess(argv, 3 if fail[0] else 0, "", "carrier took it")
        d = row("a", "end@1")["deaf"]
        with tempfile.TemporaryDirectory(prefix="deaf-test-") as pend:
            with self.assertRaises(RuntimeError):
                deaf_alarm.send("a", d, "h/user", run, pend)
            fail[0] = False
            deaf_alarm.send("a", d, "h/user", run, pend)
            self.assertEqual(len(composed), 1)
            self.assertIn("written-by-send", posted[1][1])
            self.assertEqual(posted[0][0], posted[1][0])
            self.assertEqual(os.listdir(pend), [])
            fail[0] = True
            with self.assertRaises(RuntimeError):
                deaf_alarm.send("a", d, "h/user", run, pend)
            with self.assertRaises(RuntimeError):
                deaf_alarm.send("a", row("a", "end@2")["deaf"], "h/user", run, pend)   # new episode: composed anew
            self.assertEqual(len(composed), 3)
            self.assertEqual(len(os.listdir(pend)), 1)   # the old episode's file is gone

    def test_a_send_that_provably_sent_nothing_is_composed_anew_next_time(self) -> None:
        # review of #718, F1: exit 4 (a TO no host places) keeps no file, so a corrected --to is used
        codes = iter([4, 0])

        def run(argv, **kw):
            if argv[0] == "gzcoord-compose":
                with open(argv[argv.index("-o") + 1], "w") as fh:
                    fh.write("[GZCOORD/1] INFO\nTO: x\nSUBJECT: s\n\nCONTEXT:\n\nNOTES:\n\nREFERENCES:\n")
                return subprocess.CompletedProcess(argv, 0, "", "")
            return subprocess.CompletedProcess(argv, next(codes), "", "")
        d = row("a", "end@1")["deaf"]
        with tempfile.TemporaryDirectory(prefix="deaf-test-") as pend:
            with self.assertRaises(RuntimeError):
                deaf_alarm.send("a", d, "bad", run, pend)
            self.assertEqual(os.listdir(pend), [])
            deaf_alarm.send("a", d, "good", run, pend)
            self.assertEqual(os.listdir(pend), [])   # a first send that succeeds keeps nothing

    def test_a_repost_after_exit_3_is_never_composed_anew_by_a_later_failure(self) -> None:
        # review of #718, F3: exit 3 then 4 then 0 must post one id three times, never a second message
        codes = iter([3, 4, 0])
        composed, ids = [], []

        def run(argv, **kw):
            if argv[0] == "gzcoord-compose":
                composed.append(1)
                with open(argv[argv.index("-o") + 1], "w") as fh:
                    fh.write("[GZCOORD/1] INFO\nTO: h/user\nSUBJECT: s\n\nCONTEXT:\n\nNOTES:\n\nREFERENCES:\n")
                return subprocess.CompletedProcess(argv, 0, "", "")
            with open(argv[1], "a") as fh:
                fh.write(f"MESSAGE-ID: id-{len(composed)}\n") if "MESSAGE-ID" not in open(argv[1]).read() else None
            ids.append(open(argv[1]).read().count("MESSAGE-ID"))
            return subprocess.CompletedProcess(argv, next(codes), "", "")
        d = row("a", "end@1")["deaf"]
        with tempfile.TemporaryDirectory(prefix="deaf-test-") as pend:
            for _ in range(2):
                with self.assertRaises(RuntimeError):
                    deaf_alarm.send("a", d, "h/user", run, pend)
            deaf_alarm.send("a", d, "h/user", run, pend)
            self.assertEqual(len(composed), 1)
            self.assertEqual(os.listdir(pend), [])

    def test_a_kept_file_for_another_addressee_is_composed_anew(self) -> None:
        composed = []

        def run(argv, **kw):
            if argv[0] == "gzcoord-compose":
                composed.append(argv[argv.index("--to") + 1])
                with open(argv[argv.index("-o") + 1], "w") as fh:
                    fh.write(f"[GZCOORD/1] INFO\nTO: {composed[-1]}\nSUBJECT: s\n\nCONTEXT:\n\nNOTES:\n\nREFERENCES:\n")
                return subprocess.CompletedProcess(argv, 0, "", "")
            return subprocess.CompletedProcess(argv, 3, "", "")
        d = row("a", "end@1")["deaf"]
        with tempfile.TemporaryDirectory(prefix="deaf-test-") as pend:
            for to in ("old/x", "new/x"):
                with self.assertRaises(RuntimeError):
                    deaf_alarm.send("a", d, to, run, pend)
            self.assertEqual(composed, ["old/x", "new/x"])
            self.assertEqual(len(os.listdir(pend)), 1)

    def test_an_unremovable_pending_file_is_a_failure_not_a_traceback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="deaf-test-") as pend:
            open(deaf_alarm.pending_path(pend, "a", "end@1"), "w").close()
            real = deaf_alarm.drop_pending

            def boom(*a):
                raise PermissionError("denied")
            deaf_alarm.drop_pending = boom
            try:
                new, _, failed = deaf_alarm.alarm([row("a", None)], {"a": "end@1"}, "h/user", False, lambda *a: None, pend)
            finally:
                deaf_alarm.drop_pending = real
            self.assertEqual(new, {})
            self.assertIn("denied", failed[0])

    def test_a_pending_file_another_run_removed_first_is_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory(prefix="deaf-test-") as pend:
            gone = os.path.basename(deaf_alarm.pending_path(pend, "a", "end@1"))
            real = os.listdir
            deaf_alarm.os.listdir = lambda p: [gone]   # listed, then taken by the other run before the unlink
            try:
                deaf_alarm.drop_pending(pend, "a")
            finally:
                deaf_alarm.os.listdir = real

    def test_a_recovered_account_drops_its_pending_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="deaf-test-") as pend:
            kept = deaf_alarm.pending_path(pend, "a", "end@1")
            other = deaf_alarm.pending_path(pend, "b", "end@1")
            for f in (kept, other):
                open(f, "w").close()
            deaf_alarm.alarm([row("a", None)], {"a": "end@1"}, "h/user", True, lambda *a: None, pend)
            self.assertTrue(os.path.exists(kept))   # a dry run changes nothing
            deaf_alarm.alarm([row("a", None)], {"a": "end@1"}, "h/user", False, lambda *a: None, pend)
            self.assertFalse(os.path.exists(kept))
            self.assertTrue(os.path.exists(other))

    def test_the_text_says_only_what_was_counted(self) -> None:
        d = {**row("a", "end@1")["deaf"], "pending": {"unread": None, "queued_requests": 2}}
        context, _ = deaf_alarm.body("a", d)
        self.assertIn("work waits for it: 2 queued job(s) taken from a REQUEST.", context)
        self.assertNotIn("unread", context)

    def test_send_failure_names_the_command(self) -> None:
        run = lambda argv, **kw: subprocess.CompletedProcess(argv, 3, "", "relay unreachable")  # noqa: E731
        with self.assertRaisesRegex(RuntimeError, "gzcoord-compose exited 3: relay unreachable"):
            deaf_alarm.send("a", row("a", "end@1")["deaf"], "h/user", run)

    def test_the_rows_of_the_real_fabric_ctl_output_are_read(self) -> None:
        # what `fabric-ctl all deaf --json` prints: ctl.rows, one JSON object per line (ctl.main), not one list
        expected = [{"login": "a", "host": "h", "address": "h/a"}, {"login": "b", "host": "h", "address": "h/b"}, {"login": "c", "host": "h", "address": "h/c"}]
        deaf_data = row("a", "end@1")["deaf"]
        replies = [{"from": "h/a", "data": {"deaf": deaf_data}}, {"from": "h/b", "data": {"deaf": row("b", None)["deaf"]}}]
        out = "\n".join(ctl.js.stringify(r) for r in ctl.rows(expected, replies)) + "\n"
        run = lambda rc: (lambda argv, **kw: subprocess.CompletedProcess(argv, rc, out, "c did not answer"))  # noqa: E731
        for rc in (0, 1):   # exit 1 is what ctl returns when an account did not answer; the rows are still the answer
            rows = deaf_alarm.read_rows(run(rc))
            self.assertEqual([r["account"] for r in rows], ["a", "b", "c"], rc)
        self.assertEqual(deaf_alarm.episode_of(rows[0])[0], "end@1")   # the key the alarm needs survived ctl.rows
        self.assertEqual(rows[2]["status"], "no answer")
        sent: list = []
        new, said, failed = deaf_alarm.alarm(rows, {"c": "end@0"}, "h/user", False, lambda a, d, to: sent.append(a))
        self.assertEqual((sent, new), (["a"], {"a": "end@1", "c": "end@0"}))   # the silent account's entry kept

    def test_reading_the_accounts_distinguishes_failures(self) -> None:
        ok = json.dumps(row("a", None))
        mk = lambda out, rc=0: (lambda argv, **kw: subprocess.CompletedProcess(argv, rc, out, "boom"))  # noqa: E731
        self.assertEqual(deaf_alarm.read_rows(mk(ok + "\n"))[0]["account"], "a")
        for bad in (mk("", 1), mk("", 0), mk("not json\n"), mk("[1]\n"), mk("{\"a\": 1}\n"), mk(ok, 2), mk(ok, 3)):
            with self.assertRaises(RuntimeError):
                deaf_alarm.read_rows(bad)

        def hang(argv, **kw):
            raise subprocess.TimeoutExpired(argv, 1)
        with self.assertRaises(RuntimeError):
            deaf_alarm.read_rows(hang)


class Table(unittest.TestCase):
    def test_status_cell_and_verb(self) -> None:
        cell = ctl._deaf_cell(row("a", "end@1")["deaf"])
        self.assertIn("DEAF 50 min", cell)
        self.assertIn("end code 5 (gave-up)", cell)
        self.assertEqual(ctl._deaf_cell(row("a", None)["deaf"]), "")
        self.assertEqual(ctl._deaf_cell(None), "")
        only = ctl._deaf_cell({**row("a", "end@1")["deaf"], "pending": {"unread": None, "queued_requests": 2}})
        self.assertIn("2 queued REQUEST", only)
        self.assertNotIn("unread", only)   # not counted, so not said (the relay's reading is channel-wide)
        self.assertIn("deaf ? (inbox: failed)", ctl._deaf_cell({"status": "unknown", "reason": "inbox: failed"}))
        self.assertIn("deaf ? (boom)", ctl._deaf_cell({"status": "failed", "error": "boom"}))
        text = ctl.table("deaf", [row("a", "end@1"), row("b", None), row("c", None, status="no answer")])
        self.assertIn("DEAF", text.split("\n")[1])
        self.assertIn("no (x)", text.split("\n")[2])
        self.assertIn("deaf", [v.name for v in ctl.VERBS])
        # the status verb's own row carries it, beside the harness and inbox cells
        self.assertIn("DEAF 50 min", ctl._drift_cells({"account": "a", "deaf": row("a", "end@1")["deaf"]}))
        self.assertNotIn("DEAF", ctl._drift_cells({"account": "a", "deaf": row("a", None)["deaf"]}))


class Cli(unittest.TestCase):
    def test_exit_3_when_the_accounts_cannot_be_read_and_nothing_is_written(self) -> None:
        with tempfile.TemporaryDirectory(prefix="deaf-test-") as d:
            env = {"PATH": d, "HOME": d, "AGENT_FABRIC_STATE_DIR": os.path.join(d, "state")}   # no fabric-ctl on PATH
            r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "tools", "fabric", "control", "deaf_alarm.py"), "--to", "h/user"],
                               env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 3, r.stderr)
            self.assertIn("deaf_alarm:", r.stderr)
            self.assertFalse(os.path.exists(os.path.join(d, "state", deaf_alarm.LEDGER)))

    def test_main_keeps_the_message_across_runs_so_a_resend_is_the_same_file(self) -> None:
        # review of #718, F2: the wiring in main, through fakes on PATH (the real entry point, nothing mocked in-process)
        with tempfile.TemporaryDirectory(prefix="deaf-test-") as d:
            bindir, state = os.path.join(d, "bin"), os.path.join(d, "state")
            os.makedirs(bindir)
            rowjson = json.dumps({"account": "a", "status": "ok", "deaf": row("a", "end@1")["deaf"]})
            scripts = {
                "fabric-ctl": f"#!/bin/sh\nprintf '%s\\n' '{rowjson}'\n",
                "gzcoord-compose": '#!/bin/sh\nwhile [ $# -gt 0 ]; do [ "$1" = -o ] && out=$2; shift; done\n'
                                   "echo c >> \"$0.count\"\n"
                                   "printf '[GZCOORD/1] INFO\\nTO: h/user\\nSUBJECT: s\\n\\nCONTEXT:\\n\\nNOTES:\\n\\nREFERENCES:\\n' > \"$out\"\n",
                "gzcoord-send": f'#!/bin/sh\ncat "$1" > "{d}/posted.$$"\nexit 3\n',
            }
            for name, text in scripts.items():
                with open(os.path.join(bindir, name), "w") as fh:
                    fh.write(text)
                os.chmod(os.path.join(bindir, name), 0o755)
            env = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": d, "AGENT_FABRIC_STATE_DIR": state}
            cmd = [sys.executable, "-I", os.path.join(HERE, "tools", "fabric", "control", "deaf_alarm.py"), "--to", "h/user"]
            for _ in range(2):
                r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
                self.assertEqual(r.returncode, 3, r.stderr)
                self.assertIn("not confirmed sent", r.stderr)
            with open(os.path.join(bindir, "gzcoord-compose.count")) as fh:
                self.assertEqual(len(fh.read().split()), 1)   # composed once, posted twice
            found = [os.path.join(root, f) for root, _, files in os.walk(state) for f in files]
            self.assertEqual([os.path.basename(os.path.dirname(f)) for f in found], [deaf_alarm.PENDING])   # one kept file, no ledger

SID = "0b1c2d3e-aaaa-bbbb-cccc-1234567890ab"


def rec(kind: str, content, stop: str | None = None, **more) -> dict:
    msg: dict = {"role": kind, "content": content}
    if stop:
        msg["stop_reason"] = stop
    return {"type": kind, "message": msg, **more}


ENDED = [rec("user", "go"), rec("assistant", [{"type": "text", "text": "done"}], "end_turn"), {"type": "attachment"}]
PENDING_TOOL = [rec("user", "go"), rec("assistant", [{"type": "tool_use", "id": "t1", "name": "Agent", "input": {}}], "tool_use")]


class Idle(Scratch):
    """j1061: the idle gate, over a real transcript file under a scratch home; the age is the file's mtime."""

    def transcript(self, records: list, age_s: float = 3600, binding: bool = True) -> str:
        self.home = os.path.join(self._tmp.name, "home")
        d = os.path.join(self.home, ".claude", "projects", "-some-copy")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, SID + ".jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")
        os.utime(path, (NOW - age_s, NOW - age_s))
        self.session = SID if binding else None
        return path

    def idle(self, **kw):
        return deaf.idle_of(lambda: getattr(self, "session", None), getattr(self, "home", os.path.join(self._tmp.name, "home")), NOW, **kw)

    def test_an_ended_turn_in_a_quiet_transcript_is_idle(self) -> None:
        self.transcript(ENDED)
        self.assertEqual(self.idle()[0], True)

    def test_a_pending_tool_use_is_not_idle_and_its_result_makes_it_idle_again(self) -> None:
        self.transcript(PENDING_TOOL)   # the prompt case: held at the dispatch guard
        r = self.idle()
        self.assertEqual(r[0], False)
        self.assertIn("pending", r[1])
        answered = PENDING_TOOL + [rec("user", [{"type": "tool_result", "tool_use_id": "t1", "content": "x"}]),
                                   rec("assistant", [{"type": "text", "text": "ok"}], "end_turn")]
        self.transcript(answered)   # positive control: one fact changed
        self.assertEqual(self.idle()[0], True)

    def test_a_tool_use_in_an_earlier_record_still_pending_is_not_idle(self) -> None:
        # a later end_turn record does not clear a call that never got its result
        self.transcript(PENDING_TOOL + [rec("assistant", [{"type": "text", "text": "x"}], "end_turn")])
        self.assertEqual(self.idle()[0], False)

    def test_a_recent_write_or_an_unanswered_prompt_is_a_turn(self) -> None:
        self.transcript(ENDED, age_s=30)
        self.assertEqual(self.idle()[0], False)
        self.transcript(ENDED + [rec("user", [{"type": "tool_result", "tool_use_id": "zz", "content": "x"}])])
        self.assertEqual(self.idle()[0], False)

    def test_what_cannot_be_read_is_unknown_never_idle(self) -> None:
        self.assertEqual(self.idle()[0], "unknown")   # no binding, no transcript
        self.transcript(ENDED, binding=False)
        self.assertEqual(self.idle()[0], "unknown")
        path = self.transcript([])
        with open(path, "w") as fh:
            fh.write("not json\n{\n")
        self.assertEqual(self.idle()[0], "unknown")   # no assistant record
        self.transcript(ENDED)
        os.chmod(path, 0)
        try:
            if os.access(path, os.R_OK):
                self.skipTest("runs as a user that reads any file")
            self.assertEqual(self.idle()[0], "unknown")
        finally:
            os.chmod(path, 0o600)
        self.assertEqual(self.idle()[0], True)

    def test_the_section_carries_idle_and_why_only_when_deaf(self) -> None:
        self.transcript(PENDING_TOOL)
        self.log({"t": iso(-3600), "event": "start", "pid": 11}, {**END5, "t": iso(-3000)})
        ctx = {"deaf_opts": {"now": NOW, "state": self.state, "uid": UID, "proc": self.proc, "home": self.home, "session": lambda: SID, "is_watch": lambda a: False}}
        sec = deaf.section(ctx, presence=lambda: {"status": "ok", "online": True, "sessions": 1, "since": None},
                           inbox=lambda: {"status": "ok", "source": "interweave", "unread": 0},
                           jobs=lambda: {"status": "ok", "jobs": [{"id": "j1", "state": "queued", "title": "x (REQUEST 01a2180d-ab5f-7fd1-82dd-a3347d5076f0)"}]})
        self.assertEqual((sec["deaf"], sec["idle"]), (True, False))
        self.assertIn("pending", sec["idle_why"])


class Restart(unittest.TestCase):
    """j1061: deaf_alarm restarts a deaf AND idle account, recording before acting."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="deaf-test-")
        self.addCleanup(self._tmp.cleanup)
        self.path = os.path.join(self._tmp.name, "state", deaf_alarm.RESTART_LEDGER)
        self.now = NOW
        self.calls: list = []

    def idle_row(self, account="a", episode="end@1", idle=True, why="the last assistant turn ended") -> dict:
        r = row(account, episode)
        r["deaf"].update(idle=idle, idle_why=why)
        return r

    def restarter(self, own="me", ctl=None) -> deaf_alarm.Restarter:
        def default(account):
            self.calls.append(account)
            return "restarted", ""
        return deaf_alarm.Restarter(self.path, own, ctl=ctl or default, clock=lambda: self.now)

    def poll(self, rows, ledger, rs, sent):
        return deaf_alarm.alarm(rows, ledger, "h/user", False, lambda a, d, t: sent.append((a, d)), None, rs)

    def test_an_idle_deaf_account_is_restarted_once_per_episode_and_the_info_says_so(self) -> None:
        rs, sent = self.restarter(), []
        ledger, said, failed = self.poll([self.idle_row()], {}, rs, sent)
        self.assertEqual((self.calls, failed), (["a"], []))
        self.assertEqual(ledger, {"a": "end@1" + deaf_alarm.RESTART_TAG})
        self.assertIn("restarted", sent[0][1]["action"])
        self.assertIn("was run: restarted", deaf_alarm.body("a", sent[0][1])[1])
        ledger2, said2, _ = self.poll([self.idle_row()], ledger, self.restarter(), sent)   # the next poll, a fresh process
        self.assertEqual((self.calls, len(sent), said2), (["a"], 1, []))
        _, _, _ = self.poll([self.idle_row(episode="end@2")], ledger2, self.restarter(), sent)   # positive control: a new episode restarts
        self.assertEqual(self.calls, ["a", "a"])

    def test_the_ledger_holds_the_attempt_before_the_restart_runs_and_when_it_raises(self) -> None:
        seen: list = []

        def ctl(account):
            with open(self.path, encoding="utf-8") as fh:
                seen.append(json.load(fh)[account])
            raise subprocess.TimeoutExpired("fabric-ctl", 1)
        rs = self.restarter(ctl=ctl)
        ledger, _, failed = self.poll([self.idle_row()], {}, rs, [])
        self.assertEqual(seen[0]["episode"], "end@1")           # on disk while the restart ran
        self.assertEqual(seen[0]["times"], [NOW])
        again, sent = self.restarter(), []
        self.poll([self.idle_row()], {}, again, sent)            # a later run: never restarted again for this episode
        self.assertEqual(self.calls, [])
        self.assertIn("failed", sent[0][1]["action"])

    def test_a_ledger_that_cannot_be_written_restarts_nothing(self) -> None:
        os.makedirs(os.path.dirname(self.path))
        os.chmod(os.path.dirname(self.path), 0o500)
        try:
            if os.access(os.path.dirname(self.path), os.W_OK):
                self.skipTest("runs as a user that writes anywhere")
            sent: list = []
            ledger, _, failed = self.poll([self.idle_row()], {}, self.restarter(), sent)
            self.assertEqual((self.calls, ledger), ([], {"a": "end@1"}))
            self.assertIn("restart ledger cannot be written", sent[0][1]["action"])
        finally:
            os.chmod(os.path.dirname(self.path), 0o700)

    def test_two_restarts_in_24_hours_are_the_cap_and_the_third_is_an_alarm_only(self) -> None:
        for n in (1, 2):
            self.now = NOW + n * 3600
            self.poll([self.idle_row(episode=f"end@{n}")], {}, self.restarter(), [])
        self.assertEqual(len(self.calls), 2)
        self.now = NOW + 3 * 3600
        sent: list = []
        ledger, _, _ = self.poll([self.idle_row(episode="end@3")], {}, self.restarter(), sent)
        self.assertEqual((len(self.calls), ledger), (2, {"a": "end@3"}))
        self.assertIn("did not restore a watch", sent[0][1]["action"])
        self.now = NOW + 2 * 3600 + deaf_alarm.RESTART_WINDOW_S + 1   # control: both aged out, restarts again
        self.poll([self.idle_row(episode="end@4")], {}, self.restarter(), [])
        self.assertEqual(len(self.calls), 3)

    def test_this_logins_own_account_is_never_restarted(self) -> None:
        sent: list = []
        self.poll([self.idle_row("me")], {}, self.restarter(own="me"), sent)
        self.assertEqual(self.calls, [])
        self.assertIn("own account", sent[0][1]["action"])
        self.poll([self.idle_row("other")], {}, self.restarter(own="me"), [])   # control
        self.assertEqual(self.calls, ["other"])

    def test_idle_false_unknown_or_absent_is_an_alarm_only_naming_why(self) -> None:
        for idle, why in ((False, "a tool call is pending (held at a permission prompt or in a long call)"), ("unknown", "the transcript cannot be read"), (None, "")):
            sent: list = []
            r = self.idle_row(idle=idle, why=why)
            if idle is None:
                del r["deaf"]["idle"], r["deaf"]["idle_why"]
            ledger, _, _ = self.poll([r], {}, self.restarter(), sent)
            self.assertEqual((self.calls, ledger), ([], {"a": "end@1"}), idle)
            self.assertIn("Not restarted", sent[0][1]["action"])
            if why:
                self.assertIn(why, sent[0][1]["action"])
        self.poll([self.idle_row()], {}, self.restarter(), [])   # control: idle true restarts
        self.assertEqual(self.calls, ["a"])

    def test_an_alarm_sent_while_held_does_not_stand_in_for_the_restart_after_it_goes_idle(self) -> None:
        sent: list = []
        ledger, _, _ = self.poll([self.idle_row(idle=False, why="pending")], {}, self.restarter(), sent)
        ledger, _, _ = self.poll([self.idle_row()], ledger, self.restarter(), sent)
        self.assertEqual((self.calls, len(sent), ledger), (["a"], 2, {"a": "end@1" + deaf_alarm.RESTART_TAG}))

    def test_dry_run_restarts_and_writes_nothing(self) -> None:
        rs = self.restarter()
        _, said, _ = deaf_alarm.alarm([self.idle_row()], {}, "h/user", True, lambda *a: self.fail("sent"), None, rs)
        self.assertEqual((self.calls, os.path.exists(self.path)), ([], False))
        self.assertIn("would restart", said[0])

    def test_the_restart_reply_is_read_from_the_account_row(self) -> None:
        mk = lambda out, rc=0: (lambda argv, **kw: subprocess.CompletedProcess(argv, rc, out, "err"))  # noqa: E731
        line = lambda data: json.dumps({"account": "a", "status": "ok", "restart": data})  # noqa: E731
        self.assertEqual(deaf_alarm.ctl_restart("a", mk(line({"status": "restarted", "pids": [1]}))), ("restarted", ""))
        self.assertEqual(deaf_alarm.ctl_restart("a", mk(line({"status": "failed", "reason": "busy upgrade"}), 1)), ("failed", "busy upgrade"))
        self.assertEqual(deaf_alarm.ctl_restart("a", mk(line({"status": "no-session"}))), ("no-session", ""))
        self.assertEqual(deaf_alarm.ctl_restart("a", mk(json.dumps({"account": "a", "status": "no answer"})))[0], "failed")
        self.assertEqual(deaf_alarm.ctl_restart("a", mk("", 2))[0], "failed")

        def boom(argv, **kw):
            raise subprocess.TimeoutExpired(argv, 1)
        self.assertEqual(deaf_alarm.ctl_restart("a", boom)[0], "failed")

    def test_the_entry_point_restarts_by_default_and_not_with_no_restart(self) -> None:
        d = self._tmp.name
        import pwd
        bindir, root = os.path.join(d, "bin"), os.path.join(d, "state2")
        state = os.path.join(root, "agents", pwd.getpwuid(os.geteuid()).pw_name)   # identity.agent_state_dir under the override
        os.makedirs(bindir)
        rowjson = json.dumps({"account": "a", "status": "ok", "deaf": {**row("a", "end@1")["deaf"], "idle": True, "idle_why": "ended"}})
        rrow = json.dumps({"account": "a", "status": "ok", "restart": {"status": "restarted"}})
        scripts = {
            "fabric-ctl": f"#!/bin/sh\nif [ \"$5\" = restart ] || [ \"$4\" = restart ]; then echo \"$@\" >> '{d}/ctl.log'; printf '%s\\n' '{rrow}'; "
                          f"else printf '%s\\n' '{rowjson}'; fi\n",
            "gzcoord-compose": '#!/bin/sh\nwhile [ $# -gt 0 ]; do [ "$1" = -o ] && out=$2; shift; done\n'
                               "printf '[GZCOORD/1] INFO\\nTO: h/user\\nSUBJECT: s\\n\\nCONTEXT:\\n\\nNOTES:\\n\\nREFERENCES:\\n' > \"$out\"\n",
            "gzcoord-send": f'#!/bin/sh\ncat "$1" >> "{d}/posted"\nexit 0\n',
        }
        for name, text in scripts.items():
            with open(os.path.join(bindir, name), "w") as fh:
                fh.write(text)
            os.chmod(os.path.join(bindir, name), 0o755)
        env = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": d, "AGENT_FABRIC_STATE_DIR": root}
        cmd = [sys.executable, "-I", os.path.join(HERE, "tools", "fabric", "control", "deaf_alarm.py"), "--to", "h/user"]
        r = subprocess.run(cmd + ["--no-restart"], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(os.path.join(d, "ctl.log")))
        self.assertFalse(os.path.exists(os.path.join(state, deaf_alarm.RESTART_LEDGER)))
        self.assertTrue(os.path.exists(os.path.join(state, deaf_alarm.LEDGER)))   # the alarm still went, so this state dir is the one read
        os.unlink(os.path.join(state, deaf_alarm.LEDGER))   # control: the same row, restart allowed
        r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(d, "ctl.log")) as fh:
            self.assertEqual(len(fh.read().splitlines()), 1)
        with open(os.path.join(d, "posted")) as fh:
            self.assertIn("was run: restarted", fh.read())


class Review1(Scratch):
    """#722 round 1: F1 (a refused binding), F2 (several sessions), F3 (the lock), F4 (ledger per send)."""

    def test_f1_a_binding_identity_refuses_is_unknown_and_the_status_reply_survives(self) -> None:
        import pwd
        root = os.path.join(self._tmp.name, "idroot")
        agent_dir = os.path.join(root, "agents", pwd.getpwuid(os.geteuid()).pw_name)
        os.makedirs(agent_dir)
        with open(os.path.join(agent_dir, "binding.json"), "w") as fh:
            json.dump({"agent": pwd.getpwuid(os.geteuid()).pw_name, "host": "some-other-host", "session": SID}, fh)
        old = os.environ.get("AGENT_FABRIC_STATE_DIR")
        os.environ["AGENT_FABRIC_STATE_DIR"] = root
        try:
            r = deaf.idle_of(deaf._binding_session, self._tmp.name, NOW)   # SystemExit before the fix
        finally:
            if old is None:
                del os.environ["AGENT_FABRIC_STATE_DIR"]
            else:
                os.environ["AGENT_FABRIC_STATE_DIR"] = old
        self.assertEqual(r[0], "unknown")

    def test_f2_more_than_one_session_is_unknown_and_one_is_judged(self) -> None:
        self.log({"t": iso(-3600), "event": "start", "pid": 11}, {**END5, "t": iso(-3000)})
        ended = lambda: (True, "ended")  # noqa: E731
        for n, want in ((2, "unknown"), (1, True)):
            r = deaf.judge(session={"status": "ok", "online": True, "sessions": n, "since": None}, last={**END5, "t": iso(-3000)}, watching=None, now=NOW,
                           ask_pending=lambda: ({"unread": 0, "queued_requests": 1}, None), ask_idle=ended)
            self.assertEqual(r["idle"], want, n)


class LockAndSave(unittest.TestCase):
    def test_f3_a_second_run_that_read_an_empty_ledger_does_not_restart_the_episode_again(self) -> None:
        with tempfile.TemporaryDirectory(prefix="deaf-test-") as d:
            path = os.path.join(d, "deaf-restart.json")
            calls: list = []
            ctl = lambda a: (calls.append(a), ("restarted", ""))[1]  # noqa: E731
            first = deaf_alarm.Restarter(path, "me", ctl=ctl, clock=lambda: NOW)
            second = deaf_alarm.Restarter(path, "me", ctl=ctl, clock=lambda: NOW)   # both read the ledger while it was empty
            self.assertEqual(first.execute("a", "end@1"), "restarted")
            self.assertTrue(second.execute("a", "end@1").startswith(deaf_alarm.ALREADY + "restarted"))
            self.assertEqual(calls, ["a"])
            self.assertEqual(len(json.load(open(path))["a"]["times"]), 1)

    def test_f4_the_alarm_ledger_is_saved_after_each_send(self) -> None:
        rows = [row("a", "end@1"), row("b", "end@2")]
        saved: list = []

        def send_one(account, d, to):
            if account == "b":
                self.assertEqual(saved, [{"a": "end@1"}])   # a's record already written when b is sent
        deaf_alarm.alarm(rows, {}, "h/user", False, send_one, None, None, lambda s: saved.append(dict(s)))
        self.assertEqual(saved[-1], {"a": "end@1", "b": "end@2"})

    def test_f6_a_run_that_lost_the_lock_tells_restarted_under_the_restart_key(self) -> None:
        with tempfile.TemporaryDirectory(prefix="deaf-test-") as d:
            path = os.path.join(d, "deaf-restart.json")
            first = deaf_alarm.Restarter(path, "me", ctl=lambda a: ("restarted", ""), clock=lambda: NOW)
            first.execute("a", "end@1")

            class Stale(deaf_alarm.Restarter):   # built before the first run wrote: plans a restart, then the lock's re-read finds it
                def plan(self, account, episode, d):
                    return ("restart", "") if not getattr(self, "_replanned", False) and not setattr(self, "_replanned", True) else super().plan(account, episode, d)
            stale = Stale(path, "me", ctl=lambda a: self.fail("restarted twice"), clock=lambda: NOW)
            sent: list = []
            ledger, _, _ = deaf_alarm.alarm([self.idle_row()], {}, "h/user", False, lambda a, dd, t: sent.append(dd), None, stale)
            self.assertEqual(ledger, {"a": "end@1" + deaf_alarm.RESTART_TAG})
            self.assertIn("was run: restarted", sent[0]["action"])

    def idle_row(self):
        r = row("a", "end@1")
        r["deaf"].update(idle=True, idle_why="ended")
        return r

    def test_f7_an_unreadable_ledger_under_the_lock_is_not_a_restart_that_was_run(self) -> None:
        with tempfile.TemporaryDirectory(prefix="deaf-test-") as d:
            path = os.path.join(d, "deaf-restart.json")
            rs = deaf_alarm.Restarter(path, "me", ctl=lambda a: self.fail("restarted"), clock=lambda: NOW)
            with open(path, "w") as fh:
                fh.write("not json")
            self.assertTrue(rs.execute("a", "end@1").startswith("not restarted: the restart ledger cannot be read"))

    def test_f8_a_failed_per_send_save_is_not_a_failure_when_the_final_write_covers_it(self) -> None:
        def save(state):
            raise OSError("ENOSPC")
        _, _, failed = deaf_alarm.alarm([row("a", "end@1")], {}, "h/user", False, lambda *a: None, None, None, save)
        self.assertEqual(failed, [])


if __name__ == "__main__":
    unittest.main()
