#!/usr/bin/env python3
"""tools/fabric/history.py — what this agent said and was told, read back
from its own episodic journal (agent-fabric ADR-041). Behind bin/fabric-history.

    fabric-history [TEXT] [--since ISO] [--until ISO] [--project P]
                   [--thread MESSAGE-ID] [--limit N] [--full]
                   [--include-failed] [--json]

TEXT keeps the episodes whose message contains it (case-insensitive).
--thread walks IN-REPLY-TO both ways from that MESSAGE-ID and shows the
whole conversation. Output is chronological, newest last, at most --limit
episodes (default 20, the newest that match), each cut to 600 characters
unless --full. An outbound message the carrier never accepted is hidden
unless --include-failed.

What it prints is history, not current truth: a message may describe a
tree that has moved since, and a decision it reports may have been
reversed. Verify a claim against the repository before acting on it.
Credential-shaped values (the corpus hygiene patterns, layout.py) are
withheld in every form of output, shown by kind and episode only.

exit 0 (also when nothing matches); 1 the journal is unreadable or
another agent's; 2 usage.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import episodic  # noqa: E402
import layout  # noqa: E402

BANNER = "history, not current truth — verify a claim against the tree before acting on it (ADR-041)"
CUT = 600


def credential_patterns() -> list:
    return [(p, label) for p, label, _ in layout.load_hygiene_patterns([]) if label.startswith("credential")]


def mask(text: str | None, eid: str, patterns: list) -> str | None:
    if text is None:
        return None
    for pat, label in patterns:
        text = pat.sub(f"[withheld: {label}, episode {eid[:8]}]", text)
    return text


def open_readonly() -> sqlite3.Connection:
    """The journal, owner-checked, read without creating it."""
    path = episodic.db_path()
    if not os.path.exists(path):
        raise episodic.JournalError(f"no journal yet at {path}: nothing sent or received since ADR-041 landed here")
    conn = episodic.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def thread_ids(conn: sqlite3.Connection, start: str) -> set[str]:
    """Every MESSAGE-ID connected to `start` by IN-REPLY-TO, either way."""
    seen, todo = set(), [start]
    while todo:
        mid = todo.pop()
        if mid in seen:
            continue
        seen.add(mid)
        for (reply_to,) in conn.execute("SELECT in_reply_to FROM episodes WHERE message_id=? AND in_reply_to IS NOT NULL", (mid,)):
            todo.append(reply_to)
        for (child,) in conn.execute("SELECT message_id FROM episodes WHERE in_reply_to=?", (mid,)):
            todo.append(child)
    return seen


def query(conn: sqlite3.Connection, args) -> list[sqlite3.Row]:
    where, params = [], []
    if not args.include_failed:
        # A pending send may have left (the post succeeded, its outcome was
        # not written): shown, tagged [pending]; only a failed one is hidden.
        where.append("NOT (direction='outbound' AND state='failed')")
    if args.since:
        where.append("happened_at >= ?"); params.append(args.since)
    if args.until:
        where.append("happened_at <= ?"); params.append(args.until)
    if args.project:
        where.append("project = ?"); params.append(args.project)
    if args.text:
        where.append("instr(lower(content), lower(?)) > 0"); params.append(args.text)
    if args.thread:
        ids = sorted(thread_ids(conn, args.thread))
        where.append(f"message_id IN ({','.join('?' * len(ids))})"); params += ids
    sql = (f"SELECT * FROM episodes {('WHERE ' + ' AND '.join(where)) if where else ''} "
           "ORDER BY happened_at DESC, recorded_at DESC LIMIT ?")
    rows = conn.execute(sql, (*params, args.limit)).fetchall()
    return list(reversed(rows))


def render(rows: list[sqlite3.Row], full: bool, patterns: list) -> list[str]:
    out = [f"# {BANNER}", f"# {len(rows)} episode(s), oldest first"]
    for r in rows:
        arrow = "→" if r["direction"] == "outbound" else "←"
        state = "" if r["state"] in ("accepted", "received") else f" [{r['state']}]"
        m = lambda k: mask(r[k], r["id"], patterns)  # noqa: E731 — every printed field is a stored claim
        out.append(f"\n## {r['happened_at']} {arrow} {m('type')} {m('message_id')}{state}"
                   + (f" (re {m('in_reply_to')})" if r["in_reply_to"] else ""))
        text = mask(r["content"], r["id"], patterns)
        if not full and len(text) > CUT:
            text = text[:CUT] + f"\n… ({len(r['content']) - CUT} more characters: --full, or --thread {m('message_id')})"
        out.append(text.rstrip("\n"))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="fabric-history", description=BANNER)
    ap.add_argument("text", nargs="?")
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--project")
    ap.add_argument("--thread")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--include-failed", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.limit < 1:
        ap.error("--limit is at least 1")
    try:
        conn = open_readonly()
        rows = query(conn, args)
    except (episodic.JournalError, sqlite3.Error, OSError) as e:
        print(f"fabric-history: {e}", file=sys.stderr)
        return 1
    patterns = credential_patterns()
    if args.json:
        print(json.dumps({"banner": BANNER, "episodes": [
            {k: (mask(r[k], r["id"], patterns) if isinstance(r[k], str) else r[k])
             for k in ("happened_at", "direction", "state", "type", "message_id", "in_reply_to", "sender", "project",
                       "carrier", "carrier_seq", "content")} for r in rows]}, indent=1))
    else:
        print("\n".join(render(rows, args.full, patterns)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
