#!/usr/bin/env python3
"""tools/fabric/episodic_import.py — the backfill of this agent's episodic
journal (agent-fabric ADR-041 rule 9): its GZCoord history from before the
journal existed, read from the carrier through the relay API, as itself.
Run as `episodic.py gzcoord-import`, which loads this module only for that
command: the journal's hot path (a send, an inbox page) never pays for it.

    episodic.py gzcoord-import [--if-needed] [PROJECT...]

Run AS THE ACCOUNT. With no PROJECT, every project with a GZCoord
integration; their relays and channels once each (tools/fabric/relay.py).
Each channel is listed from its first record with a consumer id made for
this run and never acknowledged, so no agent's cursor moves. Each record is
decided as the inbox decides what is addressed (inbox.mjs forMe), with the
history the agent has rather than the role it holds now:

  before this agent's birth     never stored, sent or received: the time in
  (or no time at all)           its UUIDv7 agent id; a reused login's earlier
                                messages are another agent's (ADR-039)
  FROM this agent's address     outbound, accepted, the carrier seq kept,
                                when the relay's sender is this account too;
                                cross-checked against gzcoord-sent.jsonl
  BROADCAST: true               inbound
  TO this agent's address       inbound
  TO-ROLE a role                inbound when role-history.jsonl shows this
                                agent held it at the message's time;
                                otherwise unresolved
  anything else                 never stored; counted, never read further

HELLO and GOODBYE (presence, retired) and records that are not GZCOORD/1
are never stored, as the inbox never journals them. A channel ending in
`:control` is refused before any request. The engine's keys decide
idempotence: a second run, or a message the live inbox already captured,
is the same row (ADR-041 rule 5).

The report is <state>/agents/<login>/episodic-import.json: counts per
decision, the unresolved TO-ROLE ids, the ledger mismatches, the last seq
seen per channel; no message content and no token. When every channel was
read to its end, the journal's meta row records it (gzcoord_imported_at,
gzcoord_import_seqs), and --if-needed then does nothing.

exit 0 imported (or already, with --if-needed); 1 a relay that failed, no
token, or a journal that refused (another agent's, say); 2 usage or a
control channel.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import pwd
import socket
import sqlite3
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import episodic  # noqa: E402
import relay  # noqa: E402

# gzmsg.mjs RETIRED_TYPES: presence, which the inbox acknowledges and never
# journals (tests/test_episodic_import.py holds this equal to its source).
RETIRED_TYPES = ("HELLO", "GOODBYE")
REPORT = "episodic-import.json"
DECISIONS = ("outbound", "outbound_same", "outbound_promoted", "outbound_conflict",
             "to_me", "to_role", "to_role_unresolved", "broadcast", "before_birth", "from_me_unverified",
             "inbound_written", "inbound_same", "inbound_conflict", "others", "retired", "not_gzcoord", "no_time")


def _when(ts) -> datetime.datetime | None:
    """A carrier's or a history line's timestamp, as an aware UTC time. The
    relay's carries microseconds and a space or a T; a naive one is UTC."""
    if not isinstance(ts, str) or not ts.strip():
        return None
    try:
        t = datetime.datetime.fromisoformat(ts.strip().replace(" ", "T").replace("Z", "+00:00"))
    except ValueError:
        return None
    return t.replace(tzinfo=datetime.UTC) if t.tzinfo is None else t.astimezone(datetime.UTC)


def birth(agent_id: str) -> datetime.datetime:
    """The UUIDv7's first 48 bits: milliseconds since the epoch, when the id
    was minted — the agent's birth (ADR-039)."""
    ms = int(agent_id.replace("-", "")[:12], 16)
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.UTC)


def role_spans(path: str) -> list[tuple[datetime.datetime, str | None]]:
    """(from, role) in valid_from order: each line holds from its
    valid_from until the next; a deactivation holds no role. A line that
    cannot be read decides nothing."""
    spans = []
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        return []
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        t = _when(rec.get("valid_from")) if isinstance(rec, dict) else None
        if t is not None:
            spans.append((t, rec.get("role") or None))
    return sorted(spans, key=lambda s: s[0])


def role_at(spans: list, t: datetime.datetime) -> str | None:
    held = None
    for start, role in spans:
        if start > t:
            break
        held = role
    return held


def read_ledger(path: str) -> dict[str, list[dict]]:
    """gzcoord-sent.jsonl by id: every post send.mjs recorded (a
    retransmission is another line with the same id)."""
    out: dict[str, list[dict]] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict) and isinstance(rec.get("id"), str):
                    out.setdefault(rec["id"], []).append(rec)
    except FileNotFoundError:
        pass
    return out


