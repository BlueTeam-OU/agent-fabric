"""tools/fabric/gzcoord/carrier/parity.py — the one-carrier health report of ADR-064
rule 11, computed from what the carrier and the inboxes recorded; it measures, it
never decides. The owner's word on a switch is given on this report
(docs/live-checks/) and is not this code's.

INPUTS (all files an account already keeps, collected by whoever runs the
report; nothing is read from a live process; `fabric-ctl <login|all>
interweave-evidence` collects them from the accounts, and load_collected reads
what it filed or printed):
  arrivals   every account's gzcoord-arrivals.jsonl: one line per copy
             received {mid, addressee, carrier, t, verdict}. Only the InterWeave carrier carries messages now; a line of
             another carrier (the relay's, in a window from before it left GZCoord) is read: it shows that a pair existed and is no copy (copies_of)
  senders    every account's interweave/ directory, read by
             record.read_deliveries (who sent what to whom, how it was
             framed, how it ended)
  kinds      {mid: direct|role|broadcast}, from the journals' headers
             (kinds_from_journal): the arrival log does not say, by contract
  window     [start, end): a pair belongs to it when its first copy arrived inside
  mirror     every account's mirror-refusal log lines {mid, t, outcome, reason[, as]} (carrier/arrivals.MirrorLog): the sends the carrier did not
             accept, as the SENDER kept them; `as` says whether it was the transport of record ("primary") or a mirror, and a row without it is a mirror's. Joined to a pair with no InterWeave copy and no sender record by MESSAGE-ID across every
             account, it names the cause that was on the sender's stderr only; an account without the log (a daemon from before it)
             says "not collected", never "no refusal" (load_mirror)
  shown      (only for the carrier drill) the account's shown ledger lines {mid, via, t, pending?, flagged?}
  carrier drill  [start, end) and a login: the interval that account's InterWeave units were stopped (carrier-record); its shown ledger is read
  offline    seconds after a message was made (its uuid7 timestamp) beyond
             which a copy counts as delivered to an addressee that was away

The report covers every (MESSAGE-ID, addressee) pair in the window: how many the
carrier delivered, missed, and delivered more than once; each pair it missed, with
its cause; the copies that arrived late (offline), direct, role and broadcast
apart; and the messages compressed and chunked. A pair the sender recorded sending that no copy of
arrived for, and whose receipt has not come, is listed as stranded; one whose
receipt came is a message the addressee filtered out (a TO-ROLE it does not
hold, or a broadcast it is not addressed by), which is no pair at all. The
arrival logs hold only copies ADDRESSED to their owner, so a non-holder of a
role is never counted as a miss. The carrier never sends a broadcast or TO-ROLE to its sender
(ADR-064 rule 6, CARRIER-CONTRACT.md §4): that sender's own pair is listed apart as `own_copies`, not
counted as a miss, so delivered plus missed is less than the pairs
by that many; it is known from the sender's own recorded deliveries of that
MESSAGE-ID, and a pair the sender recorded nothing for stays a miss.

The carrier-outage drill (ADR-064 rule 11, gate 2) is a section of its own, computed from one account's shown ledger and the
senders' delivery records, for each pair made inside the drill: held by a sender's outbox, delivered once after the window's end,
and shown to the session once. A property the files cannot show (a ledger line interrupted before its final line) is `unknown`, never yes.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from collections import defaultdict

from . import arrivals

CARRIERS = ("interweave",)
CARRIER = CARRIERS[0]
# An arrival log from before the relay left GZCoord holds lines of its carrier. They are read, so a collection that reaches back
# over the cutover is not refused; the report counts no copy of it (copies_of).
RETIRED_CARRIERS = ("relay",)
UUID7 = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}")
OFFLINE_AFTER_S = 60.0
# A pair belongs to a window by its FIRST copy, so a copy up to this long outside the window still decides
# whether a pair is inside it and whether the other carrier's copy is there: a collection holds the arrivals
# this far beyond each edge (control/carrier_evidence.py), and is refused when it does not say it did.
MARGIN_S = 3600


def parse_t(t: str) -> float:
    import calendar     # lazy: a start of fabric-ctl imports this module and parses no stamp
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
            if name == "arrival" and r["carrier"] not in CARRIERS + RETIRED_CARRIERS:
                raise CollectedError(f"{who}: an arrival row names the carrier {r['carrier'][:20]!r}")
    want = meta.get("counts")
    if isinstance(want, dict) and (want.get("arrivals"), want.get("deliveries"), want.get("kinds")) != (len(arrivals), len(deliveries), len(kinds)):
        raise CollectedError(f"{who}: the files do not hold what the collection counted (cut short, or edited)")


def _read_parts(path: str, drill: bool = False) -> dict[str, tuple[dict, list, list, dict, list | None, list | None]]:
    """login -> (meta, arrivals, deliveries, kinds, shown, mirror) as filed; shown is None where the collection has none (one made
    before the shown ledger's section) and always when `drill` is false: the report must not depend on files it does not use. `mirror`
    is None only where the collection has none, whatever `drill` says: it explains a miss of the report itself.
    A collection filed by an earlier daemon also holds the relay's acknowledgement, backfill and watch sections (acks.jsonl, backfills.jsonl,
    watch.jsonl, or the same keys of a printed row): nothing reads them any more, so they are neither read nor refused."""
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
            shown = _jsonl(os.path.join(d, "shown.jsonl"), login) if drill and os.path.exists(os.path.join(d, "shown.jsonl")) else None
            mirror = _jsonl(os.path.join(d, "mirror.jsonl"), login) if os.path.exists(os.path.join(d, "mirror.jsonl")) else None
            parts[login] = (meta, _jsonl(os.path.join(d, "arrivals.jsonl"), login), _jsonl(os.path.join(d, "deliveries.jsonl"), login), kinds, shown, mirror)
    else:
        for n, line in enumerate(_jsonl(path, "collected"), 1):
            body = line.get("interweaveEvidence") if isinstance(line, dict) else None
            login = line.get("account") if isinstance(line, dict) else None
            if not (isinstance(login, str) and isinstance(body, dict) and all(isinstance(body.get(k), list) for k in ("arrivals", "deliveries"))):
                raise CollectedError(f"line {n}: not a row of `fabric-ctl --json interweave-evidence` with its rows (was it printed with --out?)")
            if login in parts:
                raise CollectedError(f"{login}: collected twice")
            parts[login] = (body, body["arrivals"], body["deliveries"], body.get("kinds") or {}, body.get("shown") if drill else None, body.get("mirror"))
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
    for login, (meta, arr, dels, kinds, *_drill) in parts.items():
        _account(login, meta, arr, dels, kinds, window)
        arrivals += arr
        senders[login] = dels
        for mid, k in kinds.items():
            if kinds_all.setdefault(mid, k) != k:
                raise CollectedError(f"{login}: the kind of {mid} differs from another account's")
        journals[login] = str(meta.get("journal") or "ok")
    return arrivals, senders, kinds_all, journals


SHOWN_ROW_KEYS = ("mid", "via", "t")


MIRROR_ROW_KEYS = ("mid", "t", "outcome", "reason")
# `as` is optional: a collection filed by an op from before the field holds none, and such a row is a mirror's.
MIRROR_ROLES = arrivals.MirrorLog.ROLES
MIRROR_OUTCOMES = arrivals.MirrorLog.OUTCOMES      # one definition: the writer's


def _mirror(login: str, meta: dict, rows: list | None) -> list[dict] | None:
    """The account's mirror-refusal rows when the collection holds its log whole; None when it does not (no file, a section that
    failed, a line that could not be read): "no refusal" cannot be said from it. A row the op would not send is a refusal."""
    log = meta.get("mirror_log")
    if rows is None or not isinstance(log, dict) or log.get("complete") is not True or log.get("skipped"):
        return None
    want = meta.get("counts")
    if isinstance(want, dict) and "mirror" in want and want["mirror"] != len(rows):
        raise CollectedError(f"{login}: the files do not hold what the collection counted of the mirror log (cut short, or edited)")
    for r in rows:
        if not (isinstance(r, dict) and set(r) in (set(MIRROR_ROW_KEYS), {*MIRROR_ROW_KEYS, "as"})
                and all(isinstance(v, str) for v in r.values()) and r["mid"] and r["outcome"] in MIRROR_OUTCOMES
                and r.get("as", "mirror") in MIRROR_ROLES):
            raise CollectedError(f"{login}: a mirror log row is not {{{', '.join(MIRROR_ROW_KEYS)}[, as: {'|'.join(MIRROR_ROLES)}]}}")
        try:
            parse_t(r["t"])
        except ValueError as e:
            raise CollectedError(f"{login}: a mirror log row has no time ({r['t'][:30]!r})") from e
    return rows


def load_mirror(path: str) -> dict:
    """{"rows": {mid: [{login, t, outcome, reason, as}]}, "uncollected": [login], "began": the start of the span every collected log covers}: every account's mirror refusals by MESSAGE-ID (the
    sender's log carries no addressee), and the accounts whose log the collection does not hold whole."""
    by_mid: dict[str, list[dict]] = defaultdict(list)
    uncollected: list[str] = []
    began = 0.0
    for login, part in _read_parts(path).items():
        rows = _mirror(login, part[0], part[5])
        if rows is None:
            uncollected.append(login)
            continue
        # Each account's log was asked for from its meta's `since` less the margin; the latest start is the span all of them cover.
        try:
            began = max(began, parse_t(part[0]["since"]) - MARGIN_S)
        except (KeyError, ValueError, TypeError):
            began = float("inf")      # a collection that does not say what it covers rules nothing out
        for r in rows:
            by_mid[r["mid"]].append({"login": login, "t": r["t"], "outcome": r["outcome"], "reason": r["reason"], "as": r.get("as", "mirror")})
    return {"rows": dict(by_mid), "uncollected": sorted(uncollected), "began": began}


