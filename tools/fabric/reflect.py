#!/usr/bin/env python3
"""tools/fabric/reflect.py — what this agent sent and received since its last
reflection pass, and the cursor that says where that was (agent-fabric
ADR-058). Behind bin/fabric-reflect.

    fabric-reflect [--max N] [--full] [--json]      the next pass
    fabric-reflect done --through ROW [--max N]     the pass is finished
    fabric-reflect status [--json]                  the cursor, and what waits

A pass prints the GZCoord messages of this login's own episodic journal
(ADR-041; never another login's) recorded after the cursor, oldest first, at
most --max of them (default 200), grouped by thread: IN-REPLY-TO chains,
and messages in no chain by their SUBJECT. Each carries its MESSAGE-ID,
direction, peer and date; a body is cut to 1500 characters unless --full (--json is never cut).
When more wait than the pass holds it says how many are left for the next.
A send the carrier did not accept is shown tagged [failed], like a
[pending] one: a retry updates the same journal row, so a pass that skipped
it would never show it once it went through. Credential-shaped values are withheld as fabric-history withholds
them (ADR-041 rule 7), in both output forms.

Reading moves nothing. `done` records, in this login's state
(reflect-cursor.json, written atomically), the last message of the pass; it
is the only thing that does, so a pass that was interrupted before `done`
is read again from the same message. `done --through ROW` closes exactly the
pass that printed "through row ROW" (its --json: "through"); ROW is
mandatory, because a `done` that worked out its own end would close what the
journal gained or the --max differed by since the pass, messages no pass
showed. ROW is refused when it lies more than --max messages past the cursor
(a pass shows at most that many; give `done` the --max the pass had). The
cursor never moves back.

The cursor is a position in the journal's insertion order (SQLite rowid),
not a time: a message imported late lands after the messages already read
and is read by the next pass. A send that was pending or failed when a pass
read it is shown tagged and is not shown again once the cursor is past it,
whatever becomes of it.

Nothing here writes memory: the agent drafts and judges (ADR-058 rule 3).

exit 0 (also when nothing waits); 1 the journal or the cursor is unusable
or another agent's; 2 usage.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "runtime"))
import episodic  # noqa: E402
import history  # noqa: E402
import identity  # noqa: E402
import layout  # noqa: E402

BANNER = "your own messages, history not current truth — verify a claim against the tree before writing it down (ADR-058)"
DEFAULT_MAX = 200
CUT = 1500
CURSOR_FILE = "reflect-cursor.json"


class CursorError(Exception):
    """The whole answer, in one line."""


def cursor_path() -> str:
    return os.path.join(episodic.state_dir(), CURSOR_FILE)


def read_cursor(owner: str) -> dict:
    """{} when no pass has finished yet. A cursor that is unreadable, or
    that was written for another agent id (a reused login), is refused: a
    cursor read as "none" would hand the whole journal back as new, and one
    kept across owners would skip messages that were never read."""
    try:
        with open(cursor_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        raise CursorError(f"{cursor_path()} is unreadable ({e}); remove it to read the journal from the start") from None
    if (not isinstance(data, dict) or not isinstance(data.get("row"), int) or isinstance(data["row"], bool)
            or data["row"] < 0 or not isinstance(data.get("agent_id"), str)):
        raise CursorError(f"{cursor_path()} is not a cursor this code wrote; remove it to read the journal from the start")
    if data["agent_id"] != owner:
        raise CursorError(f"{cursor_path()} belongs to agent {data['agent_id']}, not {owner}; "
                          "remove it to read this journal from the start")
    return data


def cursor(conn: sqlite3.Connection, owner: str) -> dict:
    """read_cursor, and a cursor whose recorded episode is not at its row refused
    (journal replaced, restored, vacuumed or truncated): "nothing waits" would be false."""
    cur = read_cursor(owner)
    if not cur:
        return cur
    # The episode the cursor closed on must still sit at that row: a restored
    # or vacuumed journal keeps the owner but moves the rows, and a row that
    # means nothing would skip messages without a word.
    at = conn.execute("SELECT id FROM episodes WHERE rowid=?", (cur["row"],)).fetchone()
    if at is None or at[0] != cur.get("episode"):
        raise CursorError(f"the cursor at row {cur['row']} does not match this journal (it ends at row "
                          f"{conn.execute('SELECT COALESCE(MAX(rowid), 0) FROM episodes').fetchone()[0]}); "
                          f"remove {cursor_path()} to read the journal from the start")
    return cur


def write_cursor(owner: str, row: int, episode_id: str) -> None:
    # The episode's own id, never its MESSAGE-ID: a header can hold a
    # credential-shaped value, and the state file is not masked on read.
    body = {"agent_id": owner, "row": row, "episode": episode_id, "done_at": episodic.now()}
    identity.atomic_write(cursor_path(), json.dumps(body, indent=1, sort_keys=True) + "\n", mode=0o600)


def waiting(conn: sqlite3.Connection, after: int, limit: int) -> list[sqlite3.Row]:
    """The first `limit` messages after the cursor, oldest first."""
    return conn.execute("SELECT rowid AS row, * FROM episodes WHERE source=? AND rowid > ? ORDER BY rowid LIMIT ?",
                        (episodic.SOURCE, after, limit)).fetchall()


def count_waiting(conn: sqlite3.Connection, after: int) -> int:
    return conn.execute("SELECT COUNT(*) FROM episodes WHERE source=? AND rowid > ?", (episodic.SOURCE, after)).fetchone()[0]


def describe(r: sqlite3.Row) -> dict:
    """The fields a pass shows, from the stored header (the journal's own
    parse), so the peer is the other side whichever way the message went."""
    try:
        meta = json.loads(r["metadata_json"])
    except ValueError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    out = r["direction"] == "outbound"
    return {"row": r["row"], "episode": r["id"], "date": r["happened_at"], "direction": r["direction"],
            "state": r["state"], "type": r["type"], "message_id": r["message_id"], "in_reply_to": r["in_reply_to"],
            "peer": meta.get("TO") if out else (meta.get("FROM") or r["sender"]),
            "subject": meta.get("SUBJECT"), "content": r["content"]}


def group(messages: list[dict]) -> list[list[dict]]:
    """Threads: messages joined by IN-REPLY-TO (through a parent outside the
    pass too, so two replies to one old message sit together); a message in
    no chain joins the others with its exact SUBJECT. Groups in the order
    of their first message, each message in journal order."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for m in messages:
        if m["in_reply_to"]:
            parent[find(m["message_id"])] = find(m["in_reply_to"])
    replied_to = {m["in_reply_to"] for m in messages if m["in_reply_to"]}
    keys: list = []
    for m in messages:
        alone = not m["in_reply_to"] and m["message_id"] not in replied_to
        keys.append(("subject", m["subject"]) if alone and m["subject"] else ("chain", find(m["message_id"])))
    groups: dict = {}
    for m, k in zip(messages, keys):
        groups.setdefault(k, []).append(m)
    return list(groups.values())


