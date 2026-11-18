#!/usr/bin/env python3
"""gzcoord/carrier/main.py stop_on_signals: a TERM raised inside INT's handler (inside stop.set(), which holds the
Event's non-reentrant lock) must not deadlock, and the carrier's stop must be set once. The Event here raises the second
signal from within set(); a lock that cannot be re-taken turns a re-entry into a failure instead of a hang. Plain script."""
from __future__ import annotations

import os
import signal
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from gzcoord.carrier import main as carrier_main  # noqa: E402

fails = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    fails += 0 if ok else 1


class NestingEvent(threading.Event):
    """set() takes a plain lock, raises `second` while holding it, then sets: what a signal landing inside Event.set() sees."""

    def __init__(self, second: int) -> None:
        super().__init__()
        self.second = second
        self.lock = threading.Lock()
        self.calls = 0
        self.reentered = False

    def set(self) -> None:
        self.calls += 1
        if not self.lock.acquire(timeout=0.5):
            self.reentered = True   # a real Event would hang here
            return
        try:
            if self.calls == 1:
                signal.raise_signal(self.second)
            super().set()
        finally:
            self.lock.release()


def old_install(stop: threading.Event) -> None:
    def h(*_: object) -> None:
        stop.set()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, h)


def run_case(install, first: int, second: int) -> NestingEvent:
    saved = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
    ev = NestingEvent(second)
    try:
        install(ev)
        signal.raise_signal(first)
    finally:
        for s, h in saved.items():
            signal.signal(s, h)
    return ev


def main() -> int:
    for first, second, label in ((signal.SIGINT, signal.SIGTERM, "TERM inside INT"), (signal.SIGTERM, signal.SIGINT, "INT inside TERM")):
        ev = run_case(carrier_main.stop_on_signals, first, second)
        check(f"{label}: stop is set, set() called once, no re-entry", ev.is_set() and ev.calls == 1 and not ev.reentered,
              f"set={ev.is_set()} calls={ev.calls} reentered={ev.reentered}")
        ctl = run_case(old_install, first, second)
        check(f"{label}: positive control, the old handler re-enters set()", ctl.reentered)
    # Two signals one after the other, the first handler already returned: a flag reset after set() would call set() twice.
    saved = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
    ev = NestingEvent(signal.SIGTERM)
    ev.calls = 1   # skips the nesting branch: this case sends its signals itself
    try:
        carrier_main.stop_on_signals(ev)
        signal.raise_signal(signal.SIGTERM)
        signal.raise_signal(signal.SIGINT)
    finally:
        for s, h in saved.items():
            signal.signal(s, h)
    check("a later signal after the first handler returned changes nothing", ev.calls == 2 and ev.is_set(),
          f"calls={ev.calls} (1 preset + 1 expected)")
    print("FAILED" if fails else "all ok")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