def load_shown(path: str, login: str) -> list[dict]:
    """`login`'s shown ledger lines for the carrier-outage drill, after load_collected's checks of the same collection. Refuses a
    collection without that account, or whose shown ledger was not collected whole: an empty ledger from a daemon that never
    sent one would read as 'never shown', which is a verdict the files do not support."""
    parts = _read_parts(path, drill=True)
    if login not in parts:
        raise CollectedError(f"the collection has no account {login}: the carrier-outage drill reads that account's own shown ledger")
    meta, shown = parts[login][0], parts[login][4]
    # The meta key keeps the name it was filed under (collections already on disk hold it), though the section is the shown ledger alone now.
    ro = meta.get("relay_outage")
    if shown is None or not isinstance(ro, dict):
        raise CollectedError(f"{login}: the collection has no shown ledger (made before its section)")
    if ro.get("complete") is not True:
        raise CollectedError(f"{login}: the shown ledger was not collected whole ({ro.get('reason') or 'no reason given'})")
    if ro.get("skipped"):
        raise CollectedError(f"{login}: {ro['skipped']} line(s) of the account's shown ledger could not be read; the drill cannot be judged from the rest")
    want = meta.get("counts")
    if isinstance(want, dict) and want.get("shown") != len(shown):
        raise CollectedError(f"{login}: the files do not hold what the collection counted of the shown ledger (cut short, or edited)")
    if any(not (isinstance(r, dict) and all(isinstance(r.get(k), str) for k in SHOWN_ROW_KEYS)) for r in shown):
        raise CollectedError(f"{login}: a shown row is not {{{', '.join(SHOWN_ROW_KEYS)}}}")
    return shown


