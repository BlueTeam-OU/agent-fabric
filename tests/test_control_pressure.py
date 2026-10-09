#!/usr/bin/env python3
"""tools/fabric/control/pressure.py: what a sample reads, how the ring is
kept, what the host op says about it. A port of
runtime/control/tests/pressure.test.mjs case for case, less the `fabric-ctl
host` rendering (ctl's: pressureText, python-dev-03)."""
from __future__ import annotations

import errno
import os
import stat
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import ops, pressure as P  # noqa: E402

PSI = "some avg10=12.50 avg60=3.10 avg300=0.80 total=1453197\nfull avg10=4.25 avg60=1.00 avg300=0.20 total=1328293\n"
MEMINFO = "MemTotal:        8000000 kB\nMemFree:          100000 kB\nMemAvailable:     409600 kB\n"
T0 = datetime(2026, 10, 4, 16, tzinfo=timezone.utc).timestamp() * 1000


def at(minutes: float) -> str:
    return (datetime(2026, 10, 4, 16, tzinfo=timezone.utc) + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class Base(unittest.TestCase):
    def scratch(self, prefix: str = "pressure-") -> str:
        t = tempfile.TemporaryDirectory(prefix=prefix)
        self.addCleanup(t.cleanup)
        return t.name

    def proc(self, psi: str | None = PSI, meminfo: str | None = MEMINFO) -> str:
        proc = self.scratch("pressure-proc-")
        if psi is not None:
            os.makedirs(os.path.join(proc, "pressure"))
            with open(os.path.join(proc, "pressure", "memory"), "w", encoding="utf-8") as fh:
                fh.write(psi)
        if meminfo is not None:
            with open(os.path.join(proc, "meminfo"), "w", encoding="utf-8") as fh:
                fh.write(meminfo)
        return proc


class Sample(Base):
    def test_psi_some_full_avg10_and_memavailable_in_mb_a_reading_the_kernel_did_not_give_is_null_never_0(self):
        now = lambda: T0  # noqa: E731
        self.assertEqual(P.sample(self.proc(), now), {"ts": at(0), "some_avg10": 12.5, "full_avg10": 4.25, "mem_available_mb": 400})
        self.assertEqual(P.sample(self.proc(psi=None), now), {"ts": at(0), "some_avg10": None, "full_avg10": None, "mem_available_mb": 400},
                         "a kernel without PSI is not a calm machine")
        self.assertEqual(P.sample(self.proc(psi="some avg10=x\nfull nonsense\n", meminfo="MemTotal: 1 kB\n"), now),
                         {"ts": at(0), "some_avg10": None, "full_avg10": None, "mem_available_mb": None}, "unparseable is unknown")
        self.assertIsNone(P.sample(self.proc(psi="full avg10=1.00 avg60=0 avg300=0 total=0\n"), now)["some_avg10"], "full is not read as some")
        self.assertEqual(P.sample(self.proc(psi="some avg10=3.00 avg60=0 avg300=0 total=0\nfull avg10=0.00 avg60=0 avg300=0 total=0\n"), now)["some_avg10"], 3,
                         "a whole number is written as the Node wrote it")
        self.assertIsInstance(P.sample(self.proc(psi="some avg10=3.00 avg60=0 avg300=0 total=0\n"), now)["some_avg10"], int)


class Sampler(Base):
    def test_one_sample_a_tick_persisted_whole_bounded_kept_across_a_restart(self):
        file = os.path.join(self.scratch("pressure-state-"), "agents", "me", "memory-pressure.json")
        t = [T0]
        now = lambda: t[0]  # noqa: E731
        proc = self.proc()
        s = P.sampler(file=file, proc=proc, now=now, max=5, log=lambda m: None)
        for _ in range(7):
            s.tick()
            t[0] += 60000
        ring = P.read_ring(file)
        self.assertEqual(len(ring), 5, "the oldest go once the ring is full")
        self.assertEqual([x["ts"] for x in ring], [at(i) for i in (2, 3, 4, 5, 6)])
        self.assertEqual(stat.S_IMODE(os.stat(file).st_mode), 0o600)
        self.assertEqual(os.listdir(os.path.dirname(file)), ["memory-pressure.json"], "no temporary file is left")
        P.sampler(file=file, proc=proc, now=now, max=5, log=lambda m: None).tick()   # a restarted daemon continues the ring it finds
        self.assertEqual([x["ts"] for x in P.read_ring(file)][-2:], [at(6), at(7)])
        self.assertEqual(P.RING_MAX, 1440, "a day of minutes by default")

    def test_the_ring_reaches_the_disk_the_file_fsynced_before_its_rename_the_directory_after_it(self):
        file = os.path.join(self.scratch("pressure-durable-"), "agents", "me", "memory-pressure.json")
        opened: dict[int, str] = {}
        events: list[str] = []
        real_open, real_rename = os.open, os.rename

        def spy_open(path, *a, **k):
            fd = real_open(path, *a, **k)
            opened[fd] = str(path)
            return fd

        def spy_fsync(fd):
            events.append(f"fsync {os.path.basename(opened.get(fd, '?'))}")

        def spy_rename(a, b):
            events.append(f"rename {os.path.basename(str(b))}")
            real_rename(a, b)
        with mock.patch.object(os, "open", spy_open), mock.patch.object(os, "fsync", spy_fsync), mock.patch.object(os, "rename", spy_rename):
            P.sampler(file=file, proc=self.proc(), now=lambda: T0, log=lambda m: None).tick()
        self.assertEqual(events, [f"fsync memory-pressure.json.{os.getpid()}.tmp", "rename memory-pressure.json", "fsync me"])
        self.assertEqual(len(P.read_ring(file)), 1, "control: the tick did write the ring")
        self.assertEqual(os.listdir(os.path.dirname(file)), ["memory-pressure.json"], "no temporary file left behind")

    def test_a_bad_ring_is_kept_aside_a_failure_to_write_is_one_line_when_it_starts_and_one_when_it_ends(self):
        d = self.scratch("pressure-bad-")
        file = os.path.join(d, "memory-pressure.json")
        with open(file, "w", encoding="utf-8") as fh:
            fh.write('{"not": "a list"}')
        logs: list[str] = []
        P.sampler(file=file, proc=self.proc(), now=lambda: T0, log=logs.append).tick()
        self.assertEqual(len(P.read_ring(file)), 1, "sampling goes on")
        with open(f"{file}.unreadable", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), '{"not": "a list"}', "the bad file is evidence, not deleted")
        self.assertEqual(len(logs), 1)
        self.assertRegex(logs[0], r"not a list of samples; kept as memory-pressure\.json\.unreadable")
        # The ring's directory is a file: nothing can be written until it is not.
        blocked = os.path.join(self.scratch("pressure-blocked-"), "state")
        with open(blocked, "w", encoding="utf-8") as fh:
            fh.write("a file where the directory goes")
        logs2: list[str] = []
        s = P.sampler(file=os.path.join(blocked, "memory-pressure.json"), proc=self.proc(), now=lambda: T0, log=logs2.append)
        for _ in range(3):
            s.tick()
        self.assertEqual(len(logs2), 1, f"not one line a minute: {logs2}")
        self.assertRegex(logs2[0], r"cannot keep the ring \((EEXIST|ENOTDIR)\)")
        os.unlink(blocked)
        s.tick()
        self.assertEqual(logs2[1:], ["agentd: memory pressure: sampling again"])
        self.assertEqual(len(P.read_ring(os.path.join(blocked, "memory-pressure.json"))), 1)
        # A ring that cannot be READ is not a bad ring: retried, never replaced.
        if os.getuid() != 0:
            kept = os.path.join(self.scratch("pressure-locked-"), "memory-pressure.json")
            P.sampler(file=kept, proc=self.proc(), now=lambda: T0, log=lambda m: None).tick()
            os.chmod(kept, 0)
            logs3: list[str] = []
            s3 = P.sampler(file=kept, proc=self.proc(), now=lambda: T0 + 60000, log=logs3.append)
            s3.tick()
            os.chmod(kept, 0o600)
            s3.tick()
            self.assertFalse(os.path.exists(f"{kept}.unreadable"))
            self.assertRegex(logs3[0], r"cannot keep the ring \(EACCES\)")
            self.assertEqual(len(P.read_ring(kept)), 2, "the day already sampled is still there")

    def test_a_failed_write_leaves_the_previous_ring_whole_and_no_temporary_file(self):
        file = os.path.join(self.scratch("pressure-atomic-"), "memory-pressure.json")
        s = P.sampler(file=file, proc=self.proc(), now=lambda: T0, log=lambda m: None)
        s.tick()
        before = open(file, encoding="utf-8").read()
        with mock.patch.object(os, "rename", side_effect=OSError(errno.EIO, "io")):
            s.tick()
        self.assertEqual(open(file, encoding="utf-8").read(), before)
        self.assertEqual(os.listdir(os.path.dirname(file)), ["memory-pressure.json"])


