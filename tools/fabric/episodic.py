#!/usr/bin/env python3
"""tools/fabric/episodic.py — this agent's episodic journal (agent-fabric
ADR-041): the exact GZCoord messages it sent and was addressed, written at
the moment they cross the carrier, in its own runtime state.

    episodic.py gzcoord-out-pending [--project P] [--working-copy W]   message on stdin
    episodic.py gzcoord-out-final MESSAGE-ID --state accepted|failed [--seq N] [--carrier C]
    episodic.py gzcoord-in [--carrier C] [--project P] [--working-copy W]
                                            JSON lines on stdin: {"content", "seq", "ts"}
    episodic.py where                       the journal's path

Run AS THE ACCOUNT (send.mjs and inbox.mjs call it); every caller passes
only messages it is entitled to read: its own, or ones addressed to it.
Nothing here prints a message's content.

WHY ABOVE THE TRANSPORT. The carrier today (the Claude-Bridge relay) keeps
its history by accident; a peer-to-peer carrier may keep none by design.
A message that was presented and not journaled could not be recovered, so
the journal is written before the carrier send (outbound) and before the
acknowledgement that lets the carrier forget it (inbound).

THE ROWS. One per (source, direction, message id). The same id again with
the same body is the same row. Outbound with another body is refused
(exit 3): this agent would be reusing an id. Inbound with another body is
the sender's reuse: the first copy stands, the other is kept in
`conflicts` and said, and the call succeeds, or the inbox would never
acknowledge it and see it forever. A record from this agent's own address
coming back on the channel (a broadcast it sent) is not a second episode:
it fills the outbound row's carrier sequence.

THE OWNER. The database names the agent id it belongs to; opened by an
account whose id differs (a reused login, ADR-039) it refuses.

exit 0 written; 1 failure (said); 2 usage; 3 integrity (outbound id reuse).
"""
from __future__ import annotations

import hashlib
import json
import os
import pwd
import re
import socket
import sqlite3
import sys
import time
import uuid

SCHEMA_VERSION = 1
SOURCE = "gzcoord"
DEFAULT_CARRIER = "claude-bridge"
STATES_OUT = ("pending", "accepted", "failed")


class JournalError(Exception):
    """The whole answer, in one line; never a message's content."""


class IntegrityError(JournalError):
    pass


# Three facts from runtime/identity.py and secret_store.py, read here rather
# than imported: their imports (subprocess, argparse, tempfile) were 210 of
# the 290 ms each journal call took, and send.mjs makes two calls per message
# (measured 2026-10-01, docs/live-checks/2026-10-01-episodic-journal.md).
# tests/test_episodic.py holds each equal to its source.
AGENT_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def _login() -> str:
    return pwd.getpwuid(os.geteuid()).pw_name