def render(groups: list[list[dict]], full: bool, patterns: list, through: int | None, left: int, shown: int) -> list[str]:
    mk = lambda m, k: (history.mask(m[k], m["episode"], patterns) if isinstance(m[k], str) else m[k]) or ""  # noqa: E731 — every printed field is a stored claim
    out = [f"# {BANNER}", f"# {shown} message(s) in {len(groups)} thread(s), oldest first"
           + (f"; through row {through}" if through is not None else "")]
    for g in groups:
        subject = next((mk(m, "subject") for m in g if m["subject"]), "(no subject)")
        out.append(f"\n### {subject}")
        for m in g:
            arrow = "→" if m["direction"] == "outbound" else "←"
            state = "" if m["state"] in ("accepted", "received") else f" [{m['state']}]"
            out.append(f"\n## {m['date']} {arrow} {mk(m, 'peer') or '?'} {mk(m, 'type')} {mk(m, 'message_id')}{state}"
                       + (f" (re {mk(m, 'in_reply_to')})" if m["in_reply_to"] else ""))
            text = mk(m, "content")
            if not full and len(text) > CUT:
                text = text[:CUT] + f"\n… ({len(m['content']) - CUT} more characters: fabric-history --thread {mk(m, 'message_id')} --full)"
            out.append(text.rstrip("\n"))
    if left:
        out.append(f"\n# {left} more message(s) wait for the next pass: run `fabric-reflect done --through {through}` for this one, then `fabric-reflect`")
    elif shown:
        out.append(f"\n# nothing else waits; `fabric-reflect done --through {through}` closes this pass, even when it wrote no memory")
    else:
        out.append("\n# nothing waits since the last pass")
    return out


