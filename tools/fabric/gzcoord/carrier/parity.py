"""tools/fabric/gzcoord/carrier/parity.py — the parity report of ADR-064 rule
11, computed from what the carriers and inboxes recorded; it measures, it
never decides. The owner's word on a switch is given on this report
(docs/live-checks/) and is not this code's.

INPUTS (all files an account already keeps, collected by whoever runs the
report; nothing is read from a live process; `fabric-ctl <login|all>
interweave-evidence` collects them from the accounts, and load_collected reads
what it filed or printed):
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
  shown, acks  (only for the relay-outage drill) every account's shown ledger lines {mid, via, t,
             pending?, flagged?} and the relay acknowledgements it made {mid, addressee, t, ok}
  relay drill  [start, end): the interval the relay refused every fetch
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

The relay-outage drill (ADR-064 rule 11) is a section of its own, computed from the shown ledgers and
the acknowledgement logs, for each pair made inside the drill: whether the relay's copy arrived before
the drill ended (then the carrier was not the only holder and the pair proves nothing), whether the
addressee's session was shown it exactly once, whether it was shown again (a later ledger line whose
`via` is interweave: after a restart; relay: on the relay's return), and whether the relay copy was
acknowledged (an acknowledgement the relay answered, in the acknowledgement log). A property the files
cannot show (no relay copy yet, a ledger line interrupted before its final line) is `unknown`, never yes.
"""
from __future__ import annotations

import calendar
import json
import os
import re
import sqlite3
import time
from collections import defaultdict

CARRIERS = ("relay", "interweave")
UUID7 = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}")
OFFLINE_AFTER_S = 60.0
# A pair belongs to a window by its FIRST copy, so a copy up to this long outside the window still decides
# whether a pair is inside it and whether the other carrier's copy is there: a collection holds the arrivals
# this far beyond each edge (control/carrier_evidence.py), and is refused when it does not say it did.
MARGIN_S = 3600


def parse_t(t: str) -> float:
    return calendar.timegm(time.strptime(t, "%Y-%m-%dT%H:%M:%SZ"))


def made_at(mid: str) -> float | None:
    """When a uuid7 MESSAGE-ID was made, from its 48-bit millisecond prefix."""
    if not UUID7.fullmatch(mid):
        return None
    return int(mid.replace("-", "")[:12], 16) / 1000.0


def kind_of(metadata_json: str | None) -> str | None:
    """direct, role or broadcast, from the header fields a journal row keeps; None for a row whose
    header cannot be read (the report then counts the message's kind as unknown, never as direct)."""
    try:
        m = json.loads(metadata_json or "{}")
    except ValueError:
        return None
    if not isinstance(m, dict):
        return None
    return "broadcast" if m.get("BROADCAST") == "true" else "role" if "TO-ROLE" in m else "direct"


def kinds_from_journal(db_path: str) -> dict[str, str]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT message_id, metadata_json FROM episodes WHERE direction='inbound'")
        return {mid: k for mid, meta in rows if (k := kind_of(meta))}
    finally:
        con.close()


class CollectedError(Exception):
    """A collection the report must not be computed from; the message says which account and why."""


ARRIVAL_KEYS = ("mid", "addressee", "carrier", "t", "verdict")
DELIVERY_KEYS = ("mid", "to", "enc", "queued", "state")
KINDS = ("direct", "role", "broadcast")
MANIFEST = "collection.json"