def copies_of(arrivals: list[dict]) -> list[dict]:
    """The InterWeave copies among `arrivals`: a line of a retired carrier (RETIRED_CARRIERS) is no copy the report counts."""
    return [a for a in arrivals if a["carrier"] == CARRIER]


def _login_of(address: str) -> str:
    return address.rsplit("/", 1)[-1]


def carrier_outage(arrivals: list[dict], senders: dict[str, list[dict]], shown: list[dict], drill: tuple[float, float], login: str) -> dict:
    """The carrier-outage drill (ADR-064 rule 11, gate 2): one account's carrier stopped for [drill) in carrier-record. A pair belongs to it when
    its MESSAGE-ID was made inside the window and it is addressed to `login` (a copy arrived for it, or a sender recorded a delivery to it).
    Per pair: whether a sender's outbox recorded the delivery (`held`), whether a copy of the carrier reached the account before the
    window ended (then the carrier did not hold it alone and the pair proves nothing; a relay line of a collection made before W15 is no
    copy, so the relay's early delivery is not read), how many copies arrived and the
    first of them, and how often the session was shown it. A property the files cannot show is `unknown`, never yes."""
    copies: dict[str, list[float]] = defaultdict(list)
    for a in copies_of(arrivals):
        if _login_of(a["addressee"]) == login:
            copies[a["mid"]].append(parse_t(a["t"]))
    queued: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for sender, recs in senders.items():
        for r in recs:
            if r["to"] == login:
                queued[r["mid"]].append((sender, r))
    pairs = []
    for m in sorted(set(copies) | set(queued)):
        created = made_at(m)
        if created is None or not drill[0] <= created < drill[1]:
            continue
        times = sorted(copies.get(m, []))
        lines = [x for x in shown if x["mid"] == m]
        finals = [x for x in lines if not x.get("pending")]
        held = bool(queued.get(m))
        early = bool(times) and times[0] < drill[1]
        rows = queued.get(m, [])
        pairs.append({"mid": m, "held": held, "sender": rows[0][0] if rows else None, "outbox_state": rows[0][1]["state"] if rows else None,
                      "exercised": held and not early, "early": early, "first": times[0] if times else None,
                      "interweave": len(times),
                      "shown": len(finals) if finals else "unknown" if lines else "no"})
    for p in pairs:
        p["ok"] = None
        if not p["exercised"]:
            continue
        if p["interweave"] != 1 or p["shown"] not in (1, "unknown"):
            p["ok"] = False
        else:
            p["ok"] = None if p["shown"] == "unknown" else True
    judged = [p["ok"] for p in pairs if p["exercised"]]
    return {"window": drill, "login": login, "pairs": pairs, "exercised": len(judged), "unknown": judged.count(None),
            "holds": None if not judged else False if False in judged else None if None in judged else True}


