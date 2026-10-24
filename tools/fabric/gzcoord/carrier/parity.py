"""tools/fabric/gzcoord/carrier/parity.py — the parity report of ADR-064 rule
11, computed from what the carriers and inboxes recorded; it measures, it
never decides. The owner's word on a switch is given on this report
(docs/live-checks/) and is not this code's.

INPUTS (all files an account already keeps, collected by whoever runs the
report; nothing is read from a live process):
  arrivals   every account's gzcoord-arrivals.jsonl: one line per copy
             received {mid, addressee, carrier (relay|interweave), t, verdict}
  senders    every account's interweave/ directory, read by
             record.read_deliveries (who sent what to whom, how it was
             framed, how it ended)
  kinds      {mid: direct|role|broadcast}, from the journals' headers
             (kinds_from_journal): the arrival log does not say, by contract
  window     [start, end): a pair belongs to it when its first copy, by
             either carrier, arrived inside
  drill      [start, end): the interval the InterWeave carrier was switched
             off, for the rollback drill
  offline    seconds after a message was made (its uuid7 timestamp) beyond
             which a copy counts as delivered to an addressee that was away

The report covers every (MESSAGE-ID, addressee) pair in the window; for each
carrier its delivered, missed and duplicate counts; each pair a carrier
missed, with its cause; the copies that arrived late (offline), direct,
role and broadcast apart; the messages compressed and chunked; and the
drill: pairs made inside it and whether each reached the addressee by the
relay and by InterWeave. A pair the sender recorded sending that no copy of
arrived for, and whose receipt has not come, is listed as stranded; one whose
receipt came is a message the addressee filtered out (a TO-ROLE it does not
hold, or a broadcast it is not addressed by), which is no pair at all. The
arrival logs hold only copies ADDRESSED to their owner, so a non-holder of a
role is never counted as a miss of either carrier.
"""
from __future__ import annotations

import calendar
import json
import re
import sqlite3
import time
from collections import defaultdict

CARRIERS = ("relay", "interweave")
UUID7 = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}")
OFFLINE_AFTER_S = 60.0


def parse_t(t: str) -> float:
    return calendar.timegm(time.strptime(t, "%Y-%m-%dT%H:%M:%SZ"))


def made_at(mid: str) -> float | None:
    """When a uuid7 MESSAGE-ID was made, from its 48-bit millisecond prefix."""
    if not UUID7.fullmatch(mid):
        return None
    return int(mid.replace("-", "")[:12], 16) / 1000.0


def kinds_from_journal(db_path: str) -> dict[str, str]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        out = {}
        for mid, meta in con.execute("SELECT message_id, metadata_json FROM episodes WHERE direction='inbound'"):
            try:
                m = json.loads(meta or "{}")
            except ValueError:
                continue
            out[mid] = "broadcast" if m.get("BROADCAST") == "true" else "role" if "TO-ROLE" in m else "direct"
        return out
    finally:
        con.close()


