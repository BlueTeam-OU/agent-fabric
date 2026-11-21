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
  watch      (only for the relay-outage drill) every account's watch log lines {t, event: start|end, pid, reason?, code?}: when a watch
             started and how it ended (carrier/arrivals.WatchLog)
  mirror     every account's mirror-refusal log lines {mid, t, outcome, reason[, as]} (carrier/arrivals.MirrorLog): the sends the carrier did not
             accept, as the SENDER kept them; `as` says whether it was the transport of record ("primary") or a mirror, and a row without it is a mirror's. Joined to a pair with no InterWeave copy and no sender record by MESSAGE-ID across every
             account, it names the cause that was on the sender's stderr only; an account without the log (a daemon from before it)
             says "not collected", never "no refusal" (load_mirror)
  shown, acks  (only for the relay-outage drill) every account's shown ledger lines {mid, via, t,
             pending?, flagged?} and the relay acknowledgements it made {mid, addressee, t, ok}
  relay drill  [start, end): the interval the relay refused every fetch
  carrier drill  [start, end) and a login: the interval that account's InterWeave units were stopped (carrier-record); its shown ledger is read
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
role is never counted as a miss of either carrier. The sender's own copy of
its broadcast or TO-ROLE (the relay returns it, the carrier never sends to its
sender, ADR-064 rule 6, CARRIER-CONTRACT.md §4) is listed apart as `own_copies`, not
counted as an InterWeave miss, so delivered plus missed is less than the pairs
by that many; it is known from the sender's own recorded deliveries of that
MESSAGE-ID, and a pair the sender recorded nothing for stays a miss.

Its fourth property reads the SENDER's relay backfill log (gzcoord/backfill.py, collected as backfills): for each pair held
by the carrier alone, the column "relay record" says whether the relay's record got the message afterwards (posted or present,
with the delay; over-age; or none: no row in any account's log by the report's until). The log is the sender's and carries no
addressee, so rows are joined by MESSAGE-ID across every account. An account whose collection has no backfill log (a daemon from
before it), or whose log has a line that could not be read, cannot say "none": the column reads "not collected" and the property
"not judged", never passed and never a refusal, so a collection made before the log existed still computes.
A message the relay took when it was SENT has no backfill line (nothing to backfill); the sender's journal row, accepted by the
relay, stands for it as a derived row of outcome "relay-took-send" (control/carrier_evidence.py), read as held ahead of "none". The
derived rows are only as complete as the daemon that sent them: meta's backfill_log.send_rows must be true for "none" to be said,
or the column reads "not collected" (a collection made before the derived rows computes, and judges nothing it cannot).

The relay-outage drill (ADR-064 rule 11) is a section of its own, computed from the shown ledgers and
the acknowledgement logs, for each pair made inside the drill: whether the relay's copy arrived before
the drill ended (then the carrier was not the only holder and the pair proves nothing), whether the
addressee's session was shown it exactly once, whether it was shown again (a later ledger line whose
`via` is interweave: after a restart; relay: on the relay's return), and whether the relay copy was
acknowledged (an acknowledgement the relay answered, in the acknowledgement log). A property the files
cannot show (no relay copy yet, a ledger line interrupted before its final line) is `unknown`, never yes.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from collections import defaultdict

from . import arrivals

CARRIERS = ("relay", "interweave")
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
            if name == "arrival" and not (r["carrier"] in CARRIERS):
                raise CollectedError(f"{who}: an arrival row names the carrier {r['carrier'][:20]!r}")
    want = meta.get("counts")
    if isinstance(want, dict) and (want.get("arrivals"), want.get("deliveries"), want.get("kinds")) != (len(arrivals), len(deliveries), len(kinds)):
        raise CollectedError(f"{who}: the files do not hold what the collection counted (cut short, or edited)")


