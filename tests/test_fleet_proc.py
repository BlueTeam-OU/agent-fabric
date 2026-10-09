#!/usr/bin/env python3
"""tools/fabric/fleet_proc.py: the /proc reader behind Fleet Deck's C0
section, run against fixture trees. The parser (a command name that
contains parentheses), the attribution by EFFECTIVE uid, the CPU rate over
two samples (a process seen once is not a rate), what is never opened, and
the command line (refusals and one live read of this very process)."""
from __future__ import annotations

import builtins
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import fleet_proc as fp  # noqa: E402

TOOL = os.path.join(HERE, "tools", "fabric", "fleet_proc.py")


def stat_line(pid: int, comm: str, utime: int, stime: int) -> str:
    # fields 3..13 are 11 values; utime is field 14, stime 15
    return f"{pid} ({comm}) S 1 {pid} {pid} 0 -1 4194560 10 0 0 0 {utime} {stime} 0 0 20 0 1 0 100 1000 50\n"


def status_text(ruid: int, euid: int, rss: int | None, swap: int | None = None) -> str:
    lines = ["Name:\tx", f"Uid:\t{ruid}\t{euid}\t{euid}\t{euid}", "Gid:\t1\t1\t1\t1"]
    if rss is not None:
        lines.append(f"VmRSS:\t{rss} kB")
    if swap is not None:
        lines.append(f"VmSwap:\t{swap} kB")
    return "\n".join(lines) + "\n"


class Tree:
    def __init__(self, test: unittest.TestCase):
        self.dir = tempfile.mkdtemp(prefix="fleet-proc-")
        test.addCleanup(self.cleanup)

    def cleanup(self) -> None:
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def proc(self, pid: int, euid: int, rss: int | None, utime: int = 0, stime: int = 0, swap: int | None = None,
             ruid: int | None = None, comm: str = "claude") -> None:
        d = os.path.join(self.dir, str(pid))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "status"), "w") as fh:
            fh.write(status_text(euid if ruid is None else ruid, euid, rss, swap))
        with open(os.path.join(d, "stat"), "w") as fh:
            fh.write(stat_line(pid, comm, utime, stime))
        for secret in ("environ", "cmdline"):
            with open(os.path.join(d, secret), "w") as fh:
                fh.write("SECRET=1\0")

    def gone(self, pid: int) -> None:
        import shutil
        shutil.rmtree(os.path.join(self.dir, str(pid)))


class Parse(unittest.TestCase):
    def test_stat_ticks_survive_a_command_name_with_parentheses_and_spaces(self):
        self.assertEqual(fp.parse_stat_ticks(stat_line(7, "a) S 9 9 (b c", 30, 12)), 42)

    def test_status_takes_the_effective_uid_and_zero_memory_for_a_kernel_thread(self):
        self.assertEqual(fp.parse_status(status_text(5, 1024, 300, 7)), {"euid": 1024, "rss_kb": 300, "swap_kb": 7})
        self.assertEqual(fp.parse_status(status_text(0, 0, None)), {"euid": 0, "rss_kb": 0, "swap_kb": 0})
        with self.assertRaises(ValueError):
            fp.parse_status("Name:\tx\n")