def compute(arrivals: list[dict], senders: dict[str, list[dict]], kinds: dict[str, str], window: tuple[float, float],
            offline_after: float = OFFLINE_AFTER_S, host: str = "", mirror: dict | None = None) -> dict:
    """`senders` maps a sender's login to its record.read_deliveries(). `mirror` is load_mirror's answer; without it a miss with no
    sender record keeps the words it had before the log, which cannot say which refusal it was."""
    # A line of a retired carrier still says the pair existed (a window from before the cutover): it is no copy of the carrier's,
    # so such a pair with no InterWeave copy is a miss with its cause, as the sender's records give it.
    pairs: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for a in arrivals:
        pairs[(a["mid"], a["addressee"])].append(a)
    sent: dict[tuple[str, str], tuple[str, dict]] = {}
    for login, recs in senders.items():
        for r in recs:
            sent[(r["mid"], f"{host}/{r['to']}" if host else r["to"])] = (login, r)
    first = {k: min(parse_t(a["t"]) for a in v) for k, v in pairs.items()}
    # The carrier sends a broadcast or a TO-ROLE to every roster member but its own sender (engine.Carrier.recipients,
    # ADR-064 rule 6, CARRIER-CONTRACT.md §4): that pair is no miss.
    sender_logins = defaultdict(set)
    for (m_, _), (login, _) in sent.items():
        sender_logins[m_].add(login)
    first_iw: dict[str, float] = {}
    for (_, addressee), v in pairs.items():
        for a in copies_of(v):
            first_iw[addressee] = min(first_iw.get(addressee, float("inf")), parse_t(a["t"]))
    inside = {k for k, t in first.items() if window[0] <= t < window[1]}
    inside |= {k for k, (_, r) in sent.items() if k not in pairs and r.get("queued") and r["state"] != "done"
               and window[0] <= parse_t(r["queued"]) < window[1]}

    per = {"delivered": 0, "missed": 0, "duplicates": 0, "mismatch": 0}
    missed: list[dict] = []
    own_copies: list[dict] = []
    stranded: list[dict] = []
    late = {k: {CARRIER: 0} for k in ("direct", "role", "broadcast", "unknown")}
    for key in sorted(inside):
        mid, addressee = key
        if not pairs.get(key):
            stranded.append({"mid": mid, "addressee": addressee, "sender": sent[key][0], "state": sent[key][1]["state"]})
        kind = kinds.get(mid, "unknown")
        created = made_at(mid)
        got = copies_of(pairs.get(key, []))
        if got:
            per["delivered"] += 1
            per["duplicates"] += len(got) - 1
            per["mismatch"] += sum(1 for g in got if g["verdict"] == "mismatch")
            if created is not None and min(parse_t(g["t"]) for g in got) - created > offline_after:
                late[kind][CARRIER] += 1
        elif addressee.rpartition("/")[2] in sender_logins.get(mid, ()):
            own_copies.append({"mid": mid, "addressee": addressee})
        else:
            per["missed"] += 1
            missed.append({"mid": mid, "addressee": addressee, "carrier": CARRIER,
                           "cause": _cause(key, sent, first_iw.get(addressee), created, mirror)})
    encs = defaultdict(set)
    for login, recs in senders.items():
        for r in recs:
            if r.get("queued") and window[0] <= parse_t(r["queued"]) < window[1]:
                encs[r["enc"]].add(r["mid"])
    out = {"window": window, "pairs": len(inside), "carriers": {CARRIER: per}, "missed": missed, "own_copies": own_copies, "stranded": stranded,
           "late": late, "offline_after_s": offline_after,
           "messages": {e: len(encs[e]) for e in ("plain", "compressed", "chunked")}}
    if mirror is not None:
        out["mirror_uncollected"] = list(mirror["uncollected"])
    out["role_pairs"] = sum(1 for k in inside if kinds.get(k[0]) == "role")
    return out