def _read_parts(path: str, drill: bool = False) -> dict[str, tuple[dict, list, list, dict, list | None, list | None, list | None, list | None, list | None]]:
    """login -> (meta, arrivals, deliveries, kinds, shown, acks, backfills, watch, mirror) as filed; shown, acks, backfills and watch are None
    where the collection has none (one made before the relay-outage drill's sections, before the backfill log's or before the
    watch log's) and always when `drill` is false: the rollback report must not depend on files it does not use. `mirror` is None
    only where the collection has none, whatever `drill` says: it explains a miss of the report itself."""
    parts: dict[str, tuple[dict, list, list, dict, list | None, list | None, list | None, list | None, list | None]] = {}
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
            extra = [_jsonl(os.path.join(d, n), login) if drill and os.path.exists(os.path.join(d, n)) else None for n in ("shown.jsonl", "acks.jsonl", "backfills.jsonl", "watch.jsonl")]
            mirror = _jsonl(os.path.join(d, "mirror.jsonl"), login) if os.path.exists(os.path.join(d, "mirror.jsonl")) else None
            parts[login] = (meta, _jsonl(os.path.join(d, "arrivals.jsonl"), login), _jsonl(os.path.join(d, "deliveries.jsonl"), login), kinds, *extra, mirror)
    else:
        for n, line in enumerate(_jsonl(path, "collected"), 1):
            body = line.get("interweaveEvidence") if isinstance(line, dict) else None
            login = line.get("account") if isinstance(line, dict) else None
            if not (isinstance(login, str) and isinstance(body, dict) and all(isinstance(body.get(k), list) for k in ("arrivals", "deliveries"))):
                raise CollectedError(f"line {n}: not a row of `fabric-ctl --json interweave-evidence` with its rows (was it printed with --out?)")
            if login in parts:
                raise CollectedError(f"{login}: collected twice")
            parts[login] = (body, body["arrivals"], body["deliveries"], body.get("kinds") or {}, body.get("shown") if drill else None, body.get("acks") if drill else None,
                           body.get("backfills") if drill else None, body.get("watch") if drill else None, body.get("mirror"))
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
ACK_ROW_KEYS = ("mid", "addressee", "t")
BACKFILL_ROW_KEYS = ("mid", "outcome", "at", "delay_s", "channel")
BACKFILL_OUTCOMES = ("posted", "present", "over-age")
RELAY_TOOK_SEND = "relay-took-send"      # derived from the sender's journal, not a log line; it has no delay_s


def _backfills(login: str, meta: dict, rows: list | None) -> list[dict] | None:
    """The account's backfill rows when the collection holds its log whole; None when it does not (no file, or the section
    failed or had a line that could not be read: "none" cannot be said from it). A row that is not what the op sends is a refusal,
    as for the other sections: the account did collect it."""
    log = meta.get("backfill_log")
    if rows is None or not isinstance(log, dict) or log.get("complete") is not True or log.get("skipped"):
        return None
    want = meta.get("counts")
    if isinstance(want, dict) and "backfills" in want and want["backfills"] != len(rows):
        raise CollectedError(f"{login}: the files do not hold what the collection counted of the backfill log (cut short, or edited)")
    for r in rows:
        d = r.get("delay_s") if isinstance(r, dict) else None
        derived = isinstance(r, dict) and r.get("outcome") == RELAY_TOOK_SEND
        if not (isinstance(r, dict) and set(r) <= set(BACKFILL_ROW_KEYS) and all(isinstance(r.get(k), str) for k in ("mid", "outcome", "at"))
                and (derived and "delay_s" not in r or r["outcome"] in BACKFILL_OUTCOMES and isinstance(d, (int, float)) and not isinstance(d, bool))
                and (r.get("channel") is None or isinstance(r["channel"], str))):
            raise CollectedError(f"{login}: a backfill row is not {{{', '.join(BACKFILL_ROW_KEYS)}}}")
        try:
            parse_t(r["at"])
        except ValueError as e:
            raise CollectedError(f"{login}: a backfill row has no time ({r['at'][:30]!r})") from e
    return rows


WATCH_ROW_KEYS = ("t", "event", "pid", "reason", "code")
WATCH_REASONS = arrivals.WatchLog.END_REASONS      # one definition: the writer's, which the op and this reader both follow


