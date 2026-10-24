#!/usr/bin/env python3
"""tools/fabric/gzcoord/carrier/ledger.py (CARRIER-CONTRACT.md §6): the shown
ledger decides what a session sees. The rule for one copy against the lines
already there (pure); the lock that serialises the inbox paths, including two
processes racing for one message; the interrupted showing found by its pending
line and shown once more, flagged; the rule 9 flagged copy shown at most once;
the torn tail repaired; the old lines compacted; and what the carrier reads of
it. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from gzcoord.carrier import ledger as L  # noqa: E402

fails = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def line(mid: str, via: str, pending: bool = False, flagged: bool = False) -> dict:
    out = {"mid": mid, "via": via, "t": "2026-10-24T00:00:00Z"}
    if pending:
        out["pending"] = True
    if flagged:
        out["flagged"] = True
    return out


def d(lines, via, verdict="ok", mid="M"):
    return L.decide(lines, mid, via, verdict)


def read(path: str) -> list[dict]:
    return [json.loads(x) for x in open(path) if x.strip()]


RACER = """
import sys, os, time
sys.path.insert(0, sys.argv[1])
from gzcoord.carrier import ledger as L
led = L.Ledger(sys.argv[2], iso_now=lambda: "2026-10-24T00:00:00Z")
held = led.exclusive()
dec = held.decide("M-RACE", sys.argv[3], "ok")
if dec.show:
    held.pending("M-RACE", sys.argv[3])
    time.sleep(0.2)                       # the showing takes a while: the others must wait for it
    with open(sys.argv[4], "a") as fh:
        fh.write(sys.argv[3] + "\\n")
    held.finish()
else:
    held.release()
