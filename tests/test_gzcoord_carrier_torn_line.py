#!/usr/bin/env python3
"""A line torn by a crash and cut by jsonl.repair, at every byte it can be torn at: what the next inbox pass does with
the message (job j143).

The carrier's files and what a torn last line means in each:
  gzcoord-shown.jsonl   the pending line precedes the showing; the final line follows the showing. Torn pending: nothing was
                        shown, the message is shown as new. Torn final: the message WAS shown, and the cut leaves a pending
                        line without its final, which the ledger's rule shows once more flagged "may repeat" (the same as an
                        inbox that died between the two appends) and settles. Never lost, never silently twice.
  inbox.jsonl (Spool)   a torn kept arrival was never receipted, so the sender resends and it is kept again.
  gzcoord-arrivals.jsonl
                        evidence for the parity report only: a cut line is a missing row, delivery is untouched.
The byte that matters is the one before the newline: the tail is then whole JSON, and a reader that did not know the
repair would cut it settles a record that the repair un-settles (ledger.final_lines).
Plain script: ok/FAIL, exit 1."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import test_gzcoord_carrier_inbox as C  # noqa: E402 — its message builders
from gzcoord.carrier import CARRIER_NAME, arrivals  # noqa: E402
from gzcoord.carrier import ledger as L  # noqa: E402
from gzcoord.transport import dedup  # noqa: E402

fails = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def iso() -> str:
    return "T"


def carrier_pass(spool: arrivals.Spool, path: str) -> dict:
    """One pass over what the carrier lists: the same, for the interweave copy."""
    classified: list[dict] = []
    listed = spool.unseen()         # before the lock, as watch.py asks: unseen reads the ledger under LOCK_SH
    lock = L.Ledger(path, iso_now=iso).exclusive()
    try:
        dedup.admit(lock, classified, listed)
        lock.finish()
    except BaseException:
        lock.release()
        raise
    return {"shown": len(classified), "may_repeat": any(c.get("may_repeat") for c in classified)}


def spool_at(d: str, ledger_path: str) -> arrivals.Spool:
    return arrivals.Spool(os.path.join(d, "interweave"), ledger_path, iso_now=iso)


def keep(spool: arrivals.Spool) -> None:
    spool.keep(C.mid(1), C.msg(1), "T", "ok", "x/y")


def lines_written(d: str) -> tuple[bytes, bytes]:
    """The pending and the final line the real writers leave for message 1, to be torn."""
    p = os.path.join(d, "model.jsonl")
    sp = spool_at(os.path.join(d, "model"), p)
    keep(sp)
    carrier_pass(sp, p)
    pending, final, rest = open(p, "rb").read().split(b"\n")
    assert rest == b"" and json.loads(pending).get("pending") and not json.loads(final).get("pending")
    return pending + b"\n", final + b"\n"


def main() -> int:
    d = tempfile.mkdtemp(prefix="gz-torn-")
    try:
        return run(d)
    finally:
        # Importing the inbox suite makes the protocol suite's scratch operator tree; each importer removes it.
        for scratch in [d, *C.P.SCRATCH]:
            shutil.rmtree(scratch, ignore_errors=True)


def run(d: str) -> int:
    n = 0

    def fresh() -> str:
        nonlocal n
        n += 1
        sub = os.path.join(d, f"c{n}")
        os.makedirs(sub)
        return sub

    via = CARRIER_NAME
    pending, final = lines_written(d)

    def ledger_state(sub: str, content: bytes) -> str:
        p = os.path.join(sub, "gzcoord-shown.jsonl")
        open(p, "wb").write(content)
        return p

    # -- the pending line torn: nothing was shown, so the message is new --------------------------------
    bad = []
    for k in range(0, len(pending)):
        sub = fresh()
        p = ledger_state(sub, pending[:k])
        sp = spool_at(sub, p)
        keep(sp)                    # the arrival is journaled before the ledger is touched
        first = carrier_pass(sp, p)
        second = carrier_pass(sp, p)
        if first != {"shown": 1, "may_repeat": False} or second != {"shown": 0, "may_repeat": False}:
            bad.append((k, first, second))
    check(f"[{via}] a pending line torn at any byte: the message is shown as new once, then not again", not bad, str(bad[:3]))

    # -- the final line torn, the newline-less whole-JSON byte included: shown once more, flagged, then settled
    bad = []
    for k in range(0, len(final)):
        sub = fresh()
        p = ledger_state(sub, pending + final[:k])
        sp = spool_at(sub, p)
        keep(sp)
        listed = [r["message_id"] for r in sp.unseen()]
        if listed != [C.mid(1)]:
            bad.append((k, "unseen before the repair", listed))
            continue
        first = carrier_pass(sp, p)
        second = carrier_pass(sp, p)
        whole_lines = [json.loads(x) for x in open(p, "rb").read().split(b"\n") if x]
        if (first != {"shown": 1, "may_repeat": True} or second != {"shown": 0, "may_repeat": False}
                or any(x.get("mid") != C.mid(1) for x in whole_lines)):
            bad.append((k, first, second))
    check(f"[{via}] a final line torn at any byte (the one before its newline included): shown once more, flagged "
          "may repeat, then settled — not lost, not shown a third time", not bad, str(bad[:3]))

    # -- positive controls: the same pass over an untorn ledger ------------------------------------------
    sub = fresh()
    p = ledger_state(sub, pending + final)
    sp = spool_at(sub, p)
    keep(sp)
    first = carrier_pass(sp, p)
    check(f"[{via}] control: a ledger whose final line is whole shows nothing", first["shown"] == 0, str(first))
    sub = fresh()
    p = ledger_state(sub, pending)
    sp = spool_at(sub, p)
    keep(sp)
    first = carrier_pass(sp, p)
    check(f"[{via}] control: a pending line with no final line is shown once more, flagged",
          first["shown"] == 1 and first["may_repeat"], str(first))

    # -- the carrier's spool: an arrival torn mid-keep was never receipted; the sender's resend keeps it once ---
    sub = fresh()
    p = os.path.join(sub, "gzcoord-shown.jsonl")
    sp = spool_at(sub, p)
    keep(sp)
    kept = open(os.path.join(sub, "interweave", "inbox.jsonl"), "rb").read()
    bad = []
    for k in range(0, len(kept)):
        sub2 = fresh()
        os.makedirs(os.path.join(sub2, "interweave"))
        open(os.path.join(sub2, "interweave", "inbox.jsonl"), "wb").write(kept[:k])
        sp2 = spool_at(sub2, os.path.join(sub2, "gzcoord-shown.jsonl"))
        keep(sp2)                    # the resend
        again = spool_at(sub2, os.path.join(sub2, "gzcoord-shown.jsonl"))
        if [r["message_id"] for r in sp2.unseen()] != [C.mid(1)] or [r["message_id"] for r in again.unseen()] != [C.mid(1)]:
            bad.append(k)
    check("a spool line torn at any byte: the resent arrival is kept once and survives a restart", not bad, str(bad[:5]))

    # -- the evidence logs: the cut line is a missing row, the next row is whole ---------------------------------
    for cls, call in ((arrivals.ArrivalLog, lambda a: a.append(C.mid(1), "h/me", "interweave", "ok")),):
        sub = fresh()
        path = os.path.join(sub, "log.jsonl")
        call(cls(path, iso_now=iso))
        whole = open(path, "rb").read()
        bad = []
        for k in range(1, len(whole)):
            open(path, "wb").write(whole[:k])
            call(cls(path, iso_now=iso))
            rows = [json.loads(x) for x in open(path, "rb").read().split(b"\n") if x]
            if len(rows) != 1 or rows[0]["mid"] != C.mid(1):
                bad.append(k)
        check(f"{cls.__name__}: a line torn at any byte is cut and the next one is whole", not bad, str(bad[:5]))

    print(f"\ntest_gzcoord_carrier_torn_line: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