def outbound(conn: sqlite3.Connection, text: str, mtype: str, meta: dict, seq, ts,
             carrier: str = episodic.DEFAULT_CARRIER) -> str:
    """This agent's own message as the carrier holds it: accepted, since the
    carrier has it. The same body again is the same row, given the carrier's
    seq if it had none, and accepted if a live send left it pending or
    failed (the post reached the carrier after all). Another body under the
    same id is kept in `conflicts`, never over the row."""
    h = hashlib.sha256(text.encode()).hexdigest()
    mid = meta.get("MESSAGE-ID") or f"sha256:{h}"
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = episodic._row(conn, "outbound", mid)
        if row and row[1] == h:
            promoted = row[2] != "accepted"
            conn.execute("UPDATE episodes SET state='accepted', carrier=COALESCE(carrier, ?), "
                         "carrier_seq=COALESCE(carrier_seq, ?) WHERE id=?", (carrier, seq, row[0]))
            out = "outbound_promoted" if promoted else "outbound_same"
        elif row:
            conn.execute("INSERT OR IGNORE INTO conflicts VALUES (?, 'outbound', ?, ?, ?, ?)",
                         (mid, h, text, episodic.now(), seq))
            out = "outbound_conflict"
        else:
            conn.execute("INSERT INTO episodes (id, source, direction, state, happened_at, recorded_at, message_id, "
                         "in_reply_to, type, sender, carrier, carrier_seq, content, content_hash, metadata_json) "
                         "VALUES (?, ?, 'outbound', 'accepted', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (str(uuid.uuid4()), episodic.SOURCE, episodic._seconds(ts), episodic.now(), mid,
                          meta.get("IN-REPLY-TO"), mtype, meta.get("FROM"), carrier, seq, text, h,
                          json.dumps(meta, sort_keys=True)))
            out = "outbound"
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return out


class Importer:
    def __init__(self, conn: sqlite3.Connection, me: str, agent_id: str, state: str):
        self.conn, self.me = conn, me
        self.born = birth(agent_id)
        self.spans = role_spans(os.path.join(state, "role-history.jsonl"))
        self.ledger = read_ledger(os.path.join(state, "gzcoord-sent.jsonl"))
        self.counts = dict.fromkeys(DECISIONS, 0)
        self.unresolved: list[dict] = []
        self.mismatch = {"not_in_ledger": [], "hash_differs": [], "seq_differs": []}

    def decide(self, rec: dict) -> tuple[str, dict | None]:
        """(decision, the inbound record to journal or None). Never reads a
        record further than its addressing once it is someone else's."""
        text = rec.get("content")
        try:
            if not isinstance(text, str):
                raise episodic.JournalError("no content")
            mtype, meta = episodic.parse_header(text)
        except episodic.JournalError:
            return "not_gzcoord", None
        if mtype in RETIRED_TYPES:
            return "retired", None
        seq, ts = rec.get("seq"), rec.get("ts_full") or rec.get("timestamp") or rec.get("ts")
        when = _when(ts)
        # Nothing from before this agent's birth is its own, sent or received:
        # a login is reused across agents (ADR-039), and what was sent by or
        # to the previous holder of the name is that agent's history.
        if when is None:
            return "no_time", None
        if when < self.born:
            return "before_birth", None
        if meta.get("FROM") == self.me:
            # The content's FROM is the sender's claim; the relay records who
            # posted it. Before the journal there is no body to compare an
            # echo against (rule 5), so both must name this account.
            if rec.get("sender") != self.me:
                return "from_me_unverified", None
            self._check_ledger(text, meta, seq)
            return outbound(self.conn, text, mtype, meta, seq, ts), None
        keep = {"content": text, "seq": seq, "ts": ts}
        # inbox.mjs forMe, in its order: a broadcast, else TO decides alone,
        # else TO-ROLE.
        if meta.get("BROADCAST") == "true":
            return "broadcast", keep
        if "TO" in meta:
            return ("to_me", keep) if meta["TO"] == self.me else ("others", None)
        if "TO-ROLE" in meta:
            role = meta["TO-ROLE"]
            if role_at(self.spans, when) == role:
                return "to_role", keep
            self.unresolved.append({"message_id": meta.get("MESSAGE-ID") or f"sha256:{hashlib.sha256(text.encode()).hexdigest()}",
                                    "seq": seq, "to_role": role, "why": "role not held then"})
            return "to_role_unresolved", None
        return "others", None

    def _check_ledger(self, text: str, meta: dict, seq) -> None:
        mid = meta.get("MESSAGE-ID")
        entries = self.ledger.get(mid) if mid else None
        if not entries:
            self.mismatch["not_in_ledger"].append({"message_id": mid, "seq": seq})
            return
        h = hashlib.sha256(text.encode()).hexdigest()
        if not any(e.get("sha256") == h for e in entries):
            self.mismatch["hash_differs"].append({"message_id": mid, "seq": seq})
        elif seq is not None and not any(e.get("seq") == seq for e in entries if e.get("sha256") == h):
            self.mismatch["seq_differs"].append({"message_id": mid, "seq": seq,
                                                 "ledger_seq": [e.get("seq") for e in entries]})

    def page(self, msgs: list) -> None:
        inbound = []
        for rec in sorted((m for m in msgs if isinstance(m, dict)), key=lambda m: int(m.get("seq") or 0)):
            decision, keep = self.decide(rec)
            self.counts[decision] += 1
            if keep:
                inbound.append(keep)
        if inbound:
            c = episodic.inbound(self.conn, inbound)
            # Already in the journal (live capture, or an earlier run): the
            # same row; a differing body sits in `conflicts`.
            self.counts["inbound_written"] += c["written"]
            self.counts["inbound_same"] += c["same"]
            self.counts["inbound_conflict"] += c["conflict"]


