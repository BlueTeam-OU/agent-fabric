#!/usr/bin/env python3
"""tools/fabric/watch_resources.py: what this account and this host cost, from a fake /proc this test builds (no
reading of the machine's own), and the disk reading that never waits on the caller.

Each case fails when its guard is removed: only this account's processes counted, by their EFFECTIVE uid; a command name
with spaces and parentheses cannot shift the stat fields; a kernel thread has no resident size and is still a process;
CPU% is only of the processes present in both samples, with the same start time, over the wall time between them, and
None until there are two samples and some time between them; a process that exits between the listing and the read is
skipped; a missing /proc is zeros, not a crash; the disk reading starts a thread and returns at once, keeps the last
good value when a later one fails, and is not asked again inside its interval."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
import watch_resources as wr  # noqa: E402


class FakeProc:
    def __init__(self, root: str):
        self.root = root

    def write(self, rel: str, text: str) -> None:
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def process(self, pid: int, *, uid: int = 1000, euid: int | None = None, rss_kb: int | None = 100, utime: int = 0, stime: int = 0,
                start: int = 1, comm: str = "worker") -> None:
        # fields after the command name: state(3) ... utime is field 14, stime 15, starttime 22 (1-based, comm is 2)
        after = ["S", "1", "1", "1", "0", "-1", "0", "0", "0", "0", "0", str(utime), str(stime), "0", "0", "20", "0", "1", "0", str(start)]
        self.write(f"{pid}/stat", f"{pid} ({comm}) " + " ".join(after) + " 0 0\n")
        lines = [f"Name:\t{comm[:15]}", f"Uid:\t{uid}\t{uid if euid is None else euid}\t{uid}\t{uid}"]
        if rss_kb is not None:
            lines.append(f"VmRSS:\t{rss_kb} kB")
        self.write(f"{pid}/status", "\n".join(lines) + "\n")

    def host(self, load: str = "0.50 0.40 0.30 1/200 999", avail_kb: int = 4096, total_kb: int = 8192) -> None:
        self.write("loadavg", load + "\n")
        self.write("meminfo", f"MemTotal:       {total_kb} kB\nMemFree:        1 kB\nMemAvailable:   {avail_kb} kB\n")


class Sampler(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="watch-res-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.proc = FakeProc(self.tmp)
        self.now = [100.0]

    def sampler(self, uid: int = 1000) -> wr.ProcSampler:
        return wr.ProcSampler(uid, self.tmp, clock=lambda: self.now[0], hertz=100)

    def test_the_sum_is_of_this_accounts_processes_by_effective_uid_only(self):
        self.proc.process(1, rss_kb=100)
        self.proc.process(2, rss_kb=200)
        self.proc.process(3, uid=1001, rss_kb=5000)
        self.proc.process(4, uid=0, euid=1000, rss_kb=50)             # a setuid process: the effective uid is the account's
        self.proc.process(5, uid=1000, euid=1001, rss_kb=7000)        # and the reverse: not ours
        self.assertEqual(self.sampler().sample(), {"procs": 3, "rss_kb": 350, "cpu_pct": None})

    def test_a_kernel_thread_without_a_resident_size_is_a_process_with_none(self):
        self.proc.process(1, rss_kb=None)
        self.proc.process(2, rss_kb=10)
        self.assertEqual(self.sampler().sample()["rss_kb"], 10)
        self.assertEqual(self.sampler().sample()["procs"], 2)

    def test_a_command_name_with_spaces_and_parentheses_cannot_shift_the_fields(self):
        self.proc.process(1, comm="a) 3 (b", utime=0, stime=0, start=7)
        s = self.sampler()
        s.sample()
        self.proc.process(1, comm="a) 3 (b", utime=60, stime=40, start=7)
        self.now[0] += 10.0
        self.assertEqual(s.sample()["cpu_pct"], 10.0)

    def test_cpu_is_ticks_over_wall_time_of_the_processes_in_both_samples_and_none_before_that(self):
        self.proc.process(1, utime=1000)
        self.proc.process(2, utime=0)
        s = self.sampler()
        self.assertIsNone(s.sample()["cpu_pct"], "the first sample has no rate")
        self.assertIsNone(s.sample()["cpu_pct"], "no time has passed")
        self.proc.process(1, utime=1100, stime=100)                 # 200 ticks = 2 s of CPU
        self.proc.process(2, utime=300)                             # 300 ticks = 3 s
        self.now[0] += 10.0
        self.assertEqual(s.sample()["cpu_pct"], 50.0)               # 5 CPU seconds over 10 wall seconds, 100 = one core

    def test_a_process_that_started_or_was_replaced_between_the_samples_adds_no_cpu(self):
        self.proc.process(1, utime=0, start=5)
        self.proc.process(2, utime=0, start=5)
        s = self.sampler()
        s.sample()
        self.proc.process(1, utime=100, start=5)
        self.proc.process(2, utime=99999, start=6)                  # the pid was reused: a different process
        self.proc.process(3, utime=99999, start=9)                  # new
        self.now[0] += 10.0
        out = s.sample()
        self.assertEqual((out["cpu_pct"], out["procs"]), (10.0, 3))

    def test_a_process_that_exits_between_the_listing_and_the_read_is_skipped(self):
        self.proc.process(1, rss_kb=10)
        os.makedirs(os.path.join(self.tmp, "2"))                    # listed, and no status to read
        self.assertEqual(self.sampler().sample()["procs"], 1)

    def test_no_proc_is_zeros_and_none_not_a_crash(self):
        gone = wr.ProcSampler(1000, os.path.join(self.tmp, "absent"), clock=lambda: 1.0, hertz=100)
        self.assertEqual(gone.sample(), {"procs": 0, "rss_kb": 0, "cpu_pct": None})
        self.assertEqual((wr.host_load(os.path.join(self.tmp, "absent")), wr.host_memory(os.path.join(self.tmp, "absent"))), (None, None))

    def test_it_reads_only_stat_and_status(self):
        self.proc.process(1)
        self.proc.write("1/environ", "SECRET=1\0")
        self.proc.write("1/cmdline", "claude\0--token\0")
        os.chmod(os.path.join(self.tmp, "1", "environ"), 0)
        os.chmod(os.path.join(self.tmp, "1", "cmdline"), 0)
        opened: list[str] = []
        real = open

        def spy(path, *a, **k):
            opened.append(str(path))
            return real(path, *a, **k)
        import builtins
        builtins.open, saved = spy, builtins.open
        try:
            self.sampler().sample()
        finally:
            builtins.open = saved
        self.assertEqual(sorted({os.path.basename(p) for p in opened}), ["stat", "status"])


class Host(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="watch-host-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.proc = FakeProc(self.tmp)

    def test_load_and_memory_are_read_from_loadavg_and_meminfo(self):
        self.proc.host("1.50 0.75 0.25 3/400 4242", avail_kb=2048, total_kb=16384)
        self.assertEqual(wr.host_load(self.tmp), (1.5, 0.75, 0.25))
        self.assertEqual(wr.host_memory(self.tmp), (2048, 16384))

    def test_files_that_are_not_what_they_should_be_are_none(self):
        self.proc.write("loadavg", "not numbers\n")
        self.proc.write("meminfo", "MemTotal: 5 kB\n")              # no MemAvailable (an old kernel)
        self.assertEqual((wr.host_load(self.tmp), wr.host_memory(self.tmp)), (None, None))

    def test_sizes_are_said_in_the_unit_that_fits(self):
        self.assertEqual([wr.human_kb(v) for v in (0, 512, 2048, 5 * 1024 * 1024, 3 * 1024 ** 3)], ["0 kB", "512 kB", "2.0 MB", "5.0 GB", "3.0 TB"])


class Disk(unittest.TestCase):
    class Done:
        def __init__(self, stdout: str):
            self.stdout = stdout

    def test_poll_returns_at_once_while_du_runs_in_a_thread_and_value_is_none_until_it_answers(self):
        release, started = threading.Event(), threading.Event()
        argv_seen = []

        def slow_du(argv, **kw):
            argv_seen.append((argv, kw.get("timeout"), kw.get("stdin")))
            started.set()
            release.wait(10)
            return Disk.Done("1234\t/home/x\n")
        disk = wr.DiskUse("/home/x", slow_du)
        disk.poll()                                                  # would hang the caller if it waited
        self.assertTrue(started.wait(5))
        self.assertEqual(disk.value(), (None, None, None))
        disk.poll()                                                  # one reading at a time
        self.assertEqual(len(argv_seen), 1)
        release.set()
        disk.wait()
        kb, age, why = disk.value()
        self.assertEqual((kb, why), (1234, None))
        self.assertIsNotNone(age)
        self.assertEqual(argv_seen[0][0], ["du", "-sk", "-x", "/home/x"], "an argument list, no shell")
        self.assertEqual(argv_seen[0][1], wr.DU_TIMEOUT_S)

    def test_it_is_not_asked_again_inside_its_interval_and_is_after_it(self):
        now = [0.0]
        calls = []

        def du(argv, **kw):
            calls.append(1)
            return Disk.Done(f"{len(calls)}00\t/h\n")
        disk = wr.DiskUse("/h", du, clock=lambda: now[0], refresh_s=600)
        disk.poll()
        disk.wait()
        now[0] = 599.0
        disk.poll()
        disk.wait()
        self.assertEqual(len(calls), 1)
        now[0] = 601.0
        disk.poll()
        disk.wait()
        self.assertEqual((len(calls), disk.value()[0]), (2, 200))

    def test_a_failed_reading_keeps_the_last_good_one_with_its_age_and_says_why(self):
        now = [0.0]
        answers = [Disk.Done("500\t/h\n"), OSError(5, "I/O error"), FileNotFoundError(), Disk.Done("")]

        def du(argv, **kw):
            a = answers.pop(0)
            if isinstance(a, Exception):
                raise a
            return a
        disk = wr.DiskUse("/h", du, clock=lambda: now[0], refresh_s=10)
        for step, (when, want) in enumerate(((0.0, (500, None)), (20.0, (500, "du: I/O error")), (40.0, (500, "du: not found")),
                                             (60.0, (500, "du answered nothing")))):
            now[0] = when
            disk.poll()
            disk.wait()
            kb, age, why = disk.value()
            self.assertEqual((kb, why), want, step)
        self.assertEqual(disk.value()[1], 60.0, "the age is of the last good reading")

    def test_a_du_that_times_out_is_said(self):
        import subprocess

        def hang(argv, **kw):
            raise subprocess.TimeoutExpired(argv, 1)
        disk = wr.DiskUse("/h", hang)
        disk.poll()
        disk.wait()
        self.assertEqual(disk.value(), (None, None, f"du: no answer within {wr.DU_TIMEOUT_S} s"))


if __name__ == "__main__":
    unittest.main()