def _jsonl(path: str, who: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            return [json.loads(x) for x in fh if x.strip()]
    except (OSError, ValueError) as e:
        raise CollectedError(f"{who}: cannot read {os.path.basename(path)}: {e}") from e


def _account(who: str, meta: dict, arrivals: list, deliveries: list, kinds: dict, window: tuple[float, float]) -> None:
    """Refuse an account whose collection cannot stand for its whole window, or whose rows are not what the op sends."""
    if meta.get("complete") is not True:
        raise CollectedError(f"{who}: the collection is not complete ({meta.get('reason') or 'no reason given'}); a report from half a log reads as carrier misses")
    try:
        since, until = parse_t(meta["since"]), parse_t(meta["until"])
    except (KeyError, ValueError, TypeError) as e:
        raise CollectedError(f"{who}: the collection does not say its window ({e})") from e
    if not (since <= window[0] and window[1] <= until):
        raise CollectedError(f"{who}: collected for {meta['since']} to {meta['until']}, which does not cover the report's window")
    if not (isinstance(meta.get("margin_s"), (int, float)) and meta["margin_s"] >= MARGIN_S):
        raise CollectedError(f"{who}: the arrivals beyond the window's edges were not collected (a copy just outside it would read as a carrier miss)")
    if not isinstance(kinds, dict) or any(k not in KINDS for k in kinds.values()) or any(not isinstance(m, str) for m in kinds):
        raise CollectedError(f"{who}: kinds is not {{message-id: direct|role|broadcast}}")
    for rows, keys, name in ((arrivals, ARRIVAL_KEYS, "arrival"), (deliveries, DELIVERY_KEYS, "delivery")):
        for r in rows:
            if not (isinstance(r, dict) and all(isinstance(r.get(k), str) for k in keys)):
                raise CollectedError(f"{who}: a {name} row is not {{{', '.join(keys)}}}")
            if set(r) - set(keys) - {"code", "by"}:
                raise CollectedError(f"{who}: a {name} row carries a key the op does not send ({sorted(set(r) - set(keys))[0]})")
            if name == "arrival" and not (r["carrier"] in CARRIERS):
                raise CollectedError(f"{who}: an arrival row names the carrier {r['carrier'][:20]!r}")
    want = meta.get("counts")
    if isinstance(want, dict) and (want.get("arrivals"), want.get("deliveries"), want.get("kinds")) != (len(arrivals), len(deliveries), len(kinds)):
        raise CollectedError(f"{who}: the files do not hold what the collection counted (cut short, or edited)")


def _read_parts(path: str, drill: bool = False) -> dict[str, tuple[dict, list, list, dict, list | None, list | None]]:
    """login -> (meta, arrivals, deliveries, kinds, shown, acks) as filed; shown and acks are None
    where the collection has none (one made before the relay-outage drill's sections) and always
    when `drill` is false: the rollback report must not depend on files it does not use."""
    parts: dict[str, tuple[dict, list, list, dict, list | None, list | None]] = {}
    if os.path.isdir(path):
        try:
            with open(os.path.join(path, MANIFEST), encoding="utf-8") as fh:
                listed = json.load(fh)["logins"]
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise CollectedError(f"{MANIFEST} cannot be read ({e}); it names the accounts the run asked, and a directory without it is not one") from e
        found = sorted(d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d)))
        if not (isinstance(listed, list) and all(isinstance(x, str) for x in listed)) or sorted(listed) != found:
            raise CollectedError(f"the directories {found} are not the accounts the run asked ({listed}): a stale or a missing account")
        for login in sorted(os.listdir(path)):
            d = os.path.join(path, login)
            if not os.path.isdir(d):
                continue
            try:
                with open(os.path.join(d, "meta.json"), encoding="utf-8") as fh:
                    meta = json.load(fh)
                with open(os.path.join(d, "kinds.json"), encoding="utf-8") as fh:
                    kinds = json.load(fh)
            except (OSError, ValueError) as e:
                raise CollectedError(f"{login}: cannot read its collection ({e}); a directory written by a run that stopped has no meta.json") from e
            if not isinstance(meta, dict) or meta.get("login") != login:
                raise CollectedError(f"{login}: meta.json is not this account's")
            extra = [_jsonl(os.path.join(d, n), login) if drill and os.path.exists(os.path.join(d, n)) else None for n in ("shown.jsonl", "acks.jsonl")]
            parts[login] = (meta, _jsonl(os.path.join(d, "arrivals.jsonl"), login), _jsonl(os.path.join(d, "deliveries.jsonl"), login), kinds, *extra)
    else:
        for n, line in enumerate(_jsonl(path, "collected"), 1):
            body = line.get("interweaveEvidence") if isinstance(line, dict) else None
            login = line.get("account") if isinstance(line, dict) else None
            if not (isinstance(login, str) and isinstance(body, dict) and all(isinstance(body.get(k), list) for k in ("arrivals", "deliveries"))):
                raise CollectedError(f"line {n}: not a row of `fabric-ctl --json interweave-evidence` with its rows (was it printed with --out?)")
            if login in parts:
                raise CollectedError(f"{login}: collected twice")
            parts[login] = (body, body["arrivals"], body["deliveries"], body.get("kinds") or {}, body.get("shown") if drill else None, body.get("acks") if drill else None)
    if not parts:
        raise CollectedError("nothing was collected")
    return parts


def load_collected(path: str, window: tuple[float, float]) -> tuple[list[dict], dict[str, list[dict]], dict[str, str], dict[str, str]]:
    """(arrivals, senders, kinds, journals) from `path`: a directory of <login>/{arrivals.jsonl, deliveries.jsonl,
    kinds.json, meta.json} as `fabric-ctl --out` files them, or a file of `fabric-ctl --json` lines. `journals`
    says per account whether its kinds could be read, because a kind the report cannot know is `unknown`, not direct."""
    parts = _read_parts(path)
    arrivals: list[dict] = []
    senders: dict[str, list[dict]] = {}
    kinds_all: dict[str, str] = {}
    journals: dict[str, str] = {}
    for login, (meta, arr, dels, kinds, _shown, _acks) in parts.items():
        _account(login, meta, arr, dels, kinds, window)
        arrivals += arr
        senders[login] = dels
        for mid, k in kinds.items():
            if kinds_all.setdefault(mid, k) != k:
                raise CollectedError(f"{login}: the kind of {mid} differs from another account's")
        journals[login] = str(meta.get("journal") or "ok")
    return arrivals, senders, kinds_all, journals


