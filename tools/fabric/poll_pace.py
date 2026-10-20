"""tools/fabric/poll_pace.py — how long a poller waits between looks.

`fabric-pr wait-merged` and `pr_review_status --wait` looked every 30 s for as long as they were asked
to, and a fleet of sessions each waiting on a PR spent one GitHub account's 5000-call hour in minutes
(2026-10-20). A wait is long precisely because nothing is happening, so the interval grows while
nothing changes and falls back the moment something does; and when GitHub says the budget is gone the
next look is at the reset, not before.

  Pace(interval)       the caller's --interval is the floor and the first wait
  pace.nap(changed)    seconds to sleep: `interval` after a poll that read something new, then half
                       again longer after each poll that read the same, to at most GROWTH_CAP
  pace.until_reset(e)  the wait a rate-limited poll implies, or None

The clock is the caller's: nothing here sleeps, reads the time, or calls GitHub.
"""
from __future__ import annotations

import datetime

GROWTH = 1.5
# 5 minutes: a state change is still seen within 5 minutes, and an hour-long wait costs 12 looks, not 120.
# An explicit --interval above it is the caller's and is kept.
GROWTH_CAP = 300


class Pace:
    def __init__(self, interval: int):
        self.interval = interval
        self.current = float(interval)

    def nap(self, changed: bool) -> int:
        """Seconds to wait before the next look, given whether the last one read something new."""
        if changed:
            self.current = float(self.interval)
        else:
            self.current = min(self.current * GROWTH, float(max(self.interval, GROWTH_CAP)))
        return max(1, int(round(self.current)))


def until_reset(reset: float | None, now: float) -> int | None:
    """Seconds until a limit that was hit ends (a second past it), or None when it was not the primary
    limit or the reset is already behind us."""
    if reset is None:
        return None
    wait = int(reset - now) + 1
    return wait if wait > 0 else None


def reset_clock(reset: float) -> str:
    return datetime.datetime.fromtimestamp(float(reset), datetime.timezone.utc).strftime("%H:%MZ")