class ReadRing(Base):
    def test_no_file_is_none_a_ring_that_is_not_a_list_of_samples_raises_never_reads_as_empty(self):
        d = self.scratch("pressure-read-")
        self.assertIsNone(P.read_ring(os.path.join(d, "none.json")))
        good = f'{{"ts": "{at(0)}", "some_avg10": 1, "full_avg10": 1, "mem_available_mb": 1}}'
        for bad in ("", "[", "{}", '[{"ts": "x", "some_avg10": 1, "full_avg10": 1, "mem_available_mb": 1}]',
                    f'[{{"ts": "{at(0)}", "some_avg10": "1", "full_avg10": 1, "mem_available_mb": 1}}]',
                    f'[{{"ts": "{at(0)}", "some_avg10": NaN, "full_avg10": 1, "mem_available_mb": 1}}]',
                    f'[{{"ts": "{at(0)}", "some_avg10": 1, "full_avg10": 1}}]'):
            with open(os.path.join(d, "r.json"), "w", encoding="utf-8") as fh:
                fh.write(bad)
            with self.assertRaises(P.BadRing, msg=f"refused: {bad}"):
                P.read_ring(os.path.join(d, "r.json"))
        with open(os.path.join(d, "r.json"), "w", encoding="utf-8") as fh:
            fh.write(f"[{good}]")
        self.assertEqual(len(P.read_ring(os.path.join(d, "r.json"))), 1, "control: a good ring is read")


