"""tools/fabric/control/pressure.py — the machine's memory pressure, sampled by
this account's agentd once a minute into a bounded ring in its own state.
The port of runtime/control/pressure.mjs; the ring file is frozen with the
wire (ADR-040 Wave 8): either implementation reads what the other wrote.

The host froze on 2026-10-04 and left nothing to read: journald fell
silent at 16:33, and `fabric-ctl host` only answers for the moment it is
asked. So the daemon samples /proc/pressure/memory — some and full
avg10, the share of the last ten seconds in which some, or all,
non-idle tasks stalled on memory — and MemAvailable, and keeps them in
<state dir>/memory-pressure.json, where the run-up to a freeze is still
there after the reboot. Numbers only. The file is this account's own;
no other account's state is read or written.

A reading the kernel did not give is null, never 0: a kernel without
PSI and a calm machine are different answers.
"""
from __future__ import annotations

import errno
import math
import os
import re
import sys
import time
from typing import Any, Callable

from control.ops import util

SAMPLE_INTERVAL_MS = 60_000
RING_MAX = 1440   # a day of minutes: the evening before a morning's look
HOUR_MS = 3600_000
LAST_N = 3
READINGS = ("some_avg10", "full_avg10", "mem_available_mb")


def ring_file(directory: str | None = None) -> str:
    return os.path.join(util.state_dir() if directory is None else directory, "memory-pressure.json")


def _now_ms() -> float:
    return time.time() * 1000


def sample(proc: str = "/proc", now: Callable[[], float] = _now_ms) -> dict:
    def read(f: str) -> str | None:
        try:
            with open(os.path.join(proc, f), encoding="utf-8", errors="replace") as fh:
                return fh.read()
        except OSError:
            return None
    psi = read("pressure/memory")   # the kernel's /proc/pressure/memory, not instance data

    def avg10(kind: str) -> float | int | None:
        m = re.search(rf"^{kind} avg10=(\d+(?:\.\d+)?) ", psi, re.M | re.A) if psi else None
        return util.whole(float(m.group(1))) if m else None
    av = re.search(r"^MemAvailable:\s+(\d+) kB$", read("meminfo") or "", re.M | re.A)
    return {"ts": util.iso_ms(now()), "some_avg10": avg10("some"), "full_avg10": avg10("full"),
            "mem_available_mb": util.js_round(int(av.group(1)) / 1024) if av else None}


def _finite(v: Any) -> bool:
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return False
    try:
        return math.isfinite(v)
    except OverflowError:
        return False   # an integer past a double: the Node's JSON.parse read it as Infinity


def _is_sample(s: Any) -> bool:
    return (isinstance(s, dict) and isinstance(s.get("ts"), str) and util.date_parse_ms(s["ts"]) is not None
            and all(k in s and (s[k] is None or _finite(s[k])) for k in READINGS))


class BadRing(Exception):
    """What the file holds is wrong, as against a file that could not be read."""