"""


def main() -> int:
    # -- the rule, pure -----------------------------------------------------
    fin_relay = [line("M", "relay")]
    check("no line: show it, with a pending line first", d([], "relay").show and d([], "relay").kind == "absent"
          and d([], "relay").append_pending)
    check("an IW copy with a mismatch and no other line is shown plainly, not as a re-show",
          d([], "interweave", "mismatch").show and not d([], "interweave", "mismatch").flagged)
    only_pending = [line("M", "relay", pending=True)]
    r = d(only_pending, "relay")
    check("a pending line with no final: shown once more, flagged may-repeat, no new pending line",
          r.show and r.may_repeat and r.kind == "repeat" and not r.append_pending)
    check("... whichever carrier asks", d(only_pending, "interweave").show and d(only_pending, "interweave").may_repeat)
    shown_by_relay = [line("M", "relay", pending=True), line("M", "relay")]
    check("a final line: the relay's copy again is not shown", not d(shown_by_relay, "relay").show)
    check("... nor an ok IW copy", not d(shown_by_relay, "interweave", "ok").show)
    shown_by_iw = [line("M", "interweave", pending=True), line("M", "interweave")]
    check("shown by the carrier first: the relay's copy is not shown", not d(shown_by_iw, "relay").show)
    check("... nor a mismatch IW copy again", not d(shown_by_iw, "interweave", "mismatch").show)
    f = d(shown_by_relay, "interweave", "mismatch")
    check("rule 9: the relay's copy shown, the IW copy reveals a mismatch: shown again, flagged, naming the message",
          f.show and f.flagged and f.of == "M" and f.kind == "flagged" and f.append_pending)
    flagged_done = shown_by_relay + [line("M", "interweave", pending=True, flagged=True), line("M", "interweave", flagged=True)]
    check("a flagged copy is shown at most once", not d(flagged_done, "interweave", "mismatch").show)
    flagged_pending = shown_by_relay + [line("M", "interweave", pending=True, flagged=True)]
    r = d(flagged_pending, "interweave", "mismatch")
    check("a flagged pending-only entry is shown once more, flagged and may-repeat",
          r.show and r.flagged and r.may_repeat and not r.append_pending)
    check("a mismatch copy is flagged only when the copy shown was the relay's (control: IW first)",
          not d(shown_by_iw, "interweave", "mismatch").show)
    check("another MESSAGE-ID's lines decide nothing", d(shown_by_relay, "relay", mid="OTHER").show)
    hh = [dict(x, h="aaaa") for x in shown_by_relay]
    check("a different message that reuses a shown MESSAGE-ID is not that message: it is shown",
          L.decide(hh, "M", "relay", "ok", "bbbb").show and not L.decide(hh, "M", "relay", "ok", "aaaa").show)
    check("a line from before the hash existed matches any body of its id (the old rule)",
          not L.decide(shown_by_relay, "M", "relay", "ok", "bbbb").show)
    check("a final line of another body settles nothing for this one",
          not L.settled([dict(x, h="aaaa") for x in fin_relay], "ok", "bbbb") and L.settled([dict(x, h="aaaa") for x in fin_relay], "ok", "aaaa"))
    check("the body hash ignores line endings and trailing space, and tells two texts apart",
          L.body_hash("a\r\nb\n") == L.body_hash("a\nb") and L.body_hash("a") != L.body_hash("b"))

    # -- settled: what the carrier stops listing -----------------------------
    fin_iw = [line("M", "interweave")]
    check("unseen settles an ok copy on any final line", L.settled(fin_relay, "ok") and L.settled(fin_iw, "ok"))
    check("a mismatch copy is settled only by the carrier's own final line", not L.settled(fin_relay, "mismatch")
          and L.settled(fin_iw, "mismatch"))
    check("no final line settles nothing", not L.settled(None, "ok") and not L.settled([], "mismatch"))

    with tempfile.TemporaryDirectory(prefix="gz-led-") as dd:
        path = os.path.join(dd, "agents", "me", "gzcoord-shown.jsonl")
        led = L.Ledger(path, iso_now=lambda: "2026-10-24T00:00:00Z")
        held = led.exclusive()
        check("the file and directory are owner-only", oct(os.stat(path).st_mode & 0o777) == "0o600"
              and oct(os.stat(os.path.dirname(path)).st_mode & 0o777) == "0o700")
        held.pending("M-1", "relay")
        check("the pending line is on disk before the showing", read(path) == [line("M-1", "relay", pending=True) | {}])
        held.finish()
        check("finish writes the final line, then releases", [x.get("pending") for x in read(path)] == [True, None]
              and read(path)[1]["via"] == "relay")

        # -- an interrupted showing ---------------------------------------
        held = led.exclusive()
        held.pending("M-2", "interweave")
        held.release()                         # the process died after the pending line
        held = led.exclusive()
        r = held.decide("M-2", "relay", "ok")
        check("a pending-only entry is found by the next inbox path", r.show and r.may_repeat)
        held.finish_repeat("M-2", "relay")
        held.finish()
        h2 = led.exclusive()
        check("... settled after the repeat", not h2.decide("M-2", "interweave", "ok").show)
        h2.release()

        # -- two inbox paths cannot both hold the lock ---------------------
        held = led.exclusive()
        order: list[str] = []

        def second():
            h = led.exclusive()
            order.append("second")
            h.release()
        t = threading.Thread(target=second)
        t.start()
        time.sleep(0.3)
        order.append("first-done")
        held.release()
        t.join(10)
        check("a second inbox path waits for the first to finish", order == ["first-done", "second"], str(order))

        # -- a torn last line does not swallow the next ---------------------
        with open(path, "ab") as fh:
            fh.write(b'{"mid":"TORN","via":"re')
        held = led.exclusive()
        held.pending("M-3", "relay")
        held.finish()
        mids = [x["mid"] for x in read(path)]
        check("a torn tail is cut before the next append", "TORN" not in mids and mids[-2:] == ["M-3", "M-3"], str(mids))

        # -- the carrier's read ----------------------------------------------
        fl = L.final_lines(path)
        check("the carrier reads final lines only, under a shared lock", set(fl) == {"M-1", "M-2", "M-3"}
              and all(not x.get("pending") for v in fl.values() for x in v))
        check("a ledger that is not there holds nothing", L.final_lines(os.path.join(dd, "none")) == {})

        # -- the ledger is never rotated (CARRIER-CONTRACT.md §6) ---------------------
        old = os.path.join(dd, "old.jsonl")
        with open(old, "w") as fh:
            for i in range(2000):
                fh.write(json.dumps({"mid": f"O-{i}", "via": "relay", "t": "2020-01-01T00:00:00Z"}) + "\n")
        before = os.path.getsize(old)
        L.Ledger(old, iso_now=lambda: "T").exclusive().release()
        check("an old, large ledger loses nothing at open: a line dropped would show its copy again",
              os.path.getsize(old) == before and len(read(old)) == 2000)

        # -- two processes racing for one message ---------------------------------
        rpath = os.path.join(dd, "race.jsonl")
        out = os.path.join(dd, "shown.txt")
        procs = [subprocess.Popen([sys.executable, "-c", RACER, os.path.join(ROOT, "tools", "fabric"), rpath, via, out])
                 for via in ("relay", "interweave", "relay", "interweave", "relay")]
        rcs = [p.wait(timeout=60) for p in procs]
        shown = open(out).read().split() if os.path.exists(out) else []
        check("five racers, one message: exactly one shows it, whichever carrier it was", rcs == [0] * 5 and len(shown) == 1, str(shown))
        lines = read(rpath)
        check("... and the ledger holds one pending and one final line for it",
              [bool(x.get("pending")) for x in lines] == [True, False], str(lines))
    print(f"\ntest_gzcoord_carrier_ledger: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