SHOWN_ROW_KEYS = ("mid", "via", "t")
ACK_ROW_KEYS = ("mid", "addressee", "t")


def load_relay_outage(path: str, window: tuple[float, float]) -> dict[str, dict]:
    """login -> {arrivals, shown, acks} for the relay-outage drill, after load_collected's checks of the
    same collection. Refuses an account whose drill sections were not collected whole: an empty ledger from
    a daemon that never sent one would read as 'never shown', which is a verdict the files do not support."""
    out: dict[str, dict] = {}
    for login, (meta, arr, dels, kinds, shown, acks) in _read_parts(path, drill=True).items():
        _account(login, meta, arr, dels, kinds, window)
        ro = meta.get("relay_outage")
        if shown is None or acks is None or not isinstance(ro, dict):
            raise CollectedError(f"{login}: the collection has no shown ledger or acknowledgement log (made before the relay-outage drill's sections)")
        if ro.get("complete") is not True:
            raise CollectedError(f"{login}: the relay-outage sections are not complete ({ro.get('reason') or 'no reason given'})")
        if ro.get("skipped"):
            # A torn or unreadable line may be the very acknowledgement or showing in question: unknown, so no report.
            raise CollectedError(f"{login}: {ro['skipped']} line(s) of the account's shown ledger or acknowledgement log could not be read; the drill cannot be judged from the rest")
        want = meta.get("counts")
        if isinstance(want, dict) and (want.get("shown"), want.get("acks")) != (len(shown), len(acks)):
            raise CollectedError(f"{login}: the files do not hold what the collection counted of the shown ledger and acknowledgements (cut short, or edited)")
        for rows, keys, name in ((shown, SHOWN_ROW_KEYS, "shown"), (acks, ACK_ROW_KEYS, "acknowledgement")):
            for r in rows:
                if not (isinstance(r, dict) and all(isinstance(r.get(k), str) for k in keys)):
                    raise CollectedError(f"{login}: a {name} row is not {{{', '.join(keys)}}}")
        if any(not isinstance(r.get("ok"), bool) for r in acks):
            raise CollectedError(f"{login}: an acknowledgement row has no ok")
        out[login] = {"arrivals": arr, "shown": shown, "acks": acks}
    return out


