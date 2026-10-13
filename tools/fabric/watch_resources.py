#!/usr/bin/env python3
"""tools/fabric/watch_resources.py — what this account and this host cost, for fabric-watch's identity header.

  ProcSampler(uid).sample()   this account's processes, summed from /proc: {"procs", "rss_kb", "cpu_pct"}. A process
                              is the account's by its EFFECTIVE uid (the one `ps -u` selects by). cpu_pct is the ticks
                              the processes present in BOTH samples used over the wall time between them, 100 = one
                              core; the first sample, and one taken before time passed, has none (None): a half-observed
                              life is not a rate. rss_kb is the sum of VmRSS, which counts a shared page once for each
                              process that maps it: a ceiling, not a footprint.
  host_load() / host_memory() /proc/loadavg's three averages; /proc/meminfo's MemAvailable and MemTotal in kB.
  DiskUse(path)               `du -sk -x path`, refreshed at most every REFRESH_S in a thread of its own, never on the
                              caller's: value() answers at once with the last reading or None, and says how old it is.

It reads /proc/<pid>/stat, /proc/<pid>/status, /proc/loadavg and /proc/meminfo, and never environ, cmdline, maps or fd
(an agent's environment holds its credentials). Every reader takes the /proc root, so a test gives it a fixture.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Callable

REFRESH_S = 600.0
DU_TIMEOUT_S = 300


def _status(proc: str, pid: str) -> dict[str, str] | None:
    try:
        with open(os.path.join(proc, pid, "status"), encoding="utf-8", errors="replace") as fh:
            return {k: v.strip() for k, _, v in (line.partition(":") for line in fh)}
    except OSError:
        return None


def _ticks(proc: str, pid: str) -> tuple[int, int] | None:
    """(utime + stime, starttime) of a process, from its stat line (the command name may hold spaces and parentheses:
    the fields start after the last `)`)."""
    try:
        with open(os.path.join(proc, pid, "stat"), encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        fields = text[text.rindex(")") + 2:].split()
        return int(fields[11]) + int(fields[12]), int(fields[19])
    except (OSError, ValueError, IndexError):
        return None


class ProcSampler:
    def __init__(self, uid: int | None = None, proc: str = "/proc", clock: Callable[[], float] = time.monotonic,
                 hertz: int | None = None):
        self.uid = os.geteuid() if uid is None else uid
        self.proc, self.clock = proc, clock
        self.hertz = hertz or os.sysconf("SC_CLK_TCK")
        self._last: tuple[float, dict[tuple[str, int], int]] | None = None

    def sample(self) -> dict:
        rss = procs = 0
        ticks: dict[tuple[str, int], int] = {}
        try:
            names = [n for n in os.listdir(self.proc) if n.isdigit()]
        except OSError:
            names = []
        for pid in names:
            status = _status(self.proc, pid)
            if status is None:
                continue                                       # exited between the listing and the read
            try:
                if int(status.get("Uid", "").split()[1]) != self.uid:
                    continue
            except (IndexError, ValueError):
                continue
            procs += 1
            try:
                rss += int(status.get("VmRSS", "0 kB").split()[0])    # a kernel thread has none
            except (IndexError, ValueError):
                pass
            t = _ticks(self.proc, pid)
            if t is not None:
                ticks[(pid, t[1])] = t[0]
        now = self.clock()
        cpu = None
        if self._last is not None:
            then, before = self._last
            wall = now - then
            both = [k for k in ticks if k in before]
            if wall > 0:
                cpu = round(100.0 * sum(ticks[k] - before[k] for k in both) / (wall * self.hertz), 1)
        self._last = (now, ticks)
        return {"procs": procs, "rss_kb": rss, "cpu_pct": cpu}


def host_load(proc: str = "/proc") -> tuple[float, float, float] | None:
    try:
        with open(os.path.join(proc, "loadavg"), encoding="utf-8") as fh:
            a, b, c = fh.read().split()[:3]
        return float(a), float(b), float(c)
    except (OSError, ValueError):
        return None


def host_memory(proc: str = "/proc") -> tuple[int, int] | None:
    """(MemAvailable, MemTotal) in kB."""
    try:
        with open(os.path.join(proc, "meminfo"), encoding="utf-8") as fh:
            values = {k: v for k, _, v in (line.partition(":") for line in fh)}
        return int(values["MemAvailable"].split()[0]), int(values["MemTotal"].split()[0])
    except (OSError, KeyError, ValueError, IndexError):
        return None


def human_kb(kb: int | float) -> str:
    size = float(kb)
    for unit in ("kB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "kB" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class DiskUse:
    """The disk use of `path`, read in the background."""

    def __init__(self, path: str, run: Callable[..., object] = subprocess.run, clock: Callable[[], float] = time.monotonic,
                 refresh_s: float = REFRESH_S):
        self.path, self.run, self.clock, self.refresh_s = path, run, clock, refresh_s
        self._kb: int | None = None
        self._at: float | None = None
        self._why: str | None = None
        self._started: float | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def poll(self) -> None:
        """Starts a reading when none is running and the last is older than refresh_s (or there is none). Never waits."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            if self._started is not None and self.clock() - self._started < self.refresh_s:
                return
            self._started = self.clock()
            self._thread = threading.Thread(target=self._read, name="watch-du", daemon=True)
            self._thread.start()

    def _read(self) -> None:
        kb, why = None, None
        try:
            r = self.run(["du", "-sk", "-x", self.path], capture_output=True, text=True, timeout=DU_TIMEOUT_S,
                         stdin=subprocess.DEVNULL, check=False)
            kb = int(str(r.stdout).split()[0]) if str(r.stdout).strip() else None     # type: ignore[attr-defined]
            if kb is None:
                why = "du answered nothing"
        except FileNotFoundError:
            why = "du: not found"
        except subprocess.TimeoutExpired:
            why = f"du: no answer within {DU_TIMEOUT_S} s"
        except (OSError, ValueError, IndexError) as e:
            why = f"du: {getattr(e, 'strerror', None) or type(e).__name__}"
        with self._lock:
            if kb is not None:
                self._kb, self._at, self._why = kb, self.clock(), None
            else:
                self._why = why                                # the last good reading stays, with its age

    def value(self) -> tuple[int | None, float | None, str | None]:
        """(kB, age in seconds, why the last reading failed): the last good reading, or None before there is one."""
        with self._lock:
            return self._kb, (None if self._at is None else self.clock() - self._at), self._why

    def wait(self, timeout: float = 5.0) -> None:
        """Waits for the running reading: for a test, and for --once, which draws once."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
