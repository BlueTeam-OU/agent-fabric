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


if __name__ == "__main__":
    unittest.main()
