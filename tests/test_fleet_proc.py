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


MOUNTS_OPEN = "proc /proc proc rw,nosuid,nodev,noexec,relatime 0 0\n"


def mounts_with(options: str) -> str:
    return f"tmpfs /tmp tmpfs rw 0 0\nproc /proc proc rw,nosuid,nodev,noexec,relatime,{options} 0 0\n"


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
    def __init__(self, test: unittest.TestCase, mounts: str | None = MOUNTS_OPEN):
        self.dir = tempfile.mkdtemp(prefix="fleet-proc-")
        test.addCleanup(self.cleanup)
        if mounts is not None:
            with open(os.path.join(self.dir, "mounts"), "w") as fh:
                fh.write(mounts)

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

    def cmdline(self, pid: int, *argv: str) -> None:
        with open(os.path.join(self.dir, str(pid), "cmdline"), "wb") as fh:
            fh.write(b"\0".join(a.encode() for a in argv) + b"\0")

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
        self.assertEqual(doc["agents"]["a"], {"uid": 1000, "cpu_pct": 50.0, "rss_kb": 130, "swap_kb": 0, "procs": 2, "inbox_watch": False})
        self.assertEqual((doc["unknown"], doc["host"], doc["interval_s"]), (["ghost"], "h1", 2.0))
        self.assertNotIn("ghost", doc["agents"])

    def test_a_login_with_no_process_is_present_with_zeros(self):
        t = Tree(self)
        doc = fp.collect(["a"], 0, proc=t.dir, uid_of=lambda _l: 1000, clk_tck=100, sleep=lambda _s: None, host="h")
        self.assertEqual(doc["agents"]["a"], {"uid": 1000, "cpu_pct": 0.0, "rss_kb": 0, "swap_kb": 0, "procs": 0, "inbox_watch": False})


WATCH = ("/usr/local/bin/fabric-python", "-I", "/home/a/.local/bin/gzcoord-inbox", "--until-delivery")


