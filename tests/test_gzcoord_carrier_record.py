#!/usr/bin/env python3
"""tools/fabric/gzcoord/carrier/record.py (ADR-064 rule 7): the carrier's
per-recipient delivery record. A delivery is done on its receipt, not on the
daemon's acceptance; the transport message_ids survive every retry and a
restart; a second carrier on the same record is refused; a torn last line is
tolerated and a damaged earlier one is not; compaction moves done deliveries
out without their text and repeats safely after an interruption; the retry
schedule is 1 s doubling to 5 min with no end. Plain script: prints ok/FAIL,
exit 1 on any failure."""
from __future__ import annotations

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from gzcoord.carrier import record as R  # noqa: E402

fails = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def raises(fn, cls=R.RecordError) -> bool:
    try:
        fn()
    except cls:
        return True
    return False


def clock():
    n = [0]

    def tick() -> str:
        n[0] += 1
        return f"2026-10-24T12:00:{n[0]:02d}Z"
    return tick


def lines(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def main() -> int:
    check("the schedule is 1 s doubling to 5 min and stays there",
          [R.backoff(n) for n in (1, 2, 3, 4, 9, 10, 40)] == [1, 2, 4, 8, 256, 300, 300])

    with tempfile.TemporaryDirectory(prefix="gz-rec-") as d:
        box = R.Outbox(os.path.join(d, "iw"), iso_now=clock())
        check("the directory is 0700 and the record 0600",
              oct(os.stat(box.directory).st_mode & 0o777) == "0o700" and oct(os.stat(box.path).st_mode & 0o777) == "0o600")
        a = box.queue("M1", "beta", "text one", 2)
        check("a new delivery has one transport id per payload, 32 hex each, all different",
              len(a.tmids) == 2 and all(len(t) == 32 and int(t, 16) >= 0 for t in a.tmids) and a.tmids[0] != a.tmids[1])
        check("the same message again is the same delivery, ids kept", box.queue("M1", "beta", "text one", 2) is a)
        check("another body under a known id is refused", raises(lambda: box.queue("M1", "beta", "other", 2)))
        check("the same id to another recipient is another delivery",
              box.queue("M1", "gamma", "text one", 1).tmids != a.tmids)
        check("a delivery with no daemon acceptance is outstanding, due at once",
              {x.key for x in box.due(0)} == {("M1", "beta"), ("M1", "gamma")})

        box.retry_after(a, 100.0)
        check("after an attempt it is due after the backoff, not before",
              a not in box.due(100.5) and a in box.due(101.0))
        box.posted(a)
        check("accepted by the daemon is not done: still outstanding until the receipt",
              a in box.outstanding() and a.posted and a.receipt_at is None)
        box.blocked(a, "UnauthorizedPeer")
        check("a refusal no retry mends is kept and the delivery stays pending", a.blocked == "UnauthorizedPeer" and a in box.outstanding())
        tmids = list(a.tmids)
        box.close()

        box = R.Outbox(os.path.join(d, "iw"), iso_now=clock())
        a2 = box.deliveries[("M1", "beta")]
        check("a restart keeps the text, the transport ids and the state",
              a2.text == "text one" and a2.tmids == tmids and a2.posted and a2.blocked == "UnauthorizedPeer")
        check("  and retries at once (the schedule is not persisted)", a2 in box.due(0))
        check("a second carrier on the same record is refused",
              raises(lambda: R.Outbox(os.path.join(d, "iw"), iso_now=clock())))

        check("a receipt naming nothing sent is ignored", box.receipt("NOPE", "beta") is False)
        check("a receipt from the wrong recipient is ignored", box.receipt("M1", "delta") is False)
        check("the recipient's receipt settles the delivery", box.receipt("M1", "beta") is True
              and ("M1", "beta") not in {x.key for x in box.outstanding()})
        check("a second receipt is ignored", box.receipt("M1", "beta") is False)
        box.close()

        box = R.Outbox(os.path.join(d, "iw"), iso_now=clock())
        done = lines(box.done_path)
        check("a done delivery leaves the record for delivered.jsonl, without its text",
              ("M1", "beta") not in box.deliveries and len(done) == 1 and "text" not in done[0]
              and done[0]["mid"] == "M1" and done[0]["to"] == "beta"
              and not [e for e in lines(box.path) if e["mid"] == "M1" and e["to"] == "beta"])
        check("the other recipient's delivery is untouched", ("M1", "gamma") in box.deliveries)
        box.receipt("M1", "gamma")
        box.close()

        # interruption: delivered.jsonl written, the record not yet rewritten
        iw = os.path.join(d, "iw")
        with open(os.path.join(iw, "deliveries.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"e": "queued", "mid": "M2", "to": "beta", "text": "t2", "t": "x", "tmids": ["a" * 32]}) + "\n")
            fh.write(json.dumps({"e": "receipt", "mid": "M2", "to": "beta", "t": "y"}) + "\n")
        with open(os.path.join(iw, "delivered.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"mid": "M2", "to": "beta", "queued": "x", "receipt": "y"}) + "\n")
        box = R.Outbox(iw, iso_now=clock())
        keys = [(o["mid"], o["to"]) for o in lines(box.done_path)]
        check("a compaction interrupted after delivered.jsonl is repeated without a duplicate line",
              keys.count(("M2", "beta")) == 1 and ("M2", "beta") not in box.deliveries)
        box.queue("M3", "beta", "t3", 1)
        box.close()

        with open(os.path.join(iw, "deliveries.jsonl"), "ab") as fh:
            fh.write(b'{"e":"posted","mid":"M3","to"')
        box = R.Outbox(iw, iso_now=clock())
        check("a torn last line (a crash mid-write) is tolerated, the delivery kept",
              ("M3", "beta") in box.deliveries)
        box.close()

        with open(os.path.join(iw, "deliveries.jsonl"), "rb") as fh:
            raw = fh.read()
        with open(os.path.join(iw, "deliveries.jsonl"), "wb") as fh:
            fh.write(b"garbage\n" + raw)
        check("a damaged line before the end refuses the record rather than guess",
              raises(lambda: R.Outbox(iw, iso_now=clock())))

    print(f"\ntest_gzcoord_carrier_record: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
