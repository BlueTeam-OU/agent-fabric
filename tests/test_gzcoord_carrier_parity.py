#!/usr/bin/env python3
"""tools/fabric/gzcoord/carrier/parity.py (ADR-064 rule 11): the report
counts per carrier what was delivered, missed and duplicated over every
(MESSAGE-ID, addressee) pair of a window, names the cause of each miss from
the sender's record, separates late copies by kind, counts compressed and
chunked messages, and says whether the rollback drill lost anything. Built on
synthetic logs with the answers known by construction. Plain script: prints
ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from gzcoord.carrier import parity as P  # noqa: E402
from gzcoord.carrier import record  # noqa: E402

fails = 0
T0 = 1_792_000_000      # 2026-10-14, any fixed second
ISO = lambda s: __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime(T0 + s))  # noqa: E731


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def mid(sec: int, n: int = 0) -> str:
    h = f"{(T0 + sec) * 1000:012x}"
    return f"{h[:8]}-{h[8:]}-7000-8000-{n:012x}"


def arr(m: str, who: str, carrier: str, sec: int, verdict: str = "ok") -> dict:
    return {"mid": m, "addressee": who, "carrier": carrier, "t": ISO(sec), "verdict": verdict}


def main() -> int:
    A, B, C = "h/alpha", "h/beta", "h/gamma"
    m1, m2, m3, m4, m5, m6 = (mid(10 * i, i) for i in range(1, 7))
    arrivals = [
        arr(m1, B, "relay", 11), arr(m1, B, "interweave", 11),                      # both
        arr(m2, B, "relay", 21),                                                      # interweave missed: blocked
        arr(m3, B, "relay", 31), arr(m3, B, "interweave", 32), arr(m3, B, "interweave", 40),   # a duplicate
        arr(m4, C, "interweave", 45),                                                 # relay missed
        arr(m5, B, "relay", 300), arr(m5, B, "interweave", 301, "mismatch"),         # late, a mismatch
        arr(m6, C, "relay", 66),                                                      # broadcast, interweave: not queued
    ]
    senders = {"alpha": [
        {"mid": m1, "to": "beta", "enc": "plain", "queued": ISO(10), "state": "done"},
        {"mid": m2, "to": "beta", "enc": "compressed", "queued": ISO(20), "state": "blocked", "code": "UnauthorizedPeer"},
        {"mid": m3, "to": "beta", "enc": "chunked", "queued": ISO(30), "state": "done"},
        {"mid": m5, "to": "beta", "enc": "plain", "queued": ISO(50), "state": "done"},
        {"mid": mid(70, 7), "to": "gamma", "enc": "plain", "queued": ISO(70), "state": "posted"},   # lost: no copy at all
    ]}
    kinds = {m1: "direct", m2: "direct", m3: "role", m4: "direct", m5: "broadcast", m6: "broadcast"}
    rep = P.compute(arrivals, senders, kinds, (T0, T0 + 1000), drill=(T0 + 15, T0 + 35), host="h")

    check("pairs over the window: six with a copy, one lost", rep["pairs"] == 7, str(rep["pairs"]))
    check("relay: delivered 5, missed 2 (m4, and the lost pair), no duplicates",
          rep["carriers"]["relay"] == {"delivered": 5, "missed": 2, "duplicates": 0, "mismatch": 0},
          str(rep["carriers"]["relay"]))
    ir = rep["carriers"]["interweave"]
    check("interweave: delivered 4, one duplicate copy, one FROM mismatch", ir["delivered"] == 4 and ir["missed"] == 3 and ir["duplicates"] == 1
          and ir["mismatch"] == 1, str(ir))
    causes = {(x["mid"], x["carrier"]): x["cause"] for x in rep["missed"]}
    check("a carrier's miss names its cause: the sender's blocked record",
          "refused by the daemon and still outstanding (UnauthorizedPeer)" in causes[(m2, "interweave")], str(causes))
    check("  a message the sender never queued says so", "recorded no InterWeave delivery" in causes[(m6, "interweave")])
    check("  a relay miss says the inbox recorded no relay copy", "no relay copy" in causes[(m4, "relay")])
    check("the lost pair is listed with the sender's state",
          [(x["sender"], x["state"]) for x in rep["lost"]] == [("alpha", "posted")] and len(rep["lost"]) == 1)
    check("late copies are counted by carrier and kind: m5 (broadcast) arrived 250 s late on both",
          rep["late"]["broadcast"] == {"relay": 1, "interweave": 1} and rep["late"]["direct"] == {"relay": 0, "interweave": 0})
    check("compressed and chunked messages are counted once each from the sender's records",
          rep["messages"] == {"plain": 3, "compressed": 1, "chunked": 1}, str(rep["messages"]))
    check("pairs to a TO-ROLE recipient are counted", rep["role_pairs"] == 1)
    d = rep["drill"]
    check("the drill lists the pairs made inside it; nothing lost when the relay carried each",
          sorted(x["mid"] for x in d["pairs"]) == sorted([m2, m3]) and d["nothing_lost"] is True)
    lost = P.compute([a for a in arrivals if a["mid"] != m2], senders, kinds, (T0, T0 + 1000), drill=(T0 + 15, T0 + 25), host="h")
    check("a drill pair that neither carrier delivered is nothing-lost false (the control)",
          lost["drill"]["nothing_lost"] is False and [x["mid"] for x in lost["drill"]["pairs"]] == [m2], str(lost["drill"]))

    narrow = P.compute(arrivals, senders, kinds, (T0 + 40, T0 + 100), host="h")
    check("the window selects pairs by their first copy (m4, m6, and the lost pair queued at 70)", narrow["pairs"] == 3, str(narrow["pairs"]))

    md = P.render_markdown(rep)
    check("the markdown carries every section the rule names",
          all(s in md for s in ("| relay |", "| interweave |", "Pairs a carrier missed", "Pairs no carrier delivered",
                                "was away", "Framing: 1 message(s) compressed, 1 chunked", "Rollback drill")), md)

    with tempfile.TemporaryDirectory(prefix="gz-par-") as d:
        db = os.path.join(d, "e.db")
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE episodes (message_id TEXT, direction TEXT, metadata_json TEXT)")
        con.executemany("INSERT INTO episodes VALUES (?, 'inbound', ?)",
                        [("a", json.dumps({"TO": "h/beta"})), ("b", json.dumps({"TO-ROLE": "dev"})),
                         ("c", json.dumps({"BROADCAST": "true"})), ("d", "{not json")])
        con.commit()
        con.close()
        check("kinds come from the journal's headers", P.kinds_from_journal(db) == {"a": "direct", "b": "role", "c": "broadcast"})

        box = record.Outbox(os.path.join(d, "iw"), iso_now=lambda: ISO(0))
        box.queue("M1", "beta", "t", 1, "chunked")
        box.queue("M2", "beta", "t2", 1)
        box.blocked(box.deliveries[("M2", "beta")], "UnauthorizedPeer")
        box.queue("M3", "beta", "t3", 1)
        box.receipt("M3", "beta")
        box.close()
        box = record.Outbox(os.path.join(d, "iw"), iso_now=lambda: ISO(0))
        got = {(x["mid"]): x["state"] for x in record.read_deliveries(os.path.join(d, "iw"))}
        box.close()
        check("a report reads the sender's record without locking or rewriting it: done, blocked, queued",
              got == {"M1": "queued", "M2": "blocked", "M3": "done"}, str(got))

    print(f"\ntest_gzcoord_carrier_parity: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