def compute(arrivals: list[dict], senders: dict[str, list[dict]], kinds: dict[str, str], window: tuple[float, float],
            drill: tuple[float, float] | None = None, offline_after: float = OFFLINE_AFTER_S,
            host: str = "") -> dict:
    """`senders` maps a sender's login to its record.read_deliveries()."""
    pairs: dict[tuple[str, str], dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for a in arrivals:
        pairs[(a["mid"], a["addressee"])][a["carrier"]].append(a)
    sent: dict[tuple[str, str], tuple[str, dict]] = {}
    for login, recs in senders.items():
        for r in recs:
            sent[(r["mid"], f"{host}/{r['to']}" if host else r["to"])] = (login, r)
    first = {k: min(parse_t(a["t"]) for c in v.values() for a in c) for k, v in pairs.items()}
    inside = {k for k, t in first.items() if window[0] <= t < window[1]}
    inside |= {k for k, (_, r) in sent.items() if k not in pairs and r.get("queued") and r["state"] != "done"
               and window[0] <= parse_t(r["queued"]) < window[1]}

    per = {c: {"delivered": 0, "missed": 0, "duplicates": 0, "mismatch": 0} for c in CARRIERS}
    missed: list[dict] = []
    stranded: list[dict] = []
    late = {k: {"relay": 0, "interweave": 0} for k in ("direct", "role", "broadcast", "unknown")}
    for key in sorted(inside):
        mid, addressee = key
        copies = pairs.get(key, {})
        if not copies:
            stranded.append({"mid": mid, "addressee": addressee, "sender": sent[key][0], "state": sent[key][1]["state"]})
        kind = kinds.get(mid, "unknown")
        created = made_at(mid)
        for c in CARRIERS:
            got = copies.get(c, [])
            if got:
                per[c]["delivered"] += 1
                per[c]["duplicates"] += len(got) - 1
                per[c]["mismatch"] += sum(1 for g in got if g["verdict"] == "mismatch")
                if created is not None and min(parse_t(g["t"]) for g in got) - created > offline_after:
                    late[kind][c] += 1
            else:
                per[c]["missed"] += 1
                missed.append({"mid": mid, "addressee": addressee, "carrier": c, "cause": _cause(c, key, sent, copies)})
    encs = defaultdict(set)
    for login, recs in senders.items():
        for r in recs:
            if r.get("queued") and window[0] <= parse_t(r["queued"]) < window[1]:
                encs[r["enc"]].add(r["mid"])
    out = {"window": window, "pairs": len(inside), "carriers": per, "missed": missed, "stranded": stranded,
           "late": late, "offline_after_s": offline_after,
           "messages": {e: len(encs[e]) for e in ("plain", "compressed", "chunked")}}
    if drill:
        d = []
        for key in sorted(inside):
            created = made_at(key[0])
            if created is not None and drill[0] <= created < drill[1]:
                copies = pairs.get(key, {})
                d.append({"mid": key[0], "addressee": key[1], "relay": bool(copies.get("relay")),
                          "interweave": bool(copies.get("interweave")), "kind": kinds.get(key[0], "unknown")})
        out["drill"] = {"window": drill, "pairs": d, "nothing_lost": all(x["relay"] or x["interweave"] for x in d)}
    out["role_pairs"] = sum(1 for k in inside if kinds.get(k[0]) == "role")
    return out


def _cause(carrier: str, key: tuple, sent: dict, copies: dict) -> str:
    if carrier == "interweave":
        rec = sent.get(key)
        if rec is None:
            return "the sender recorded no InterWeave delivery (not carried: no roster row, carrier off or sender had none)"
        login, r = rec
        if r["state"] == "blocked":
            return f"sent by {login}, refused by the daemon and still outstanding ({r.get('code')})"
        if r["state"] == "abandoned":
            return f"sent by {login}, abandoned by its operator ({r.get('by')})"
        if r["state"] in ("queued", "posted"):
            return f"sent by {login}, {r['state']} and without a receipt yet"
        return f"sent by {login} and receipted, but the addressee's arrival log has no InterWeave line"
    return "the addressee's inbox recorded no relay copy"


def render_markdown(rep: dict, title: str = "InterWeave carrier parity report") -> str:
    w = rep["window"]
    iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))  # noqa: E731
    L = [f"# {title}", "", f"Window: {iso(w[0])} to {iso(w[1])} (a pair belongs to it by its first copy).",
         f"Pairs (MESSAGE-ID, addressee): {rep['pairs']}; of them to a TO-ROLE recipient: {rep['role_pairs']}.", "",
         "| carrier | delivered | missed | duplicate copies | FROM mismatches |", "|---|---|---|---|---|"]
    for c in CARRIERS:
        p = rep["carriers"][c]
        L.append(f"| {c} | {p['delivered']} | {p['missed']} | {p['duplicates']} | {p['mismatch']} |")
    L += ["", "## Pairs a carrier missed, with the cause", ""]
    L += [f"- {m['mid']} to {m['addressee']}, {m['carrier']}: {m['cause']}" for m in rep["missed"]] or ["- none"]
    L += ["", "## Pairs the sender recorded sending, no copy arrived and no receipt came", ""]
    L += [f"- {m['mid']} to {m['addressee']} (sender {m['sender']}, {m['state']})" for m in rep["stranded"]] or ["- none"]
    L += ["", f"## Delivered to an addressee that was away (first copy over {int(rep['offline_after_s'])} s after the message was made)", "",
          "| kind | relay | interweave |", "|---|---|---|"]
    for k, v in rep["late"].items():
        L.append(f"| {k} | {v['relay']} | {v['interweave']} |")
    m = rep["messages"]
    L += ["", f"## Framing: {m['compressed']} message(s) compressed, {m['chunked']} chunked, {m['plain']} sent plain", ""]
    if "drill" in rep:
        d = rep["drill"]
        L += [f"## Rollback drill ({iso(d['window'][0])} to {iso(d['window'][1])}): "
              f"{'nothing lost' if d['nothing_lost'] else 'MESSAGES LOST'}", ""]
        L += [f"- {x['mid']} to {x['addressee']} ({x['kind']}): relay {'yes' if x['relay'] else 'NO'}, "
              f"interweave {'yes' if x['interweave'] else 'no'}" for x in d["pairs"]] or ["- no pair was made inside the drill"]
    return "\n".join(L) + "\n"