def _cause(key: tuple, sent: dict, addressee_first: float | None = None,
           made: float | None = None, mirror: dict | None = None) -> str:
    rec = sent.get(key)
    if rec is None:
        # Which of the three the sender's refusal was is on its stderr only (adapter.Adapter.post_result); what the
        # collection can say is whether the addressee was receiving by InterWeave at all yet.
        said = "the sender recorded no InterWeave delivery (not carried: no roster row, carrier off or sender had none)"
        if mirror is not None:
            said = "the sender recorded no InterWeave delivery"
            refused = mirror["rows"].get(key[0])
            if refused:
                # A primary's failure is the sender's own send exiting 3: the cause, so it leads; a line without that role
                # (the second copy of a send from before the relay left GZCoord) is an addition to it.
                first = [f"{x['login']}'s log: the carrier did not accept it at send ({x['outcome']}: {x['reason']}) at {x['t']}"
                         for x in refused if x["as"] == "primary"]
                rest = [f"{x['login']}'s mirror log: the carrier did not accept it ({x['outcome']}: {x['reason']}) at {x['t']}"
                        for x in refused if x["as"] != "primary"]
                said = "; ".join(first + [said] + rest)
            elif mirror["uncollected"]:
                said += f"; the mirror log was not collected from {len(mirror['uncollected'])} account(s), the sender's among them or not, so a refusal is not ruled out"
            elif made is not None and made < mirror.get("began", 0.0):
                said += "; the message was made before the span the mirror logs were collected over, so a refusal is not ruled out"
            else:
                said += "; no account's mirror log holds a refusal for it"
        if addressee_first is None:
            return said + "; the addressee has no InterWeave arrival in the collection"
        if made is not None and made < addressee_first:
            return said + f"; the addressee's first InterWeave arrival in the collection is {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(addressee_first))}, later"
        return said
    login, r = rec
    if r["state"] == "blocked":
        return f"sent by {login}, refused by the daemon and still outstanding ({r.get('code')})"
    if r["state"] == "abandoned":
        return f"sent by {login}, abandoned by its operator ({r.get('by')})"
    if r["state"] in ("queued", "posted"):
        return f"sent by {login}, {r['state']} and without a receipt yet"
    return f"sent by {login} and receipted, but the addressee's arrival log has no InterWeave line"