class Watch(unittest.TestCase):
    """inbox_watch: true, false and null, from a fake /proc; the command line read for that and nothing else."""

    def cmd(self, *argv: str) -> bool:
        return fp.runs_inbox_watch(b"\0".join(a.encode() for a in argv) + b"\0")

    def test_a_command_that_runs_gzcoord_inbox_with_until_delivery_or_wait_is_a_watch(self):
        for argv in (WATCH, ("python3", "/x/gzcoord-inbox", "--wait"), ("/usr/bin/gzcoord-inbox", "--until-delivery"),
                     ("gzcoord-inbox", "--wait", "--json"), ("fabric-python", "-I", "-u", "/b/gzcoord-inbox", "--until-delivery")):
            self.assertTrue(self.cmd(*argv), argv)

    def test_a_command_that_only_mentions_the_words_is_not(self):
        prompt = "Session start: run gzcoord-inbox --until-delivery now"
        for argv in (("claude", "--resume", "id", "--", prompt), ("/bin/bash", "-c", "eval 'gzcoord-inbox --until-delivery'"),
                     ("gzcoord-inbox",), ("gzcoord-inbox", "--replay", "7"), ("gzcoord-inbox", "--history"),
                     ("gzcoord-inbox", "--wait=5"), ("gzcoord-inbox", "--until-delivery-x"), ("vim", "gzcoord-inbox"),
                     ("a", "b", "c", "d", "gzcoord-inbox", "--wait"), ("tail", "--wait", "gzcoord-inbox-log"), ("--until-delivery",), ()):
            self.assertFalse(self.cmd(*argv), argv)
        self.assertFalse(fp.runs_inbox_watch(b""))

    def sample(self, t: Tree, uids: set[int] = frozenset({1000})) -> fp.Sample:
        return fp.sample(set(uids), t.dir, cmdlines=True)

    def test_true_when_a_process_of_the_login_runs_a_watch(self):
        t = Tree(self)
        t.proc(10, 1000, 100)
        t.proc(11, 1000, 50)
        t.cmdline(11, *WATCH)
        s = self.sample(t)
        self.assertEqual((s.watching, s.unreadable, fp.watch_state(1000, s, 1000)), ({1000}, set(), True))

    def test_false_when_the_processes_were_read_and_none_is_one(self):
        t = Tree(self)
        t.proc(10, 1000, 100)
        t.cmdline(10, "claude", "--", "run gzcoord-inbox --until-delivery")
        t.proc(11, 2000, 50)
        t.cmdline(11, *WATCH)                                  # another login's watch is not this login's
        s = self.sample(t)
        self.assertEqual(fp.watch_state(1000, s, 1000), False)
        self.assertEqual(fp.watch_state(1000, s, 5), False, "a reader that is another uid sees it too: nothing hides /proc here")

    def test_null_when_a_command_line_of_the_login_could_not_be_read(self):
        t = Tree(self)
        t.proc(10, 1000, 100)
        t.proc(11, 1000, 50)
        os.remove(os.path.join(t.dir, "11", "cmdline"))
        os.mkdir(os.path.join(t.dir, "11", "cmdline"))       # a read that fails with something other than "gone"
        s = self.sample(t)
        self.assertEqual((s.unreadable, fp.watch_state(1000, s, 1000)), ({1000}, None))

    def test_a_watch_seen_wins_over_a_command_line_that_could_not_be_read(self):
        t = Tree(self)
        t.proc(10, 1000, 100)
        t.cmdline(10, *WATCH)
        t.proc(11, 1000, 50)
        os.remove(os.path.join(t.dir, "11", "cmdline"))
        os.mkdir(os.path.join(t.dir, "11", "cmdline"))
        self.assertTrue(fp.watch_state(1000, self.sample(t), 1000))

    def test_a_process_that_exited_between_the_listing_and_the_read_is_not_unknown(self):
        t = Tree(self)
        t.proc(10, 1000, 100)
        t.proc(11, 1000, 50)
        os.remove(os.path.join(t.dir, "11", "cmdline"))        # gone: ENOENT
        s = self.sample(t)
        self.assertEqual((s.procs, s.unreadable, fp.watch_state(1000, s, 1000)), ({1000: 1}, set(), False))

    def test_a_login_with_no_process_is_false_for_a_reader_that_sees_every_process(self):
        t = Tree(self)
        self.assertEqual(fp.watch_state(2000, self.sample(t, {2000}), 1000), False)

    def test_null_for_a_login_whose_processes_could_be_hidden_from_this_reader(self):
        for mounts, hidden in ((mounts_with("hidepid=2"), True), (mounts_with("hidepid=invisible"), True), (mounts_with("hidepid=1"), True),
                               (mounts_with("hidepid=4"), True), (mounts_with("hidepid=0"), False), (MOUNTS_OPEN, False), (None, None)):
            t = Tree(self, mounts)
            s = self.sample(t, {2000})
            self.assertEqual(s.hidden, hidden, mounts)
            self.assertEqual(fp.watch_state(2000, s, 1000), False if hidden is False else None, mounts)
            self.assertEqual(fp.watch_state(1000, self.sample(t), 1000), False, "a reader sees its own account's processes whatever hides the rest")

    def test_hidepid_does_not_hide_from_root_or_a_member_of_the_gid_group(self):
        hide = mounts_with("hidepid=2,gid=999")
        t = Tree(self, hide)
        self.assertTrue(fp.proc_hides_others(t.dir, euid=1000, groups=[1000]))
        self.assertFalse(fp.proc_hides_others(t.dir, euid=0, groups=[]))
        self.assertFalse(fp.proc_hides_others(t.dir, euid=1000, groups=[1000, 999]))

    def test_only_the_asked_logins_command_lines_are_opened_and_environ_never(self):
        t = Tree(self)
        t.proc(10, 1000, 100)
        t.proc(11, 3000, 100)
        opened: list[str] = []
        real = builtins.open

        def spy(path, *a, **k):
            opened.append(str(path))
            return real(path, *a, **k)
        builtins.open = spy
        try:
            self.sample(t)
        finally:
            builtins.open = real
        self.assertEqual([p for p in opened if p.endswith("cmdline")], [os.path.join(t.dir, "10", "cmdline")], "positive control: the asked login's")
        self.assertEqual([p for p in opened if p.endswith("environ")], [])

    def test_what_a_command_line_said_is_never_in_the_answer(self):
        t = Tree(self)
        t.proc(10, 1000, 100)
        t.cmdline(10, "claude", "--token", "SECRET-VALUE-9", "gzcoord-inbox", "--wait")
        doc = fp.collect(["a"], 0, proc=t.dir, uid_of=lambda _l: 1000, clk_tck=100, sleep=lambda _s: None, host="h", own_uid=1000)
        self.assertNotIn("SECRET", json.dumps(doc))
        self.assertIs(doc["agents"]["a"]["inbox_watch"], True)

    def test_the_command_line_is_read_in_the_second_sample_only_and_only_its_start(self):
        t = Tree(self)
        t.proc(10, 1000, 100)
        self.assertEqual(fp.sample({1000}, t.dir).watching, set(), "without cmdlines=True nothing is read for it")
        t.cmdline(10, *WATCH)
        with open(os.path.join(t.dir, "10", "cmdline"), "ab") as fh:
            fh.write(b"y" * 10000)
        self.assertEqual(self.sample(t).watching, {1000}, "a long tail after the watch's own words does not matter")
        t.cmdline(10, "x" * (fp.CMDLINE_BYTES + 10), "gzcoord-inbox", "--wait")
        self.assertEqual(self.sample(t).watching, set(), "words past the bytes looked at are not looked at")

    def test_a_process_command_line_is_opened_once_per_collect_not_once_per_sample(self):
        t = Tree(self)
        t.proc(10, 1000, 100)
        t.proc(11, 1000, 100)
        opened: list[str] = []
        real = builtins.open

        def spy(path, *a, **k):
            opened.append(str(path))
            return real(path, *a, **k)
        builtins.open = spy
        try:
            fp.collect(["a"], 0, proc=t.dir, uid_of=lambda _l: 1000, clk_tck=100, sleep=lambda _s: None, host="h", own_uid=1000)
        finally:
            builtins.open = real
        self.assertEqual(sorted(p for p in opened if p.endswith("cmdline")), [os.path.join(t.dir, "10", "cmdline"), os.path.join(t.dir, "11", "cmdline")])

    def test_collect_says_true_false_and_null_per_login(self):
        t = Tree(self)
        t.proc(10, 1000, 100)
        t.cmdline(10, *WATCH)
        t.proc(11, 2000, 100)
        t.proc(12, 3000, 100)
        os.remove(os.path.join(t.dir, "12", "cmdline"))
        os.mkdir(os.path.join(t.dir, "12", "cmdline"))
        doc = fp.collect(["a", "b", "c", "d"], 0, proc=t.dir, uid_of=lambda l: {"a": 1000, "b": 2000, "c": 3000, "d": 4000}[l],
                         clk_tck=100, sleep=lambda _s: None, host="h", own_uid=1000)
        self.assertEqual({l: doc["agents"][l]["inbox_watch"] for l in "abcd"}, {"a": True, "b": False, "c": None, "d": False})


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
        self.assertIn(a["inbox_watch"], (True, False), "this login's own processes are readable by it")
        self.assertGreaterEqual(a["procs"], 1)
        self.assertGreater(a["rss_kb"], 0)


if __name__ == "__main__":
    unittest.main()