def read_ring(file: str | None = None) -> list[dict] | None:
    """None when there is no ring yet; a ring that is not a list of samples
    raises BadRing — it is never read as an empty one; a read that failed
    raises its own OSError."""
    file = ring_file() if file is None else file
    try:
        with open(file, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except FileNotFoundError:
        return None
    try:
        ring = util.loads(text)
    except ValueError:
        raise BadRing(f"{file}: not JSON") from None
    if not isinstance(ring, list) or not all(_is_sample(s) for s in ring):
        raise BadRing(f"{file}: not a list of samples")
    return ring


def _write_all(fd: int, data: bytes) -> None:
    """os.write may take a prefix (a nearly full disk): the rest is written, or
    the write fails, but a prefix is never what gets published."""
    view = memoryview(data)
    while view:
        n = os.write(fd, view)
        if n <= 0:
            raise OSError(errno.EIO, "write made no progress")
        view = view[n:]


def _write_ring(file: str, ring: list[dict]) -> None:
    """Whole or not at all, and durable: a freeze mid-write must not cost the
    ring, and the minutes before a freeze are what it is for — so the data
    reaches the disk before the rename, and the rename before the next tick.
    Without the two fsyncs a reboot could find the old ring, or an empty file
    under the new name (review of #96)."""
    directory = os.path.dirname(file)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    tmp = f"{file}.{os.getpid()}.tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            _write_all(fd, (util.js_json(ring) + "\n").encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.rename(tmp, file)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass   # not made, or already renamed
        raise
    dfd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def _cause(e: BaseException) -> str:
    """e.code ?? e.message, as the Node said a cause."""
    code = getattr(e, "errno", None)
    return errno.errorcode.get(code, str(e)) if isinstance(code, int) else str(e)


def _stderr(m: str) -> None:
    print(m, file=sys.stderr, flush=True)


class Sampler:
    """One per daemon. tick() takes a sample and persists the ring; a failure is
    one line when it starts and one when it ends, not one a minute. A ring
    whose content is bad is kept aside as <file>.unreadable and a new one
    begun: sampling that stopped for good on a bad file would be the silence
    this exists to end. A ring that could not be read is retried next tick,
    never replaced: a passing I/O error must not cost a day of samples.
    The daemon calls tick() from one thread at a time."""

    def __init__(self, file: str | None = None, proc: str = "/proc", now: Callable[[], float] = _now_ms,
                 max: int = RING_MAX, log: Callable[[str], None] = _stderr) -> None:  # noqa: A002 — the Node's word
        self.file = ring_file() if file is None else file
        self.proc, self.now, self.max, self.log = proc, now, max, log
        self.ring: list[dict] | None = None
        self.failing = False

    def tick(self) -> None:
        try:
            if self.ring is None:
                try:
                    self.ring = read_ring(self.file) or []
                except BadRing as e:
                    os.rename(self.file, f"{self.file}.unreadable")
                    self.log(f"agentd: memory pressure: {e}; kept as {os.path.basename(self.file)}.unreadable, a new ring begun")
                    self.ring = []
            self.ring.append(sample(self.proc, self.now))
            if len(self.ring) > self.max:
                del self.ring[:len(self.ring) - self.max]
            _write_ring(self.file, self.ring)
            if self.failing:
                self.log("agentd: memory pressure: sampling again")
                self.failing = False
        except Exception as e:  # noqa: BLE001 — every failure is the same one line, and the next tick retries
            if not self.failing:
                self.log(f"agentd: memory pressure: cannot keep the ring ({_cause(e)})")
            self.failing = True


def sampler(**kw: Any) -> Sampler:
    return Sampler(**kw)


def summary(ring: list[dict], now: float | None = None) -> dict:
    """The last readings and, per reading, the worst of the last hour with when
    it was: the highest stall shares, the lowest MemAvailable. A sample
    dated ahead of now (a clock set back) is not in the hour."""
    now = _now_ms() if now is None else now
    hour = [s for s in ring if (t := util.date_parse_ms(s["ts"])) is not None and now - HOUR_MS < t <= now]

    def worst(key: str, worse: Callable[[float, float], bool]) -> dict | None:
        w: dict | None = None
        for s in hour:
            if s[key] is not None and (w is None or worse(s[key], w["value"])):
                w = {"value": s[key], "ts": s["ts"]}
        return w
    return {"status": "ok", "interval_s": SAMPLE_INTERVAL_MS // 1000, "samples": len(ring),
            "since": ring[0]["ts"] if ring else None, "last": ring[-LAST_N:],
            "hour": {"samples": len(hour), "some_avg10": worst("some_avg10", lambda a, b: a > b),
                     "full_avg10": worst("full_avg10", lambda a, b: a > b),
                     "mem_available_mb": worst("mem_available_mb", lambda a, b: a < b)}}


def memory_pressure(file: str | None = None, now: Callable[[], float] = _now_ms) -> dict:
    """For the `host` op: `none` before the first sample, `failed` with the
    reason for a ring that cannot be read."""
    try:
        ring = read_ring(ring_file() if file is None else file)
        return {"status": "none"} if ring is None else summary(ring, now())
    except (OSError, BadRing) as e:
        return {"status": "failed", "error": _cause(e)[:200]}