def _carrier_pair_line(x: dict, iso) -> str:
    if not x["exercised"]:
        why = ("no sender in the collection recorded a delivery to the account" if not x["held"]
               else "a copy reached the account before the window ended, so the carrier did not hold it alone")
        return f"- {x['mid']}: NOT exercised ({why}; it does not count)"
    arrived = (f"delivered after the window's end ({iso(x['first'])})" if x["first"] is not None else "never delivered by the report's end")
    copies = f"{x['interweave']} copy(ies)"
    shown = {"no": "not shown", "unknown": "shown: unknown (a showing was interrupted)", 1: "shown once"}.get(x["shown"], f"shown {x['shown']} times")
    return (f"- {x['mid']}: held by {x['sender']}'s outbox ({x['outbox_state']}); {arrived}; {copies}; {shown}"
            f"{' -- FAILS' if x['ok'] is False else ' -- UNKNOWN' if x['ok'] is None else ''}")


def render_markdown(rep: dict, title: str = "InterWeave carrier parity report") -> str:
    w = rep["window"]
    iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))  # noqa: E731
    L = [f"# {title}", "", f"Window: {iso(w[0])} to {iso(w[1])} (a pair belongs to it by its first copy).",
         f"Pairs (MESSAGE-ID, addressee): {rep['pairs']}; of them to a TO-ROLE recipient: {rep['role_pairs']}.", "",
         "| carrier | delivered | missed | duplicate copies | FROM mismatches |", "|---|---|---|---|---|"]
    for c in CARRIERS:
        p = rep["carriers"][c]
        L.append(f"| {c} | {p['delivered']} | {p['missed']} | {p['duplicates']} | {p['mismatch']} |")
    L += ["", "## Pairs the carrier missed, with the cause", ""]
    L += [f"- {m['mid']} to {m['addressee']}, {m['carrier']}: {m['cause']}" for m in rep["missed"]] or ["- none"]
    L += ["", f"Not counted as InterWeave misses: {len(rep['own_copies'])} pair(s) whose addressee is the message's own sender "
          "(a broadcast or TO-ROLE: the carrier never sends to its sender)."]
    L += ["", "## Pairs the sender recorded sending, no copy arrived and no receipt came", ""]
    L += [f"- {m['mid']} to {m['addressee']} (sender {m['sender']}, {m['state']})" for m in rep["stranded"]] or ["- none"]
    L += ["", f"## Delivered to an addressee that was away (first copy over {int(rep['offline_after_s'])} s after the message was made)", "",
          "| kind | interweave |", "|---|---|"]
    for k, v in rep["late"].items():
        L.append(f"| {k} | {v[CARRIER]} |")
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
        if rep.get("mirror_uncollected"):
            L += ["", f"The mirror-refusal log was not collected whole from {', '.join(rep['mirror_uncollected'])}: a miss whose sender is one of them "
                  "has no refusal to name (a daemon from before the log, or a section that failed)."]
        odd = sorted(login for login, j in a.items() if j not in ("ok", *said))
        if odd:
            L += ["", f"The journal state of {', '.join(odd)} is not one the report knows: their kinds are unknown."]
    m = rep["messages"]
    L += ["", f"## Framing: {m['compressed']} message(s) compressed, {m['chunked']} chunked, {m['plain']} sent plain", ""]
    if "carrier_outage" in rep:
        d = rep["carrier_outage"]
        verdict = ("no message in the collection was held by a sender's outbox" if not d["exercised"] else "every message held arrived once by the carrier and was shown once" if d["holds"] is True
                   else "A PROPERTY FAILED" if d["holds"] is False else f"UNSETTLED, none failed and {d['unknown']} pair(s) cannot be told yet")
        L += ["", f"## Carrier-outage drill of {d['login']} ({iso(d['window'][0])} to {iso(d['window'][1])}): {verdict}", "",
              "Per pair addressed to the account and made inside the drill: held by a sender's outbox (a delivery row the sender recorded), delivered after the "
              "window's end, how many copies the carrier delivered, "
              "and shown to the session once or not. A pair a copy reached before the window ended, or that no outbox recorded, proves nothing.", ""]
        L += [_carrier_pair_line(x, iso) for x in d["pairs"]] or ["- no pair was made inside the drill"]
    return "\n".join(L) + "\n"