class Summary(Base):
    def test_last_readings_and_the_worst_of_the_last_hour_with_when_older_and_future_samples_are_not_in_it(self):
        def s(minute, some, full, avail):
            return {"ts": at(minute), "some_avg10": some, "full_avg10": full, "mem_available_mb": avail}
        ring = [s(-90, 99, 99, 1), s(-50, 10, 1, 900), s(-30, 40, 2, 300), s(-20, None, 8, None), s(-1, 0, 0, 2000), s(0, 1, 0, 1900), s(5, 100, 100, 0)]
        out = P.summary(ring, T0)
        self.assertEqual(out["last"], ring[-3:])
        self.assertEqual(out["hour"], {"samples": 5, "some_avg10": {"value": 40, "ts": at(-30)}, "full_avg10": {"value": 8, "ts": at(-20)}, "mem_available_mb": {"value": 300, "ts": at(-30)}})
        self.assertEqual((out["samples"], out["since"], out["interval_s"]), (7, at(-90), 60))
        self.assertEqual(P.summary([s(-61, 50, 50, 50)], T0)["hour"], {"samples": 0, "some_avg10": None, "full_avg10": None, "mem_available_mb": None}, "an hour with no samples has no worst")
        self.assertEqual(P.HOUR_MS, 3600000)
        self.assertEqual(list(out), ["status", "interval_s", "samples", "since", "last", "hour"], "key order is the wire's")


class HostOp(Base):
    def test_the_host_op_carries_the_pressure_none_before_the_first_sample_failed_for_a_bad_ring_the_summary_otherwise(self):
        d = self.scratch("pressure-op-")
        file = os.path.join(d, "memory-pressure.json")

        def no(*_a, **_k):
            raise OSError("no")
        ctx = {"host_opts": {"proc": self.proc(), "sys": os.path.join(d, "nosys"), "leases": os.path.join(d, "noleases"), "run": no, "cpus": 2, "statfs": no},
               "pressure_opts": {"file": file, "now": lambda: T0}}
        self.assertEqual(ops.collect("host", ctx)["host"]["memory_pressure"], {"status": "none"})
        with open(file, "w", encoding="utf-8") as fh:
            fh.write("garbage")
        self.assertEqual(ops.collect("host", ctx)["host"]["memory_pressure"]["status"], "failed")
        fresh = os.path.join(d, "fresh.json")
        P.sampler(file=fresh, proc=self.proc(), now=lambda: T0).tick()
        h = ops.collect("host", {**ctx, "pressure_opts": {"file": fresh, "now": lambda: T0}})["host"]
        self.assertEqual(h["status"], "ok", "the machine section is still the machine")
        self.assertEqual(h["memory_pressure"]["hour"]["some_avg10"], {"value": 12.5, "ts": at(0)})
        self.assertEqual(P.memory_pressure(fresh, lambda: T0)["last"][0]["mem_available_mb"], 400)


if __name__ == "__main__":
    unittest.main()
