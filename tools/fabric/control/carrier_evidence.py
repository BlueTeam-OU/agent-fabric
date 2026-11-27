"""tools/fabric/control/carrier_evidence.py — `<carrier>-evidence`: the files ADR-064
rule 11's parity report is computed from, read by the account that keeps them and
sent to the operator that runs the report (agent-fabric ADR-029 §5 rules 3, 6).

CONTRACT
  request   op `<carrier>-evidence` (EVIDENCE_OP), signed (sign.ACTION_OPS): only an operator
            can ask, as for an action; the reply is posted on the control channel like
            every op's, so what it carries is metadata a channel reader could already
            infer from the traffic, and never a body. With
            args {section, since, until}:
              section  `arrivals` | `deliveries` | `shown` | `mirror`
              since, until  YYYY-MM-DDTHH:MM:SSZ, since < until
            No other key, no other value: an argument never names a path.
  reply     data["<carrier>-evidence"] = {status: "ok", section, since, until,
            rows: [...], next: <ISO time> | null, journal?, skipped?} or
            {status: "refused", reason}. A page is at most PAGE_BYTES of rows; a
            `next` says the window holds more and is the `since` of the next
            page: this request again, from there.
  arrivals  rows {mid, addressee, carrier, t, verdict} of the account's
            gzcoord-arrivals.jsonl with `t` in [since, until), oldest first;
            `kinds` {mid: direct|role|broadcast} for the page's MESSAGE-IDs, read
            from the account's journal (`journal`: ok | absent | unreadable).
  deliveries rows {mid, to, enc, queued, state, code?, by?} of
            record.read_deliveries with `queued` in [since, until), oldest first;
            `undated`, how many have no `queued` and so belong to no window.
  shown     rows {mid, via, t, pending?, flagged?} of the account's shown ledger
            (gzcoord-shown.jsonl) with `t` in [since, until): one line per step of a
            showing (carrier/ledger.py), `via` the carrier that brought the copy shown,
            `pending` and `flagged` present as true when set. The ledger's `h`, a hash
            of the text, does not leave. Read by the carrier-outage drill (ADR-064 rule 11) and nothing else.
            A collection filed by an earlier daemon also holds the relay's acknowledgement, backfill and watch sections;
            this op no longer serves them and the parity report ignores them.
  mirror    rows {mid, t, outcome, reason, as} of gzcoord-mirror.jsonl (carrier/arrivals.py MirrorLog): the SENDER's line for each send the
            carrier did not accept, `outcome` one of MIRROR_OUTCOMES (absent, not-carried, failed, no-answer), `as` "mirror"
            (a send from before the relay left GZCoord, whose second copy the carrier refused) or "primary" (the transport of record: carrier-record, carrier-only; a line written
            before the field has none and is sent as "mirror"), `reason` a short line of words (what the sender's stderr said, kept),
            with `t` in [since, until). Read by the parity
            report to name the cause of a pair with no InterWeave copy and no sender record, and nothing else. A failure of this
            section ends only this section; a line of another shape is skipped and counted.
  never     a body. Rows are built key by key from a closed list, each value a
            short string: a line of the log with a text, a path or a key in it
            that a later version adds does not leave. The journal is opened
            read-only and only message_id and the header fields that make a
            kind are read from it.

A page is cut on a second boundary, because `next` is a time: rows that share
the second the page ends on go to the next page whole, never half (a cursor
inside a second would send the rows before it twice or lose those after it). A
second with more rows than a page holds is refused by name, not cut.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from typing import Any

from control import opsutil as util
from gzcoord.carrier import CARRIER_NAME, arrivals, parity, record

EVIDENCE_OP = f"{CARRIER_NAME}-evidence"
SECTIONS = ("arrivals", "deliveries")
# Collected beside the two the report counts: the carrier-outage drill's evidence (parity.carrier_outage). Kept
# apart so an account whose daemon predates it still yields a collection the report is computed from.
DRILL_SECTIONS = ("shown",)
MIRROR_SECTION = "mirror"
MIRROR_OUTCOMES = arrivals.MirrorLog.OUTCOMES
ALL_SECTIONS = SECTIONS + DRILL_SECTIONS + (MIRROR_SECTION,)
SHOWN_KEYS = ("mid", "via", "t")
ARRIVAL_KEYS = ("mid", "addressee", "carrier", "t", "verdict")
DELIVERY_KEYS = ("mid", "to", "enc", "queued", "state", "code", "by")
# The relay's message limit is 128 KiB and a record is posted as a JSON string inside a JSON record, which
# escapes every quote: 64 KiB of rows is the most that always fits with the reply's own fields.
PAGE_BYTES = 64 * 1024
# How far beyond a window's edges a collection reaches (parity.MARGIN_S): a delivery queued before the window and
# delivered inside it is a pair of the window, and the first or the other copy of a pair may lie just outside it.
LOOKBACK_S = parity.MARGIN_S
# One page: a read of the two logs and at most a few hundred journal lookups (each bounded by the connection's 5 s).
EVIDENCE_BUDGET_S = 60
FIELD_MAX = 200
ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
IN_CHUNK = 500       # the journal's lookups per statement, below SQLite's variable limit


def _time(v: Any) -> float | None:
    if not (isinstance(v, str) and ISO_RE.fullmatch(v)):
        return None
    try:
        return parity.parse_t(v)
    except (ValueError, OverflowError):
        return None


def check_args(args: Any) -> str | None:
    """None for the arguments this op takes, else what is wrong."""
    if not isinstance(args, dict):
        return f"{EVIDENCE_OP} takes the arguments section, since and until"
    extra = sorted(set(args) - {"section", "since", "until"})
    if extra:
        return f"{EVIDENCE_OP} takes no argument {extra[0]!r}"
    if args.get("section") not in ALL_SECTIONS:
        return f"section is one of {', '.join(ALL_SECTIONS)}"
    start, end = _time(args.get("since")), _time(args.get("until"))
    if start is None or end is None:
        return "since and until are YYYY-MM-DDTHH:MM:SSZ"
    if not start < end:
        return "since is before until"
    return None


def _short(v: Any) -> str | None:
    return v[:FIELD_MAX] if isinstance(v, str) else None


def _row(src: dict, keys: tuple[str, ...], required: tuple[str, ...]) -> dict | None:
    """The closed list of keys, each a short string, or None when a required one is not."""
    out = {k: _short(src[k]) for k in keys if isinstance(src.get(k), str)}
    return out if all(out.get(k) for k in required) else None


def _read_arrivals(path: str) -> tuple[list[dict], int]:
    rows: list[dict] = []
    skipped = 0
    try:
        fh = open(path, encoding="utf-8")
    except FileNotFoundError:
        return rows, 0
    with fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                o = json.loads(line)
            except ValueError:
                skipped += 1      # a torn last line from a crash
                continue
            r = _row(o, ARRIVAL_KEYS, ARRIVAL_KEYS[:4]) if isinstance(o, dict) else None
            if r is None or _time(r["t"]) is None or "verdict" not in r:
                skipped += 1
                continue
            rows.append(r)
    return rows, skipped


def _read_lines(path: str, convert) -> tuple[list[dict], int]:
    """The rows `convert` accepts from a JSON-lines file of the account's, and how many lines it did not
    (a torn last line, a line of a shape this version does not know). A file that is not there holds nothing."""
    rows: list[dict] = []
    skipped = 0
    try:
        fh = open(path, encoding="utf-8")
    except FileNotFoundError:
        return rows, 0
    with fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                o = json.loads(line)
            except ValueError:
                skipped += 1
                continue
            r = convert(o) if isinstance(o, dict) else None
            if r is None:
                skipped += 1
            elif r is not DROP:
                rows.append(r)
    return rows, skipped


# A line the shown section leaves out on purpose, which is not an unreadable one (it is not counted as skipped).
DROP = object()


def _shown_row(o: dict):
    r = _row(o, SHOWN_KEYS, SHOWN_KEYS)
    if r is None or _time(r["t"]) is None:
        return None
    if not parity.UUID7.fullmatch(r["mid"]):
        return DROP       # a mid built from a hash of the text (a message with no MESSAGE-ID): a text hash does not leave
    return {**r, **{k: True for k in ("pending", "flagged") if o.get(k) is True}}


def _mirror_row(o: dict):
    """{mid, t, outcome, reason, as}: a line of another shape, or an outcome this version does not know, is skipped and counted, never
    filed as one the report would then print."""
    role = o.get("as", "mirror")      # no field: a line from before it, a mirror's
    if (role not in arrivals.MirrorLog.ROLES or o.get("outcome") not in MIRROR_OUTCOMES or not isinstance(o.get("mid"), str) or not o["mid"]
            or _time(o.get("t")) is None or not isinstance(o.get("reason"), str)):
        return None
    if not parity.UUID7.fullmatch(o["mid"]):
        # A sender accepts any id-shaped MESSAGE-ID (a v4, the old <instance>-NNNN): its line is the account's, not an unreadable
        # one, which would make the whole log read "not collected".
        return DROP
    # The carrier's own error can name a file of the sender's (an OSError on its outbox): a path never leaves the account.
    return {"mid": _short(o["mid"]), "t": o["t"], "outcome": o["outcome"], "reason": _short(re.sub(r"\S*/\S*", "<path>", o["reason"])), "as": role}


def _page(rows: list[dict], key: str, page_bytes: int | None = None) -> tuple[list[dict], str | None] | str:
    """The rows that fit page_bytes (PAGE_BYTES unless the account splits for the second carrier too), whole seconds only, and the time the next page starts at; or why
    the first second alone does not fit."""
    page_bytes = PAGE_BYTES if page_bytes is None else page_bytes   # read now: a test sets the module's constant
    size = 0
    for i, r in enumerate(rows):
        size += len(json.dumps(r, separators=(",", ":"))) + 1
        if size > page_bytes:
            cut = i
            while cut > 0 and rows[cut - 1][key] == rows[i][key]:
                cut -= 1
            if cut == 0:
                return f"more than {page_bytes} bytes of rows share the second {rows[i][key]}"
            return rows[:cut], rows[cut][key]
    return rows, None


def kinds_for(db_path: str, mids: list[str]) -> tuple[dict[str, str], str]:
    if not os.path.isfile(db_path):
        return {}, "absent"
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return {}, "unreadable"
    out: dict[str, str] = {}
    try:
        for i in range(0, len(mids), IN_CHUNK):
            chunk = mids[i:i + IN_CHUNK]
            marks = ",".join("?" * len(chunk))
            for mid, meta in con.execute(
                    f"SELECT message_id, metadata_json FROM episodes WHERE direction='inbound' AND message_id IN ({marks})", chunk):
                if (k := parity.kind_of(meta)):
                    out[mid] = k
    except sqlite3.Error:
        return {}, "unreadable"
    finally:
        con.close()
    return out, "ok"


def carrier_evidence(request: Any, *, state: str | None = None, db_path: str | None = None, page_bytes: int | None = None) -> dict:
    """One page of one section. Every refusal is one line of a reply."""
    args = request.get("args") if isinstance(request, dict) else None
    bad = check_args(args)
    if bad:
        return {"status": "refused", "reason": bad}
    state = util.state_dir() if state is None else state
    section, since, until = args["section"], args["since"], args["until"]
    start, end = _time(since), _time(until)
    if section == MIRROR_SECTION:
        every, skipped = _read_lines(os.path.join(state, "gzcoord-mirror.jsonl"), _mirror_row)
        inside = sorted((r for r in every if start <= _time(r["t"]) < end), key=lambda r: r["t"])
        key, extra = "t", {"skipped": skipped}
    elif section in DRILL_SECTIONS:
        every, skipped = _read_lines(os.path.join(state, "gzcoord-shown.jsonl"), _shown_row)
        # File order breaks a tie on the second: a ledger's pending line comes before its final line.
        inside = sorted((r for r in every if start <= _time(r["t"]) < end), key=lambda r: r["t"])
        key, extra = "t", {"skipped": skipped}
    elif section == "arrivals":
        every, skipped = _read_arrivals(os.path.join(state, "gzcoord-arrivals.jsonl"))
        inside = sorted((r for r in every if start <= _time(r["t"]) < end), key=lambda r: r["t"])
        key, extra = "t", {"skipped": skipped}
    else:
        got, undated = [], 0
        for d in record.read_deliveries(os.path.join(state, CARRIER_NAME)):
            r = _row(d, DELIVERY_KEYS, ("mid", "to", "enc", "state"))
            if r is None or _time(r.get("queued")) is None:
                undated += 1      # no `queued` (an old delivered.jsonl line) belongs to no window
                continue
            got.append(r)
        inside = sorted((r for r in got if start <= _time(r["queued"]) < end), key=lambda r: (r["queued"], r["mid"], r["to"]))
        key, extra = "queued", {"undated": undated}
    page = _page(inside, key, page_bytes)
    if isinstance(page, str):
        return {"status": "refused", "reason": page}
    rows, nxt = page
    out: dict[str, Any] = {"status": "ok", "section": section, "since": since, "until": until, "rows": rows, "next": nxt, **extra}
    if section == "arrivals":
        mids = sorted({r["mid"] for r in rows})
        out["kinds"], out["journal"] = kinds_for(db_path or _db_path(state), mids)
    return out


def _db_path(state: str) -> str:
    return os.path.join(state, "episodic.db")


def window_for(section: str, since: str, until: str) -> tuple[str, str]:
    """The span a collection asks one section for. Both begin LOOKBACK_S before the report's window: a
    delivery queued earlier is a pair of the window, an arrival earlier may be its first copy. Arrivals
    also end LOOKBACK_S after it: a pair's other copy may come after the window closed."""
    import time
    fmt = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))  # noqa: E731
    first = fmt(parity.parse_t(since) - LOOKBACK_S)
    return (first, fmt(parity.parse_t(until) + LOOKBACK_S)) if section != "deliveries" else (first, until)