def cmd_read(conn, owner: str, args, patterns: list) -> int:
    cur = cursor(conn, owner)
    after = cur.get("row", 0)
    window = waiting(conn, after, args.max)
    left = count_waiting(conn, after) - len(window)
    through = window[-1]["row"] if window else None
    groups = group([describe(r) for r in window])
    if args.json:
        mk = lambda m, k: history.mask(m[k], m["episode"], patterns) if isinstance(m[k], str) else m[k]  # noqa: E731
        print(json.dumps({"banner": BANNER, "through": through, "left": left, "threads": [
            [{k: mk(m, k)
              for k in ("date", "direction", "peer", "type", "message_id", "in_reply_to", "subject", "state", "content")}
             for m in g] for g in groups]}, indent=1))
    else:
        print("\n".join(render(groups, args.full, patterns, through, left, len(window))))
    return 0


def cmd_done(conn, owner: str, args) -> int:
    with identity.agent_lock():
        cur = cursor(conn, owner)
        have = cur.get("row", 0)
        row = conn.execute("SELECT rowid, id FROM episodes WHERE source=? AND rowid=?",
                           (episodic.SOURCE, args.through)).fetchone()
        if row is None:
            raise CursorError(f"row {args.through} is not a message of this journal; `fabric-reflect` prints the row to close")
        shown = conn.execute("SELECT COUNT(*) FROM episodes WHERE source=? AND rowid > ? AND rowid <= ?",
                             (episodic.SOURCE, have, row[0])).fetchone()[0]
        if shown > args.max:
            raise CursorError(f"row {args.through} is {shown} messages past the cursor; a pass of --max {args.max} "
                              "never showed that far: give `done` the --max of the pass, or close the row it printed")
        if row is None or row[0] <= have:
            print(f"fabric-reflect: nothing to close; the cursor stays at row {have}")
            return 0
        write_cursor(owner, row[0], row[1])
    print(f"fabric-reflect: pass closed through row {row[0]}")
    return 0


def cmd_status(conn, owner: str, args) -> int:
    cur = cursor(conn, owner)
    n = count_waiting(conn, cur.get("row", 0))
    info = {"cursor_row": cur.get("row", 0), "done_at": cur.get("done_at"), "waiting": n}
    if args.json:
        print(json.dumps(info, indent=1))
    else:
        print(f"cursor: row {info['cursor_row']}" + (f", closed {info['done_at']}" if info["done_at"] else " (no pass closed yet)"))
        print(f"{n} message(s) wait for the next pass")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="fabric-reflect", description=BANNER)
    ap.add_argument("action", nargs="?", choices=("done", "status"))
    ap.add_argument("--max", type=int, default=DEFAULT_MAX)
    ap.add_argument("--through", type=int)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.max < 1:
        ap.error("--max is at least 1")
    if args.action == "done" and args.through is None:
        ap.error("done needs --through ROW, the row the pass printed")
    if args.through is not None and (args.action != "done" or args.through < 1):
        ap.error("--through ROW belongs to `done` and is at least 1")
    try:
        conn = history.open_readonly()
        owner = episodic.own_agent_id()
        patterns = history.credential_patterns() if args.action != "done" else []
        if args.action == "done":
            return cmd_done(conn, owner, args)
        if args.action == "status":
            return cmd_status(conn, owner, args)
        return cmd_read(conn, owner, args, patterns)
    except (episodic.JournalError, CursorError, sqlite3.Error, OSError) as e:
        print(f"fabric-reflect: {e}", file=sys.stderr)
        return 1
    except layout.HygieneError as e:
        # A broken list cannot mask a credential: nothing is shown unmasked.
        print(f"fabric-reflect: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