def _ensure_marker_columns(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(meta)")}
    for col in ("gzcoord_imported_at", "gzcoord_import_seqs"):
        if col not in cols:
            conn.execute(f"ALTER TABLE meta ADD COLUMN {col} TEXT")


def imported(conn: sqlite3.Connection) -> str | None:
    _ensure_marker_columns(conn)
    row = conn.execute("SELECT gzcoord_imported_at FROM meta").fetchone()
    return row[0] if row else None


def _write_report(path: str, report: dict) -> None:
    old = os.umask(0o077)
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        os.umask(old)


def main(argv: list[str]) -> int:
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 0
    if_needed = "--if-needed" in argv
    projects = [a for a in argv if a != "--if-needed"]
    if any(p.startswith("-") for p in projects):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    try:
        pairs, none = relay.channels(projects or relay.integrated_projects(), os.environ)
    except (ValueError, OSError) as e:
        print(f"gzcoord-import: {e}", file=sys.stderr)
        return 1
    for p in none:
        print(f"gzcoord-import: {p} has no GZCoord integration; no channel to import from")
    control = [c for _, c in pairs if relay.is_control(c)]
    if control:
        print(f"gzcoord-import: {control[0]} is the control plane's channel, never GZCOORD/1 messages; refused",
              file=sys.stderr)
        return 2
    try:
        agent_id = episodic.own_agent_id()
        conn = episodic.connect(agent_id=agent_id)
        if if_needed and imported(conn):
            print(f"gzcoord-import: already imported ({imported(conn)}); nothing to do")
            return 0
    except (episodic.JournalError, sqlite3.Error, OSError) as e:
        print(f"gzcoord-import: {e}", file=sys.stderr)
        return 1
    me = pwd.getpwuid(os.getuid())
    tok = relay.own_token(os.environ.get("HOME") or me.pw_dir)
    if not tok:
        print(f"gzcoord-import: no {relay.TOKEN_NAME} in this account's secrets.env (fabric-secrets sync first)",
              file=sys.stderr)
        return 1
    address = episodic.own_address()
    state = episodic.state_dir()
    imp = Importer(conn, address, agent_id, state)
    # A consumer the relay has never seen lists from seq 1. It is this
    # run's alone and never acknowledged: the account's own consumer (its
    # address) keeps its cursor wherever the inbox left it.
    consumer = f"{address}#episodic-import-{uuid.uuid4()}"
    seqs, rc = {}, 0
    for url, channel in pairs:
        last, pages, ok = None, 0, True
        try:
            for msgs in relay.pages(url, tok, channel, consumer):
                imp.page(msgs)
                pages += 1
                last = max(int(m["seq"]) for m in msgs)
        except (OSError, ValueError, KeyError, TypeError, episodic.JournalError, sqlite3.Error) as e:
            print(f"gzcoord-import: {channel} at {url}: {e}", file=sys.stderr)
            rc, ok = 1, False
        seqs[channel] = {"relay": url, "last_seq": last, "pages": pages, "complete": ok}
        print(f"gzcoord-import: {address} on {channel}: {pages} page(s), last seq {last if last is not None else '-'}")
    report = {"agent_id": agent_id, "address": address, "at": episodic.now(), "complete": rc == 0,
              "channels": seqs, "counts": imp.counts, "to_role_unresolved": imp.unresolved,
              "ledger": imp.mismatch, "birth": imp.born.strftime("%Y-%m-%dT%H:%M:%SZ")}
    try:
        _write_report(os.path.join(state, REPORT), report)
        if rc == 0:
            _ensure_marker_columns(conn)
            conn.execute("UPDATE meta SET gzcoord_imported_at=?, gzcoord_import_seqs=?",
                         (report["at"], json.dumps({c: v["last_seq"] for c, v in seqs.items()}, sort_keys=True)))
    except (OSError, sqlite3.Error) as e:
        print(f"gzcoord-import: {e}", file=sys.stderr)
        return 1
    c = imp.counts
    sent = c["outbound"] + c["outbound_same"] + c["outbound_promoted"] + c["outbound_conflict"]
    print(f"gzcoord-import: {sent} sent ({c['outbound']} new), {c['to_me'] + c['to_role'] + c['broadcast']} received "
          f"({c['inbound_written']} new), "
          f"{c['to_role_unresolved']} TO-ROLE unresolved, "
          f"{sum(len(v) for v in imp.mismatch.values())} ledger mismatch(es); report {os.path.join(state, REPORT)}")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