class Sampling(unittest.TestCase):
    def test_a_login_is_its_effective_uid_summed_and_others_are_not_counted(self):
        t = Tree(self)
        t.proc(10, 1000, 100, swap=5)
        t.proc(11, 1000, 250, swap=1)
        t.proc(12, 2000, 999)
        t.proc(13, 2000, 77, ruid=1000)          # real uid 1000, effective 2000: ps -u 2000 counts it, 1000 does not
        s = fp.sample({1000}, t.dir)
        self.assertEqual((s.rss_kb, s.swap_kb, s.procs), ({1000: 350}, {1000: 6}, {1000: 2}))

    def test_a_listing_entry_that_is_not_a_process_or_vanished_is_skipped(self):
        t = Tree(self)
        t.proc(10, 1000, 100)
        os.makedirs(os.path.join(t.dir, "self"))
        os.makedirs(os.path.join(t.dir, "99"))   # a pid with nothing readable: exited since the listing
        self.assertEqual(fp.sample({1000}, t.dir).procs, {1000: 1})

    def test_environ_and_cmdline_are_never_opened(self):
        t = Tree(self)
        t.proc(10, 1000, 100)
        opened: list[str] = []
        real = builtins.open

        def spy(path, *a, **k):
            opened.append(str(path))
            return real(path, *a, **k)
        builtins.open = spy
        try:
            fp.sample({1000}, t.dir)
        finally:
            builtins.open = real
        self.assertTrue(any(p.endswith("/status") for p in opened), "the spy saw the reads (positive control)")
        self.assertEqual([p for p in opened if p.endswith(("environ", "cmdline"))], [])

    def test_cpu_counts_only_processes_seen_in_both_samples(self):
        self.assertEqual(fp.cpu_pct({1: 100, 2: 50}, {1: 200, 3: 9999}, 2.0, 100), 50.0)   # pid 1: 100 ticks/2 s at 100 Hz
        self.assertEqual(fp.cpu_pct({1: 100}, {1: 90}, 1.0, 100), 0.0, "a counter that went down is not negative CPU")
        self.assertIsNone(fp.cpu_pct({1: 0}, {1: 5}, 0, 100), "no time passed: unmeasured, not idle")

    def test_collect_rate_comes_from_two_samples_and_the_clock_between_them(self):
        t = Tree(self)
        t.proc(10, 1000, 100, utime=100)
        t.proc(11, 1000, 50, utime=0)

        def between(_s: float) -> None:
            t.proc(10, 1000, 120, utime=150, stime=50)   # +100 ticks
            t.gone(11)
            t.proc(12, 1000, 10, utime=900)              # new: contributes memory, not rate
        ticks = iter([0.0, 2.0])
        doc = fp.collect(["a", "ghost"], 2.0, proc=t.dir, uid_of=lambda login: {"a": 1000}[login], clk_tck=100,
                         clock=lambda: next(ticks), sleep=between, host="h1")
        self.assertEqual(doc["agents"]["a"], {"uid": 1000, "cpu_pct": 50.0, "rss_kb": 130, "swap_kb": 0, "procs": 2})
        self.assertEqual((doc["unknown"], doc["host"], doc["interval_s"]), (["ghost"], "h1", 2.0))
        self.assertNotIn("ghost", doc["agents"])

    def test_a_login_with_no_process_is_present_with_zeros(self):
        t = Tree(self)
        doc = fp.collect(["a"], 0, proc=t.dir, uid_of=lambda _l: 1000, clk_tck=100, sleep=lambda _s: None, host="h")
        self.assertEqual(doc["agents"]["a"], {"uid": 1000, "cpu_pct": 0.0, "rss_kb": 0, "swap_kb": 0, "procs": 0})


class Command(unittest.TestCase):
    def run_tool(self, *args: str) -> subprocess.CompletedProcess:
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        return subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, timeout=30, env=env,
                              stdin=subprocess.DEVNULL, check=False)

    def test_refusals_say_one_line_and_exit_2(self):
        for args, word in (([], "--json is required"), (["--json", "--interval", "99"], "--interval"),
                           (["--json", "--interval", "x"], "--interval"), (["--json", "--login"], "needs a value"),
                           (["--json", "--bogus"], "unknown argument")):
            p = self.run_tool(*args)
            self.assertEqual((p.returncode, p.stdout), (2, ""), args)
            self.assertEqual(len(p.stderr.strip().splitlines()), 1, args)
            self.assertIn(word, p.stderr)

    def test_a_live_read_of_this_login_finds_this_process(self):
        import pwd
        me = pwd.getpwuid(os.geteuid()).pw_name
        p = self.run_tool("--json", "--login", me, "--interval", "0")
        self.assertEqual(p.returncode, 0, p.stderr)
        a = json.loads(p.stdout)["agents"][me]
        self.assertGreaterEqual(a["procs"], 1)
        self.assertGreater(a["rss_kb"], 0)


if __name__ == "__main__":
    unittest.main()
