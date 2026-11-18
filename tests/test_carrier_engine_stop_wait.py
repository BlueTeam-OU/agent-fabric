#!/usr/bin/env python3
"""gzcoord/carrier/engine.py Carrier.stop: a stop signal landing while the main thread is inside stop.wait() (the reconnect
backoff, engine.run) must not take a lock the interrupted thread holds. The handler is main.stop_on_signals. A
threading.Event as the stop is the positive control: the main thread holds its condition lock inside wait(), so the
handler's set() hangs. Each case runs in a child process with a deadline, so a hang is a failure, not a stuck suite.
Plain script."""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from gzcoord.carrier import engine  # noqa: E402

CHILD = r'''
import os, signal, sys, threading, time
sys.path.insert(0, os.path.join(sys.argv[1], "tools", "fabric"))
from gzcoord.carrier import engine, main as carrier_main
if sys.argv[2] == "event":
    stop = threading.Event()
    carrier_main.stop_on_signals(stop)
    # A deterministic window: the signal arrives while wait() holds the condition lock, not by luck of timing.
    orig = stop._cond.wait
    def held(timeout=None):
        signal.raise_signal(signal.SIGTERM)
        return orig(timeout)
    stop._cond.wait = held
    stop.wait(30)
else:
    stop = engine.Carrier.__dataclass_fields__["stop"].default_factory()
    carrier_main.stop_on_signals(stop)
    threading.Timer(0.3, lambda: signal.raise_signal(signal.SIGTERM)).start()
    t0 = time.monotonic()
    got = stop.wait(30)
    assert got and time.monotonic() - t0 < 5, (got, time.monotonic() - t0)
print("returned")
'''

fails = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    fails += 0 if ok else 1


def run(kind: str) -> tuple[bool, str]:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    try:
        p = subprocess.run([sys.executable, "-I", "-c", CHILD, ROOT, kind], capture_output=True, text=True,
                           timeout=6, check=False, env=env)
    except subprocess.TimeoutExpired:
        return False, "hung"
    return p.returncode == 0 and "returned" in p.stdout, p.stderr.strip()[-300:]


def main() -> int:
    ok, d = run("flag")
    check("a TERM inside the carrier's stop.wait() ends the wait promptly", ok, d)
    ok, d = run("event")
    check("positive control: the same signal inside threading.Event.wait() hangs", not ok and d == "hung", f"ok={ok} {d}")

    check("fresh flag is clear", not engine.StopFlag().is_set())
    ticks: list[float] = []
    now = [0.0]

    def sleep(s: float) -> None:
        ticks.append(s)
        now[0] += s
    g = engine.StopFlag(sleep=sleep, clock=lambda: now[0])
    check("wait(0.25) times out false in slices of at most SLICE", g.wait(0.25) is False and max(ticks) <= g.SLICE
          and abs(sum(ticks) - 0.25) < 1e-9, str(ticks))
    t = [0.0]

    def sleep_then_set(s: float) -> None:
        t[0] += s   # time moves, so a flag that ignores set() times out false instead of looping
        h.set()
    h = engine.StopFlag(sleep=sleep_then_set, clock=lambda: t[0])
    check("a flag set during a slice ends the wait true", h.wait(5) is True)

    def boom(s: float) -> None:
        raise AssertionError("slept")
    check("wait(0) on a clear flag returns false without sleeping", engine.StopFlag(sleep=boom).wait(0) is False)
    print("FAILED" if fails else "all ok")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
