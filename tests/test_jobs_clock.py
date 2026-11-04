#!/usr/bin/env python3
"""The clock:<UTC time> blocker of fabric-jobs (tools/fabric/jobsparts/blockers.py): its form, its check against a
replaced now(), and the refresh that evaluates it however the caller asked. The command-level cases (block refusing a
past time, --stored, switch) are in tests/test_jobs_switch.py. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import datetime
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, this script's own directory

own_instance_tree()
ROOT = os.path.dirname(HERE)
T = "clock:2026-10-30T17:00:00Z"
EPOCH = datetime.datetime(2026, 10, 30, 17, 0, 0, tzinfo=datetime.timezone.utc).timestamp()


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:500]}"))
        fails += not good

    spec = importlib.util.spec_from_file_location("jobs_clock", os.path.join(ROOT, "tools", "fabric", "jobs.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    bl, Refused = mod.blockers, mod.Refused

    def refused(text: str) -> str:
        try:
            bl.normalise(text)
        except Refused as e:
            return str(e)
        return ""

    check("normalise keeps seconds", bl.normalise(T) == T)
    check("…and adds them when left out", bl.normalise("clock:2026-10-30T17:00Z") == T)
    check("…whatever surrounds it", bl.normalise("  clock:2026-10-30T17:00Z ") == T)
    check("an offset is refused with the form named", "trailing Z" in refused("clock:2026-10-30T17:00+02:00") and "clock:" in refused("clock:2026-10-30T17:00+02:00"))
    check("a bare local time is refused", bool(refused("clock:2026-10-30T17:00")))
    check("a lowercase z is refused", bool(refused("clock:2026-10-30T17:00z")))
    check("a date that does not exist is refused", "does not exist" in refused("clock:2026-02-30T10:00Z"))
    check("hour 24 and second 60 are refused", bool(refused("clock:2026-10-30T24:00Z")) and bool(refused("clock:2026-10-30T10:00:60Z")))
    check("a leap day that exists is accepted", bl.normalise("clock:2028-02-29T10:00Z") == "clock:2028-02-29T10:00:00Z")
    check("the form is named in FORMS", "clock:" in bl.FORMS)

    clock = [EPOCH - 1]
    bl.now = lambda: clock[0]
    c = bl.check_clock(EPOCH)
    check("one second before the time it waits, saying until when and for how long", c.state == "waiting" and c.detail == "until 2026-10-30T17:00:00Z, in 0h1m", c)
    clock[0] = EPOCH - 3 * 3600 - 30 * 60
    check("…hours and minutes", bl.check_clock(EPOCH).detail == "until 2026-10-30T17:00:00Z, in 3h30m", bl.check_clock(EPOCH))
    clock[0] = EPOCH
    c = bl.check_clock(EPOCH)
    check("at the time it is cleared", c.state == "cleared" and c.detail == "reached 2026-10-30T17:00:00Z", c)

    with tempfile.TemporaryDirectory(prefix="jobs-clock-") as tmp:
        path = os.path.join(tmp, "jobs-blockers.json")
        bl.cache_path = lambda: path
        pr = "pr:o/r#5"
        seed = {pr: {"state": "waiting", "detail": "open", "checked_at": EPOCH - 5}}
        json.dump(seed, open(path, "w"))
        job = {"id": "j1", "state": "blocked", "blockers": [T, pr]}
        clock[0] = EPOCH - 1
        cache = bl.refresh(bl.specs_of(job), check=False)
        check("check=False still evaluates a clock: waiting before the time", cache[T]["state"] == "waiting", cache)
        check("…and checks nothing else (the pr has no entry changes)", cache[pr]["state"] == "waiting" and cache[pr]["checked_at"] == EPOCH - 5, cache)
        clock[0] = EPOCH + 1
        cache = bl.refresh(bl.specs_of(job), check=False)
        check("…and cleared once the time is reached, with no check", cache[T]["state"] == "cleared", cache)
        check("a clock with a waiting pull request stays blocked", bl.cleared_flag(job, cache) is False, cache)
        alone = {"id": "j2", "state": "blocked", "blockers": [T]}
        check("a lone cleared clock clears the job", bl.cleared_flag(alone, cache) is True)
        clock[0] = EPOCH - 500
        check("a cleared clock stays cleared in the cache, as the others", bl.refresh([T], check=True)[T]["state"] == "cleared")
        bl.forget([T])
        check("…until forget starts it over", bl.refresh([T], check=False)[T]["state"] == "waiting")
        # TTL: a waiting clock checked a second ago is evaluated again at once
        clock[0] = EPOCH + 5
        check("a waiting clock is not held back by CACHE_TTL_S", bl.refresh([T], check=True)[T]["state"] == "cleared")
        check("an imported past clock normalises to its stored shape", bl.normalise("clock:2020-01-01T00:00:00Z") == "clock:2020-01-01T00:00:00Z")

    print(f"\ntest_jobs_clock: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