def _watch(login: str, meta: dict, rows: list | None) -> list[dict] | None:
    """The account's watch log when the collection holds it whole; None when it does not (no file: a collection from before it,
    or a section that failed, or had a line that could not be read: "no watch started" cannot be said from it). A row that is not
    what the op sends is a refusal, as for the other sections."""
    log = meta.get("watch_log")
    if rows is None or not isinstance(log, dict) or log.get("complete") is not True or log.get("skipped"):
        return None
    want = meta.get("counts")
    if isinstance(want, dict) and "watch" in want and want["watch"] != len(rows):
        raise CollectedError(f"{login}: the files do not hold what the collection counted of the watch log (cut short, or edited)")
    for r in rows:
        ok = (isinstance(r, dict) and set(r) <= set(WATCH_ROW_KEYS) and isinstance(r.get("t"), str)
              and isinstance(r.get("pid"), int) and not isinstance(r.get("pid"), bool)
              and (r.get("event") == "start" and set(r) == {"t", "event", "pid"}
                   or r.get("event") == "end" and r.get("reason") in WATCH_REASONS and isinstance(r.get("code"), int) and not isinstance(r.get("code"), bool)))
        if not ok:
            raise CollectedError(f"{login}: a watch log row is not {{t, event, pid}} or {{t, event, pid, reason, code}}")
        try:
            parse_t(r["t"])
        except ValueError as e:
            raise CollectedError(f"{login}: a watch log row has no time ({r['t'][:30]!r})") from e
    return rows


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
            raise CollectedError(f"{login}: a mirror log row is not {{{', '.join(MIRROR_ROW_KEYS)}}}")
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
        rows = _mirror(login, part[0], part[8])
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


def load_relay_outage(path: str, window: tuple[float, float]) -> dict[str, dict]:
    """login -> {arrivals, deliveries, shown, acks, backfills, watch, watch_why, send_rows} (backfills None when the
    sender's log was not collected whole; send_rows whether its derived rows were) for the relay-outage drill, after load_collected's checks of the
    same collection. Refuses an account whose drill sections were not collected whole: an empty ledger from
    a daemon that never sent one would read as 'never shown', which is a verdict the files do not support."""
    out: dict[str, dict] = {}
    for login, (meta, arr, dels, kinds, shown, acks, backfills, watch, _mirror_rows) in _read_parts(path, drill=True).items():
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
        out[login] = {"arrivals": arr, "deliveries": dels, "shown": shown, "acks": acks, "backfills": _backfills(login, meta, backfills),
                     "watch": _watch(login, meta, watch), "watch_why": _watch_why(meta, watch),
                     "send_rows": (meta.get("backfill_log") or {}).get("send_rows") is True}
    return out


def _watch_why(meta: dict, rows: list | None) -> str | None:
    """Why `watch` is None, in words a report prints; None when it is not."""
    log = meta.get("watch_log")
    if not isinstance(log, dict):
        return "no watch log in the collection, from a daemon that predates it"
    if log.get("complete") is not True:
        return f"the watch log's section failed: {log.get('reason') or 'no reason given'}"
    if rows is None:
        return "the watch log's file is not in the collection"
    if log.get("skipped"):
        return f"{log['skipped']} line(s) of the watch log could not be read"
    return None


NOT_COLLECTED = "not collected"


def relay_record(mid: str, per_account: dict[str, dict], until: float | None) -> dict:
    """What the relay's record got of `mid` afterwards, from every account's backfill log (the log is the sender's, which a pair's
    addressee does not name): {state: posted|present|relay-took-send|over-age|none|not collected, delay_s?, channel?}. A row from `until` on is
    no answer by then. `none` is said only when the SENDER's log (the account whose delivery record names the message) is in
    the collection, was collected whole and its derived relay-took-send rows were: a collection that lacks the sender, or its log, cannot say the log holds no row."""
    rows = [r for a in per_account.values() for r in (a.get("backfills") or []) if r["mid"] == mid
            and (until is None or parse_t(r["at"]) < until)]
    landed = sorted((r for r in rows if r["outcome"] in ("posted", "present")), key=lambda r: r["at"])
    if landed:
        r = landed[0]
        return {"state": r["outcome"], "delay_s": r["delay_s"], "channel": r.get("channel")}
    # The relay had it from the send itself: held, whatever the log says (it holds no line for a send the relay took).
    if any(r["outcome"] == RELAY_TOOK_SEND for r in rows):
        return {"state": RELAY_TOOK_SEND, "channel": None}
    if rows:
        return {"state": "over-age", "channel": rows[0].get("channel"), "delay_s": rows[0].get("delay_s")}
    senders = [a for a in per_account.values() if any(d["mid"] == mid for d in a["deliveries"])]
    if not senders:
        return {"state": NOT_COLLECTED, "why": "the sender's account is not in the collection"}
    if any(a.get("backfills") is None for a in senders):
        return {"state": NOT_COLLECTED, "why": "the sender's backfill log was not collected"}
    if not all(a.get("send_rows") for a in senders):
        return {"state": NOT_COLLECTED, "why": "the sender's collection has no rows of the messages the relay took at send (a daemon from before them)"}
    return {"state": "none"}


