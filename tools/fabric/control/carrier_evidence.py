"""tools/fabric/control/carrier_evidence.py — `<carrier>-evidence`: the files ADR-064
rule 11's parity report is computed from, read by the account that keeps them and
sent to the operator that runs the report (agent-fabric ADR-029 §5 rules 3, 6).

CONTRACT
  request   op `<carrier>-evidence` (EVIDENCE_OP), signed (sign.ACTION_OPS): only an operator
            can ask, as for an action; the reply is posted on the control channel like
            every op's, so what it carries is metadata a channel reader could already
            infer from the traffic, and never a body. With
            args {section, since, until}:
              section  `arrivals` | `deliveries`
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

from control.ops import util
from gzcoord.carrier import CARRIER_NAME, parity, record

EVIDENCE_OP = f"{CARRIER_NAME}-evidence"
SECTIONS = ("arrivals", "deliveries")
ARRIVAL_KEYS = ("mid", "addressee", "carrier", "t", "verdict")
DELIVERY_KEYS = ("mid", "to", "enc", "queued", "state", "code", "by")
# The relay's message limit is 128 KiB and a record is posted as a JSON string inside a JSON record, which
# escapes every quote: 64 KiB of rows is the most that always fits with the reply's own fields.
PAGE_BYTES = 64 * 1024
# Where the deliveries of a window start: a message queued shortly before the window and delivered inside it
# is a pair of the window, and the parity report names the sender of a pair a carrier missed from this record.
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
    if args.get("section") not in SECTIONS:
        return f"section is one of {', '.join(SECTIONS)}"
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


def _page(rows: list[dict], key: str) -> tuple[list[dict], str | None] | str:
    """The rows that fit PAGE_BYTES, whole seconds only, and the time the next page starts at; or why
    the first second alone does not fit."""
    size = 0
    for i, r in enumerate(rows):
        size += len(json.dumps(r, separators=(",", ":"))) + 1
        if size > PAGE_BYTES:
            cut = i
            while cut > 0 and rows[cut - 1][key] == rows[i][key]:
                cut -= 1
            if cut == 0:
                return f"more than {PAGE_BYTES} bytes of rows share the second {rows[i][key]}"
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


def carrier_evidence(request: Any, *, state: str | None = None, db_path: str | None = None) -> dict:
    """One page of one section. Every refusal is one line of a reply."""
    args = request.get("args") if isinstance(request, dict) else None
    bad = check_args(args)
    if bad:
        return {"status": "refused", "reason": bad}
    state = util.state_dir() if state is None else state
    section, since, until = args["section"], args["since"], args["until"]
    start, end = _time(since), _time(until)
    if section == "arrivals":
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
    page = _page(inside, key)
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
    return (first, fmt(parity.parse_t(until) + LOOKBACK_S)) if section == "arrivals" else (first, until)