def relay_outage(per_account: dict[str, dict], drill: tuple[float, float]) -> dict:
    """The relay-outage drill's section. A pair belongs to it when its MESSAGE-ID was made inside `drill`
    (as for the rollback drill) and an account's arrival log holds a copy of it."""
    pairs = []
    for login in sorted(per_account):
        acct = per_account[login]
        copies: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for a in acct["arrivals"]:
            copies[(a["mid"], a["addressee"])][a["carrier"]].append(parse_t(a["t"]))
        for (mid, addressee), by in sorted(copies.items()):
            created = made_at(mid)
            if created is None or not (drill[0] <= created < drill[1]):
                continue
            lines = [x for x in acct["shown"] if x["mid"] == mid]
            finals = sorted((x for x in lines if not x.get("pending")), key=lambda x: x["t"])
            plain = [x for x in finals if not x.get("flagged")]
            flagged = [x for x in finals if x.get("flagged")]
            acks = [x for x in acct["acks"] if x["mid"] == mid and x["addressee"] == addressee]
            relay_first = min(by["relay"]) if by.get("relay") else None
            carrier_first = min(by["interweave"]) if by.get("interweave") else None
            # Held by the carrier alone means its copy arrived inside the drill and the relay's did not: a pair both
            # carriers delivered after the relay returned was sent late and proves nothing about the outage.
            in_drill = carrier_first is not None and drill[0] <= carrier_first < drill[1]
            held_alone = in_drill and (relay_first is None or relay_first >= drill[1])
            if plain:
                shown = "once" if len(plain) == 1 else f"{len(plain)} times"
            else:
                shown = "unknown" if lines else "no"       # a pending line alone: the showing was interrupted, whether it reached the session is not known
            again = [("after a restart" if x.get("via") == "interweave" else "on the relay's return") for x in plain[1:]]
            if relay_first is None:
                acked = "unknown"       # the relay's copy has not arrived (in the collected window): nothing to acknowledge yet
            elif any(x["ok"] for x in acks):
                acked = "yes"
            elif any(not x["ok"] for x in acks) or any(parse_t(x["t"]) <= relay_first for x in acct["acks"]):
                # "no" is a fact: the relay refused (ok false), or the log was demonstrably kept when the copy arrived
                # (an earlier line, of any message). The log did not exist before e4424b06; an empty one proves nothing.
                acked = "no"
            else:
                acked = "unknown"
            pairs.append({"mid": mid, "addressee": addressee, "account": login, "carrier_only": held_alone,
                          "interweave": bool(by.get("interweave")), "in_drill": in_drill, "relay_back": relay_first is not None,
                          "shown": shown, "first_via": plain[0].get("via") if plain else None, "again": again,
                          "flagged_reshow": len(flagged), "acked": acked})
    exercised = [p for p in pairs if p["carrier_only"]]
    for p in pairs:
        p["ok"] = None
        if p not in exercised:
            continue
        failed = p["shown"] not in ("once", "unknown") or p["again"] or (p["first_via"] not in (None, "interweave")) or p["acked"] == "no"
        p["ok"] = False if failed else None if "unknown" in (p["shown"], p["acked"]) else True
    judged = [p["ok"] for p in exercised]
    # True: every property held for every pair held by the carrier alone; False: one failed; None: none failed, some cannot be told yet.
    return {"window": drill, "pairs": pairs, "exercised": len(exercised), "unknown": judged.count(None),
            "holds": None if not judged else False if False in judged else None if None in judged else True}


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
    if "accounts" in rep:
        a = rep["accounts"]
        said = {"unreadable": "could not be read", "absent": "is absent"}
        L += ["", f"## Collected from {len(a)} account(s)", "", ", ".join(sorted(a)) or "none",
              "", f"Arrivals were collected {MARGIN_S // 60} minutes beyond each edge of the window: a pair whose two copies are further apart than that "
              "across an edge may show a miss the full files would not."]
        for state, words in said.items():
            blind = sorted(login for login, j in a.items() if j == state)
            if blind:
                L += ["", f"The journal {words} on {', '.join(blind)}: the kind of a message only they received is unknown."]
        odd = sorted(login for login, j in a.items() if j not in ("ok", *said))
        if odd:
            L += ["", f"The journal state of {', '.join(odd)} is not one the report knows: their kinds are unknown."]
    m = rep["messages"]
    L += ["", f"## Framing: {m['compressed']} message(s) compressed, {m['chunked']} chunked, {m['plain']} sent plain", ""]
    if "drill" in rep:
        d = rep["drill"]
        L += [f"## Rollback drill ({iso(d['window'][0])} to {iso(d['window'][1])}): "
              f"{'nothing lost' if d['nothing_lost'] else 'MESSAGES LOST'}", ""]
        L += [f"- {x['mid']} to {x['addressee']} ({x['kind']}): relay {'yes' if x['relay'] else 'NO'}, "
              f"interweave {'yes' if x['interweave'] else 'no'}" for x in d["pairs"]] or ["- no pair was made inside the drill"]
    if "relay_outage" in rep:
        d = rep["relay_outage"]
        verdict = ("no message was held by the carrier alone" if not d["exercised"] else "the three properties hold" if d["holds"] is True
                   else "A PROPERTY FAILED" if d["holds"] is False else f"UNSETTLED, none failed and {d['unknown']} pair(s) cannot be told yet")
        L += ["", f"## Relay-outage drill ({iso(d['window'][0])} to {iso(d['window'][1])}): {verdict}", "",
              "Per pair made inside the drill: held by the carrier alone (the InterWeave copy arrived inside the drill and the relay's did not; otherwise the pair proves nothing), "
              "shown to the session once or not, shown again, the relay copy acknowledged.", ""]
        for x in d["pairs"]:
            exercised = x["carrier_only"]
            why = ("no InterWeave copy" if not x["interweave"] else "the InterWeave copy came after the drill ended, so the sender sent it late"
                   if not x["in_drill"] else "the relay delivered it during the outage")
            held = "carrier alone" if exercised else f"NOT exercised ({why}; it does not count)"
            L.append(f"- {x['mid']} to {x['addressee']} ({x['account']}): {held}; shown {x['shown']}"
                     f"{' by ' + x['first_via'] if x['first_via'] else ''}; shown again: {', '.join(x['again']) or 'no'}; "
                     f"relay copy {'back' if x['relay_back'] else 'not back'}, acknowledged: {x['acked']}"
                     f"{' -- FAILS' if x['ok'] is False else ' -- UNKNOWN' if exercised and x['ok'] is None else ''}")
        if not d["pairs"]:
            L.append("- no pair was made inside the drill")
    return "\n".join(L) + "\n"