def load_shown(path: str, login: str) -> list[dict]:
    """`login`'s shown ledger lines for the carrier-outage drill, after load_collected's checks of the same collection. Refuses a
    collection without that account, or whose shown ledger was not collected whole: an empty ledger from a daemon that never
    sent one would read as 'never shown', which is a verdict the files do not support."""
    parts = _read_parts(path, drill=True)
    if login not in parts:
        raise CollectedError(f"the collection has no account {login}: the carrier-outage drill reads that account's own shown ledger")
    meta, shown = parts[login][0], parts[login][4]
    ro = meta.get("relay_outage")
    if shown is None or not isinstance(ro, dict):
        raise CollectedError(f"{login}: the collection has no shown ledger (made before the relay-outage drill's sections)")
    if ro.get("complete") is not True:
        raise CollectedError(f"{login}: the shown ledger was not collected whole ({ro.get('reason') or 'no reason given'})")
    if ro.get("skipped"):
        raise CollectedError(f"{login}: {ro['skipped']} line(s) of the account's shown ledger or acknowledgement log could not be read; the drill cannot be judged from the rest")
    want = meta.get("counts")
    if isinstance(want, dict) and want.get("shown") != len(shown):
        raise CollectedError(f"{login}: the files do not hold what the collection counted of the shown ledger (cut short, or edited)")
    if any(not (isinstance(r, dict) and all(isinstance(r.get(k), str) for k in SHOWN_ROW_KEYS)) for r in shown):
        raise CollectedError(f"{login}: a shown row is not {{{', '.join(SHOWN_ROW_KEYS)}}}")
    return shown


def _login_of(address: str) -> str:
    return address.rsplit("/", 1)[-1]


def carrier_outage(arrivals: list[dict], senders: dict[str, list[dict]], shown: list[dict], drill: tuple[float, float], login: str) -> dict:
    """The carrier-outage drill (ADR-064 rule 11, gate 2): one account's carrier stopped for [drill) in carrier-record. A pair belongs to it when
    its MESSAGE-ID was made inside the window and it is addressed to `login` (a copy arrived for it, or a sender recorded a delivery to it).
    Per pair: whether a sender's outbox recorded the delivery (`held`), whether a copy of any carrier reached the account before the
    window ended (then the carrier did not hold it alone and the pair proves nothing), how many copies of each carrier arrived and the
    first of them, and how often the session was shown it. A property the files cannot show is `unknown`, never yes."""
    copies: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for a in arrivals:
        if _login_of(a["addressee"]) == login:
            copies[a["mid"]][a["carrier"]].append(parse_t(a["t"]))
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
        by = copies.get(m, {})
        times = sorted(t for ts in by.values() for t in ts)
        lines = [x for x in shown if x["mid"] == m]
        finals = [x for x in lines if not x.get("pending")]
        held = bool(queued.get(m))
        early = bool(times) and times[0] < drill[1]
        rows = queued.get(m, [])
        pairs.append({"mid": m, "held": held, "sender": rows[0][0] if rows else None, "outbox_state": rows[0][1]["state"] if rows else None,
                      "exercised": held and not early, "early": early, "first": times[0] if times else None,
                      "interweave": len(by.get("interweave", [])), "relay": len(by.get("relay", [])),
                      "shown": len(finals) if finals else "unknown" if lines else "no"})
    for p in pairs:
        p["ok"] = None
        if not p["exercised"]:
            continue
        # In carrier-record the sender also mirrors every message to the relay, which the watch reads after the carrier's wait: one relay copy
        # beside the carrier's is the mode working, so each carrier is counted alone. The outbox under test is the carrier's, so it must deliver.
        if p["interweave"] != 1 or p["relay"] > 1 or p["shown"] not in (1, "unknown"):
            p["ok"] = False
        else:
            p["ok"] = None if p["shown"] == "unknown" else True
    judged = [p["ok"] for p in pairs if p["exercised"]]
    return {"window": drill, "login": login, "pairs": pairs, "exercised": len(judged), "unknown": judged.count(None),
            "holds": None if not judged else False if False in judged else None if None in judged else True}