def state_dir() -> str:
    """identity.agent_state_dir() for this login."""
    override = os.environ.get("AGENT_FABRIC_STATE_DIR")
    root = os.path.abspath(override) if override else os.path.join(
        os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state"), "agent-fabric")
    return os.path.join(root, "agents", _login())


def own_agent_id() -> str | None:
    """secret_store.own_agent_id(): the id in this account's own store."""
    home = os.environ.get("HOME") or pwd.getpwuid(os.getuid()).pw_dir
    store = os.environ.get("AGENT_FABRIC_SECRET_STORE") or os.path.join(home, ".local", "share", "agent-fabric", "secrets")
    try:
        with open(os.path.join(store, ".agent-id"), encoding="utf-8") as fh:
            aid = fh.read().strip()
    except FileNotFoundError:
        return None
    if not AGENT_ID_RE.match(aid):
        raise JournalError(f"the store's .agent-id is not an agent id: {aid[:40]!r}")
    return aid


def db_path() -> str:
    return os.path.join(state_dir(), "episodic.db")


def own_address() -> str:
    """<host>/<login>, as the inbox and send.mjs address this account
    (identity.current_host() is the short hostname)."""
    return f"{socket.gethostname().split('.')[0]}/{_login()}"


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _seconds(ts: str | None) -> str:
    """A carrier's timestamp in the journal's one form, to the second, UTC
    (2026-10-01T17:19:04Z): the relay's carries microseconds, and the
    journal orders by text."""
    if not ts:
        return now()
    head = ts.replace(" ", "T").split(".")[0].rstrip("Z")
    return head + "Z" if len(head) == 19 else ts


_FIRST = re.compile(r"^\[GZCOORD/1\] ([A-Z][A-Z0-9-]*)$")
_KEY = re.compile(r"^([A-Z][A-Z0-9-]*): ")
_SECTION = re.compile(r"^[A-Z][A-Z0-9-]*:$")
# What JS String.prototype.trim() strips (ECMAScript WhiteSpace and
# LineTerminator): str.strip() strips another set (\x1c-\x1f, not \ufeff),
# and a value trimmed differently is a message keyed differently.
_JS_TRIM = "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"


def parse_header(text: str) -> tuple[str, dict[str, str]]:
    """(type, metadata) of a GZCOORD/1 message, read exactly as gzmsg.mjs
    parse() reads it: the inbox decides a record is addressed with that
    parser, and the journal must key the message the inbox saw (review of
    #78: a header that ended at a blank line read body lines as header).
    A byte-order mark is dropped; KEY: value lines up to the first section
    marker; a repeated key keeps its last value. Validating is send.mjs's
    and the reader's job."""
    lines = text.lstrip("\ufeff").replace("\r\n", "\n").split("\n")
    m = _FIRST.match(lines[0] if lines else "")
    if not m:
        raise JournalError("not a GZCOORD/1 message")
    meta: dict[str, str] = {}
    for line in lines[1:]:
        if _SECTION.match(line):
            break
        k = _KEY.match(line)
        if k:
            meta[k.group(1)] = line[k.end():].strip(_JS_TRIM)
    return m.group(1), meta


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def connect(path: str | None = None, agent_id: str | None = None) -> sqlite3.Connection:
    """The journal, created private (directory 0700, files 0600 — the WAL
    and its index too, so the umask is set around the open) and checked
    against its owner."""
    path = path or db_path()
    owner = agent_id or own_agent_id()
    if not owner:
        raise JournalError("this account has no agent id (fabric-secrets store id); no journal without an owner")
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    os.chmod(os.path.dirname(path), 0o700)
    old = os.umask(0o077)
    try:
        conn = sqlite3.connect(path, timeout=5.0, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("CREATE TABLE IF NOT EXISTS meta (schema_version INTEGER NOT NULL, "
                     "owner_agent_id TEXT NOT NULL, created_at TEXT NOT NULL)")
        conn.execute("""CREATE TABLE IF NOT EXISTS episodes (
            id TEXT PRIMARY KEY, source TEXT NOT NULL, direction TEXT, state TEXT NOT NULL,
            happened_at TEXT NOT NULL, recorded_at TEXT NOT NULL,
            session_id TEXT, project TEXT, working_copy TEXT,
            message_id TEXT, in_reply_to TEXT, type TEXT, sender TEXT,
            carrier TEXT, carrier_seq INTEGER,
            content TEXT NOT NULL, content_hash TEXT NOT NULL, metadata_json TEXT NOT NULL,
            UNIQUE (source, direction, message_id))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS conflicts (
            message_id TEXT NOT NULL, direction TEXT NOT NULL, content_hash TEXT NOT NULL,
            content TEXT NOT NULL, seen_at TEXT NOT NULL, carrier_seq INTEGER,
            PRIMARY KEY (message_id, direction, content_hash))""")
        for col in ("happened_at", "message_id", "in_reply_to", "project"):
            conn.execute(f"CREATE INDEX IF NOT EXISTS episodes_{col} ON episodes({col})")
        row = conn.execute("SELECT owner_agent_id, schema_version FROM meta").fetchone()
        if row is None:
            conn.execute("INSERT INTO meta VALUES (?, ?, ?)", (SCHEMA_VERSION, owner, now()))
        elif row[0] != owner:
            conn.execute("ROLLBACK")
            conn.close()
            raise JournalError(f"{path} belongs to agent {row[0]}, not {owner}: a reused login never reads "
                               "another agent's history")
        conn.execute("COMMIT")
    finally:
        os.umask(old)
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(path + suffix):
            os.chmod(path + suffix, 0o600)
    return conn


def _row(conn: sqlite3.Connection, direction: str, message_id: str):
    return conn.execute("SELECT id, content_hash, state FROM episodes WHERE source=? AND direction=? AND message_id=?",
                        (SOURCE, direction, message_id)).fetchone()


def out_pending(conn: sqlite3.Connection, text: str, project: str | None = None, working_copy: str | None = None) -> str:
    """The outbound row, before the carrier sees the message. Its id."""
    mtype, meta = parse_header(text)
    if not meta.get("MESSAGE-ID"):
        raise JournalError("the message has no MESSAGE-ID")
    mid, h = meta["MESSAGE-ID"], _sha(text)
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = _row(conn, "outbound", mid)
        if row:
            if row[1] != h:
                raise IntegrityError(f"MESSAGE-ID {mid} is already in this journal with another body; "
                                     "an id is never reused")
            if row[2] == "failed":
                conn.execute("UPDATE episodes SET state='pending', recorded_at=? WHERE id=?", (now(), row[0]))
            conn.execute("COMMIT")
            return row[0]
        eid = str(uuid.uuid4())
        conn.execute("INSERT INTO episodes (id, source, direction, state, happened_at, recorded_at, project, "
                     "working_copy, message_id, in_reply_to, type, sender, content, content_hash, metadata_json) "
                     "VALUES (?, ?, 'outbound', 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (eid, SOURCE, now(), now(), project, working_copy, mid, meta.get("IN-REPLY-TO"), mtype,
                      meta.get("FROM"), text, h, json.dumps(meta, sort_keys=True)))
        conn.execute("COMMIT")
        return eid
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def out_final(conn: sqlite3.Connection, message_id: str, state: str, seq: int | None = None,
              carrier: str = DEFAULT_CARRIER) -> None:
    if state not in ("accepted", "failed"):
        raise JournalError(f"state {state!r} is not accepted or failed")
    # Only a pending row takes an outcome of failed: the same message sent
    # again while the relay is down must not mark the copy it already
    # delivered as failed (review of #78).
    row = _row(conn, "outbound", message_id)
    if not row:
        raise JournalError(f"no outbound row for MESSAGE-ID {message_id} (a pending row comes first)")
    if state == "failed" and row[2] != "pending":
        return
    conn.execute("UPDATE episodes SET state=?, carrier=?, carrier_seq=COALESCE(?, carrier_seq), recorded_at=? "
                 "WHERE id=?", (state, carrier, seq, now(), row[0]))


def inbound(conn: sqlite3.Connection, records: list[dict], carrier: str = DEFAULT_CARRIER,
            project: str | None = None, working_copy: str | None = None) -> dict:
    """Addressed records, one transaction: all journaled or none (so the
    caller acknowledges none). Counts by outcome."""
    me = own_address()
    counts = {"written": 0, "same": 0, "echo": 0, "conflict": 0, "claims_me": 0}
    conn.execute("BEGIN IMMEDIATE")
    try:
        for rec in records:
            text = rec["content"]
            h, seq = _sha(text), rec.get("seq")
            try:
                mtype, meta = parse_header(text)
            except JournalError:
                # The inbox addressed it, so it is kept, whatever its shape.
                mtype, meta = None, {}
            # A message with no id (a retired shape, a broadcast the relay did
            # not validate) is keyed by its body: one unkeyable record must
            # not hold every other one in the page (review of #78).
            mid = meta.get("MESSAGE-ID") or f"sha256:{h}"
            if meta.get("FROM") == me:
                # Its own message coming back only when this journal holds that
                # very message: a FROM in the content is the sender's claim, and
                # a forged one must not pass for an echo, shown but not kept.
                own = _row(conn, "outbound", mid)
                if own and own[1] == h:
                    conn.execute("UPDATE episodes SET carrier_seq=COALESCE(carrier_seq, ?) WHERE id=?",
                                 (seq, own[0]))
                    counts["echo"] += 1
                    continue
                counts["claims_me"] += 1
            row = _row(conn, "inbound", mid)
            if row and row[1] == h:
                counts["same"] += 1
                continue
            if row:
                conn.execute("INSERT OR IGNORE INTO conflicts VALUES (?, 'inbound', ?, ?, ?, ?)",
                             (mid, h, text, now(), seq))
                counts["conflict"] += 1
                continue
            conn.execute("INSERT INTO episodes (id, source, direction, state, happened_at, recorded_at, project, "
                         "working_copy, message_id, in_reply_to, type, sender, carrier, carrier_seq, content, "
                         "content_hash, metadata_json) VALUES (?, ?, 'inbound', 'received', ?, ?, ?, ?, ?, ?, ?, ?, "
                         "?, ?, ?, ?, ?)",
                         (str(uuid.uuid4()), SOURCE, _seconds(rec.get("ts")), now(), project, working_copy, mid,
                          meta.get("IN-REPLY-TO"), mtype, meta.get("FROM"), carrier, seq, text, h,
                          json.dumps(meta, sort_keys=True)))
            counts["written"] += 1
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return counts


def _flag(argv: list[str], name: str) -> str | None:
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 0 if argv else 2
    cmd = argv[0]
    try:
        if cmd == "where":
            print(db_path())
            return 0
        project, wc = _flag(argv, "--project"), _flag(argv, "--working-copy")
        carrier = _flag(argv, "--carrier") or DEFAULT_CARRIER
        if cmd == "gzcoord-out-pending":
            conn = connect()
            out_pending(conn, sys.stdin.read(), project, wc)
            return 0
        if cmd == "gzcoord-out-final":
            if len(argv) < 2 or _flag(argv, "--state") is None:
                print("usage: episodic.py gzcoord-out-final MESSAGE-ID --state accepted|failed [--seq N]", file=sys.stderr)
                return 2
            seq = _flag(argv, "--seq")
            out_final(connect(), argv[1], _flag(argv, "--state"), int(seq) if seq not in (None, "") else None, carrier)
            return 0
        if cmd == "gzcoord-in":
            records = [json.loads(line) for line in sys.stdin if line.strip()]
            if not all(isinstance(r, dict) and isinstance(r.get("content"), str) for r in records):
                raise JournalError("gzcoord-in takes one JSON object with a content string per line")
            counts = inbound(connect(), records, carrier, project, wc)
            if counts["conflict"]:
                print(f"episodic: {counts['conflict']} message(s) reuse an id this journal holds with another body; "
                      "the first copy stands, the other is in `conflicts`", file=sys.stderr)
            if counts["claims_me"]:
                print(f"episodic: {counts['claims_me']} message(s) name this account as FROM but are no message it "
                      "sent; kept as received", file=sys.stderr)
            return 0
        print(f"episodic: unknown command {cmd!r}", file=sys.stderr)
        return 2
    except IntegrityError as e:
        print(f"episodic: {e}", file=sys.stderr)
        return 3
    except (JournalError, sqlite3.Error, OSError, ValueError, KeyError) as e:
        print(f"episodic: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