def watch_in_drill(rows: list[dict], drill: tuple[float, float]) -> dict:
    """The watch log's account of the drill: every start inside it, with how the watch before it ended (the reason of the latest
    earlier end line; "no end line" when the latest earlier line is another watch's start, which was killed from outside, left by an
    interrupt or an exception inside the process, or is still running; "no earlier line" when the collection, which reaches back only
    to the window's margin, holds nothing before), and every end inside it by the give-up (exit 5)."""
    ordered = sorted(rows, key=lambda r: parse_t(r["t"]))
    starts, gave_up = [], []
    for i, r in enumerate(ordered):
        at = parse_t(r["t"])
        if not drill[0] <= at < drill[1]:
            continue
        if r["event"] == "start":
            before = ordered[i - 1] if i else None
            after = ("no earlier line" if before is None else before["reason"] if before["event"] == "end" else "no end line")
            starts.append({"t": r["t"], "pid": r["pid"], "after": after})
        elif r["reason"] == "gave-up":
            gave_up.append({"t": r["t"], "pid": r["pid"]})
    return {"starts": starts, "gave_up": gave_up}


def relay_outage(per_account: dict[str, dict], drill: tuple[float, float], until: float | None = None) -> dict:
    """The relay-outage drill's section. A pair belongs to it when its MESSAGE-ID was made inside `drill`
    (as for the rollback drill) and an account's arrival log holds a copy of it. `until` is the report's end, by
    which a backfill must have been logged (no bound when None)."""
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
            # Held by the carrier alone means its copy arrived inside the drill and the relay's did not: a pair whose
            # InterWeave copy arrived outside the drill proves nothing about the outage.
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
    for p in pairs:
        p["relay_record"] = relay_record(p["mid"], per_account, until) if p["carrier_only"] else None
    records = [p["relay_record"]["state"] for p in exercised]
    # The fourth property: a failure is a fact whatever else is not collected; otherwise one that cannot be said is not judged.
    backfill = (None if not exercised else False if any(s in ("over-age", "none") for s in records)
                else None if NOT_COLLECTED in records else True)
    watches = {login: (watch_in_drill(a["watch"], drill) if a.get("watch") is not None else {"why": a.get("watch_why") or "not collected"})
               for login, a in sorted(per_account.items())}
    judged = [p["ok"] for p in exercised]
    # True: every property held for every pair held by the carrier alone; False: one failed; None: none failed, some cannot be told yet.
    return {"window": drill, "pairs": pairs, "exercised": len(exercised), "unknown": judged.count(None),
            "holds": None if not judged else False if False in judged else None if None in judged else True,
            "watches": watches, "backfill": backfill, "backfill_not_collected": sorted({p["relay_record"]["why"] for p in exercised if p["relay_record"]["state"] == NOT_COLLECTED})}


def compute(arrivals: list[dict], senders: dict[str, list[dict]], kinds: dict[str, str], window: tuple[float, float],
            drill: tuple[float, float] | None = None, offline_after: float = OFFLINE_AFTER_S,
            host: str = "", mirror: dict | None = None) -> dict:
    """`senders` maps a sender's login to its record.read_deliveries(). `mirror` is load_mirror's answer; without it a miss with no
    sender record keeps the words it had before the log, which cannot say which refusal it was."""
    pairs: dict[tuple[str, str], dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for a in arrivals:
        pairs[(a["mid"], a["addressee"])][a["carrier"]].append(a)
    sent: dict[tuple[str, str], tuple[str, dict]] = {}
    for login, recs in senders.items():
        for r in recs:
            sent[(r["mid"], f"{host}/{r['to']}" if host else r["to"])] = (login, r)
    first = {k: min(parse_t(a["t"]) for c in v.values() for a in c) for k, v in pairs.items()}
    # The carrier sends a broadcast or a TO-ROLE to every roster member but its own sender (engine.Carrier.recipients,
    # ADR-064 rule 6, CARRIER-CONTRACT.md §4), where the relay hands the sender its own copy back: that pair is no InterWeave miss.
    sender_logins = defaultdict(set)
    for (m_, _), (login, _) in sent.items():
        sender_logins[m_].add(login)
    first_iw: dict[str, float] = {}
    for (_, addressee), v in pairs.items():
        for a in v.get("interweave", []):
            first_iw[addressee] = min(first_iw.get(addressee, float("inf")), parse_t(a["t"]))
    inside = {k for k, t in first.items() if window[0] <= t < window[1]}
    inside |= {k for k, (_, r) in sent.items() if k not in pairs and r.get("queued") and r["state"] != "done"
               and window[0] <= parse_t(r["queued"]) < window[1]}

    per = {c: {"delivered": 0, "missed": 0, "duplicates": 0, "mismatch": 0} for c in CARRIERS}
    missed: list[dict] = []
    own_copies: list[dict] = []
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
            elif c == "interweave" and addressee.rpartition("/")[2] in sender_logins.get(mid, ()):
                own_copies.append({"mid": mid, "addressee": addressee})
            else:
                per[c]["missed"] += 1
                missed.append({"mid": mid, "addressee": addressee, "carrier": c,
                               "cause": _cause(c, key, sent, copies, first_iw.get(addressee), created, mirror)})
    encs = defaultdict(set)
    for login, recs in senders.items():
        for r in recs:
            if r.get("queued") and window[0] <= parse_t(r["queued"]) < window[1]:
                encs[r["enc"]].add(r["mid"])
    out = {"window": window, "pairs": len(inside), "carriers": per, "missed": missed, "own_copies": own_copies, "stranded": stranded,
           "late": late, "offline_after_s": offline_after,
           "messages": {e: len(encs[e]) for e in ("plain", "compressed", "chunked")}}
    if mirror is not None:
        out["mirror_uncollected"] = list(mirror["uncollected"])
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


def _cause(carrier: str, key: tuple, sent: dict, copies: dict, addressee_first: float | None = None,
           made: float | None = None, mirror: dict | None = None) -> str:
    if carrier == "interweave":
        rec = sent.get(key)
        if rec is None:
            # Which of the three the sender's refusal was is on its stderr only (adapter.Adapter.post_result); what the
            # collection can say is whether the addressee was receiving by InterWeave at all yet.
            said = "the sender recorded no InterWeave delivery (not carried: no roster row, carrier off or sender had none)"
            if mirror is not None:
                said = "the sender recorded no InterWeave delivery"
                refused = mirror["rows"].get(key[0])
                if refused:
                    # A primary's failure is the sender's own send exiting 3: the cause, so it leads; a mirror's refusal is an addition
                    # to a send the relay carried.
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
    return "the addressee's inbox recorded no relay copy"


def _record_words(r: dict) -> str:
    return (f"{r['state']} (delay {r['delay_s']} s)" if r["state"] in ("posted", "present")
            else "the relay took it at send" if r["state"] == RELAY_TOOK_SEND else r["state"])


def _carrier_pair_line(x: dict, iso) -> str:
    if not x["exercised"]:
        why = ("no sender in the collection recorded a delivery to the account" if not x["held"]
               else "a copy reached the account before the window ended, so the carrier did not hold it alone")
        return f"- {x['mid']}: NOT exercised ({why}; it does not count)"
    arrived = (f"delivered after the window's end ({iso(x['first'])})" if x["first"] is not None else "never delivered by the report's end")
    copies = f"{x['interweave'] + x['relay']} copy(ies) ({x['interweave']} interweave, {x['relay']} relay)"
    shown = {"no": "not shown", "unknown": "shown: unknown (a showing was interrupted)", 1: "shown once"}.get(x["shown"], f"shown {x['shown']} times")
    return (f"- {x['mid']}: held by {x['sender']}'s outbox ({x['outbox_state']}); {arrived}; {copies}; {shown}"
            f"{' -- FAILS' if x['ok'] is False else ' -- UNKNOWN' if x['ok'] is None else ''}")


def _row_words(r: dict) -> str:
    """The row the fourth property read for a pair: its outcome and delay, or why there is none."""
    if r["state"] in ("posted", "present", "over-age"):
        d = r.get("delay_s")
        return f"{r['state']}, delay {d} s" if isinstance(d, (int, float)) else r["state"]
    if r["state"] == RELAY_TOOK_SEND:
        return f"{RELAY_TOOK_SEND} (the relay took it at send; no delay)"
    if r["state"] == NOT_COLLECTED:
        return f"not collected ({r.get('why')})"
    return "none by the report's end"


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
    L += ["", f"Not counted as InterWeave misses: {len(rep['own_copies'])} pair(s) whose addressee is the message's own sender "
          "(a broadcast or TO-ROLE: the relay returns the sender its copy, the carrier never sends to its sender)."]
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
        if rep.get("mirror_uncollected"):
            L += ["", f"The mirror-refusal log was not collected whole from {', '.join(rep['mirror_uncollected'])}: a miss whose sender is one of them "
                  "has no refusal to name (a daemon from before the log, or a section that failed)."]
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
    if "carrier_outage" in rep:
        d = rep["carrier_outage"]
        verdict = ("no message in the collection was held by a sender's outbox" if not d["exercised"] else "every message held arrived once by the carrier and was shown once" if d["holds"] is True
                   else "A PROPERTY FAILED" if d["holds"] is False else f"UNSETTLED, none failed and {d['unknown']} pair(s) cannot be told yet")
        L += ["", f"## Carrier-outage drill of {d['login']} ({iso(d['window'][0])} to {iso(d['window'][1])}): {verdict}", "",
              "Per pair addressed to the account and made inside the drill: held by a sender's outbox (a delivery row the sender recorded), delivered after the "
              "window's end, how many copies each carrier delivered (the relay's mirror copy beside the carrier's is normal in carrier-record), "
              "and shown to the session once or not. A pair a copy reached before the window ended, or that no outbox recorded, proves nothing.", ""]
        L += [_carrier_pair_line(x, iso) for x in d["pairs"]] or ["- no pair was made inside the drill"]
    if "relay_outage" in rep:
        d = rep["relay_outage"]
        verdict = ("no message was held by the carrier alone" if not d["exercised"] else "the three properties hold" if d["holds"] is True
                   else "A PROPERTY FAILED" if d["holds"] is False else f"UNSETTLED, none failed and {d['unknown']} pair(s) cannot be told yet")
        L += ["", f"## Relay-outage drill ({iso(d['window'][0])} to {iso(d['window'][1])}): {verdict}", "",
              "Per pair made inside the drill: held by the carrier alone (the InterWeave copy arrived inside the drill and the relay's did not; otherwise the pair proves nothing), "
              "shown to the session once or not, shown again, the relay copy acknowledged.", ""]
        for x in d["pairs"]:
            exercised = x["carrier_only"]
            why = ("no InterWeave copy" if not x["interweave"] else "the InterWeave copy arrived outside the drill"
                   if not x["in_drill"] else "the relay delivered it during the outage")
            held = "carrier alone" if exercised else f"NOT exercised ({why}; it does not count)"
            L.append(f"- {x['mid']} to {x['addressee']} ({x['account']}): {held}; shown {x['shown']}"
                     f"{' by ' + x['first_via'] if x['first_via'] else ''}; shown again: {', '.join(x['again']) or 'no'}; "
                     f"{'relay record: ' + _record_words(x['relay_record']) + '; ' if exercised else ''}"
                     f"relay copy {'back' if x['relay_back'] else 'not back'}, acknowledged: {x['acked']}"
                     f"{' -- FAILS' if x['ok'] is False else ' -- UNKNOWN' if exercised and x['ok'] is None else ''}")
        if not d["pairs"]:
            L.append("- no pair was made inside the drill")
        L += ["", "Watches inside the drill, from each account's watch log (every start with how the watch before it ended; a give-up is the watch's exit 5, after its primary transport, the relay or the carrier where it leads, did not answer for the give-up bound, 15 minutes unless set otherwise):", ""]
        for login, w in d["watches"].items():
            if "why" in w:
                L.append(f"- {login}: not collected ({w['why']})")
                continue
            starts = ", ".join(f"{iso(parse_t(x['t']))} after {x['after']}" for x in w["starts"]) or "none"
            gave = ", ".join(iso(parse_t(x["t"])) for x in w["gave_up"])
            L.append(f"- {login}: restarts (starts inside the drill): {len(w['starts'])} ({starts}); gave up: {'yes, at ' + gave if gave else 'no'}")
        if d["exercised"]:
            fourth = {True: "holds: every such message is on the relay's record (by backfill, or taken by the relay at send)",
                      False: "FAILED: a message held by the carrier alone did not reach the relay's record by backfill (over-age, or no row by the report's end)",
                      None: "not judged: " + ("; ".join(d["backfill_not_collected"]) + " (a collection made before the log or before the rows of sends the relay took, with a line that could not be read, or of fewer accounts than sent)"
                                            if d["backfill_not_collected"] else "no pair to judge")}[d["backfill"]]
            L += ["", f"Fourth property, relay record by backfill: {fourth}."]
            L += [f"  - {x['mid']} to {x['addressee']}: backfill row {_row_words(x['relay_record'])}" for x in d["pairs"] if x["carrier_only"]]
    return "\n".join(L) + "\n"
