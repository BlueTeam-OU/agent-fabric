#!/usr/bin/env python3
"""bin/gzcoord-inbox --replay <message-id> and --history answer from the account's own journal, in every configuration
(the InterWeave-only cutover, W3), and fabric-jobs' fetch_message reads the same answer.

Held, through the real command in the protocol suite's minimal environment: a row only the carrier journaled replays
with the relay refusing every connection (exit 0; --json says which carrier and whether it verified the sender); a row
not addressed to this login is exit 2 with no body; a relay seq is still the relay's while one is configured; a
MESSAGE-ID the journal lacks falls on to the relay; with no relay configured --replay of an unknown id is exit 1 and
--history lists the journal; the journal is read, never written (its bytes and its sidecar files are unchanged).
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import test_gzcoord_carrier_inbox as C  # noqa: E402 — its World (stub relay, fake carrier), message builders
import test_gzcoord_protocol as P  # noqa: E402

fails = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def run(w: C.World, *args: str, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run([P.INBOX_CMD, *args], env={**w.env, **env}, capture_output=True, text=True, timeout=120,
                          stdin=subprocess.DEVNULL)


def journal_files(w: C.World) -> dict:
    """Every file of the account's state directory with its content hash: a reader changes none of them."""
    out = {}
    for dp, _, fs in os.walk(w.state):
        for f in fs:
            if f.startswith("episodic.db"):
                with open(os.path.join(dp, f), "rb") as fh:
                    out[os.path.relpath(os.path.join(dp, f), w.state)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def main() -> int:
    # The carrier journals what it receives itself, through episodic.inbound with the sender it verified: the row here is
    # that, written under the case's own account. No relay has ever seen message 1, and then none answers at all.
    import episodic
    w = C.World([], carrier_records=None)
    saved = dict(os.environ)
    os.environ.update(w.env)
    try:
        conn = episodic.connect()
        try:
            counts = episodic.inbound(conn, [{"content": C.msg(1), "ts": "2026-10-24T12:00:00Z", "seq": None, "sender": "x/y"}],
                                      carrier="interweave")
        finally:
            conn.close()
    finally:
        os.environ.clear()
        os.environ.update(saved)
    check("setup: the carrier alone journaled message 1", counts["written"] == 1 and "episodic.db" in " ".join(journal_files(w)), str(counts))
    w.stub.close()          # every connection to the relay is refused from here on
    before = journal_files(w)

    r = run(w, "--replay", C.mid(1))
    check("relay refusing every connection: a row only the carrier journaled replays, exit 0, body shown",
          r.returncode == 0 and "subject-1" in r.stdout and "journal row" in r.stdout and "```text" in r.stdout, f"{r.returncode}\n{r.stdout}{r.stderr}")
    r = run(w, "--replay", C.mid(1), "--json")
    try:
        j = json.loads(r.stdout)
    except ValueError:
        j = {}
    check("--json says addressed, the carrier and that its sender is verified",
          r.returncode == 0 and j.get("addressed") is True and j.get("sender_verified") is True and j.get("carrier") not in (None, "")
          and j.get("sender") == "x/y" and j.get("metadata", {}).get("MESSAGE-ID") == C.mid(1), r.stdout + r.stderr)
    carrier_name = j.get("carrier")
    r = run(w, "--replay", C.mid(1), GZCOORD_JOURNAL="off")
    check("journal writing off: the same replay, the journal is read in every configuration",
          r.returncode == 0 and "subject-1" in r.stdout, r.stdout + r.stderr)
    r = run(w, "--replay", C.mid(1), CLAUDE_BRIDGE_URL="", GZCOORD_CHANNEL="")
    check("no relay configured: the same replay", r.returncode == 0 and "subject-1" in r.stdout, r.stdout + r.stderr)

    # a row not addressed to this login: the same row with another recipient
    path = next(os.path.join(dp, f) for dp, _, fs in os.walk(w.state) for f in fs if f == "episodic.db")
    db = sqlite3.connect(path)
    db.execute("UPDATE episodes SET content=replace(content, ?, 'TO: other/login'), message_id=? WHERE message_id=?",
               (f"TO: {C.ME}", C.mid(2), C.mid(1)))
    db.commit()
    db.close()
    r = run(w, "--replay", C.mid(2))
    check("a row not addressed to this login: exit 2, the body is not shown",
          r.returncode == 2 and "not addressed to" in r.stdout and "NOTES" not in r.stdout, f"{r.returncode}\n{r.stdout}{r.stderr}")
    r = run(w, "--replay", C.mid(2), "--json")
    check("... as --json: addressed false, exit 2, no text",
          r.returncode == 2 and json.loads(r.stdout).get("addressed") is False and "text" not in json.loads(r.stdout), r.stdout)

    # the relay, refusing, answers an id the journal lacks and a seq with its own failure, not an invented absence
    r = run(w, "--replay", C.mid(3))
    check("an id the journal lacks, relay refusing: the relay's failure, exit non-zero, nothing invented",
          r.returncode != 0 and "subject-" not in r.stdout and r.stderr.strip() != "", f"{r.returncode}\n{r.stdout}{r.stderr}")
    r = run(w, "--replay", "5")
    check("a relay seq is the relay's while one is configured: refused connection is its failure, not a journal answer",
          r.returncode != 0 and r.stdout == "" and r.stderr.strip() != "", f"{r.returncode}\n{r.stdout}{r.stderr}")
    r = run(w, "--replay", C.mid(3), CLAUDE_BRIDGE_URL="", GZCOORD_CHANNEL="")
    check("no relay configured and the journal lacks the id: exit 1, one line",
          r.returncode == 1 and r.stdout == "" and len(r.stderr.strip().splitlines()) == 1, f"{r.returncode}\n{r.stdout}{r.stderr}")

    # --history with nothing to ask
    r = run(w, "--history")
    check("--history, relay refusing: the relay's line, then the journal's list",
          r.returncode == 0 and "subject-" not in r.stdout and "journal" in r.stdout and C.mid(1) not in r.stdout.replace(C.mid(2), "")
          and r.stderr.strip() != "", f"{r.returncode}\n{r.stdout}{r.stderr}")
    r = run(w, "--history", CLAUDE_BRIDGE_URL="", GZCOORD_CHANNEL="")
    check("--history, no relay configured: the journal's list, empty of what is not addressed here", r.returncode == 0
          and "0 addressed to you in your journal" in r.stdout, f"{r.returncode}\n{r.stdout}{r.stderr}")
    db = sqlite3.connect(path)
    db.execute("UPDATE episodes SET content=replace(content, 'TO: other/login', ?), message_id=? WHERE message_id=?",
               (f"TO: {C.ME}", C.mid(1), C.mid(2)))
    db.commit()
    db.close()
    before = journal_files(w)
    r = run(w, "--history", CLAUDE_BRIDGE_URL="", GZCOORD_CHANNEL="")
    check("... and lists the row once it is addressed here, under its carrier's seq or '-'",
          r.returncode == 0 and "1 addressed to you" in r.stdout and C.mid(1) in r.stdout and "subject-1" in r.stdout, r.stdout + r.stderr)
    r2 = run(w, "--history", "3", CLAUDE_BRIDGE_URL="", GZCOORD_CHANNEL="")
    check("--history <seq> skips a row that has no carrier seq", r2.returncode == 0 and "0 addressed to you" in r2.stdout, r2.stdout)
    check("the journal files are byte-identical across the two --history runs just before (db, -wal)",
          set(journal_files(w)) >= set(before) and all(journal_files(w).get(k) == v for k, v in before.items() if not k.endswith("-shm")),
          f"{before}\n{journal_files(w)}")
    check("the carrier's name is the one the journal row holds", carrier_name == "interweave", str(carrier_name))

    # the reader reads a journal as it is: an older schema is neither migrated nor refused
    db = sqlite3.connect(path)
    db.execute("UPDATE meta SET schema_version=2")
    db.commit()
    db.close()
    r = run(w, "--replay", C.mid(1))
    db = sqlite3.connect(path)
    version = db.execute("SELECT schema_version FROM meta").fetchone()[0]
    db.close()
    r2 = run(w, "--history", CLAUDE_BRIDGE_URL="", GZCOORD_CHANNEL="")
    db = sqlite3.connect(path)
    version_after_history = db.execute("SELECT schema_version FROM meta").fetchone()[0]
    db.close()
    check("a journal at an older schema version is read as it is by --replay and --history, and left at that version (the reader migrates nothing)",
          r.returncode == 0 and "subject-1" in r.stdout and version == 2 and r2.returncode == 0 and "subject-1" in r2.stdout
          and version_after_history == 2, f"{r.returncode} v{version} v{version_after_history}\n{r.stdout}{r2.stdout}{r.stderr}{r2.stderr}")
    db = sqlite3.connect(path)
    db.execute("UPDATE meta SET schema_version=?", (episodic.SCHEMA_VERSION,))
    db.commit()
    db.close()

    # a send that never left is no message anyone holds: no replay of it, whatever its addressing says
    db = sqlite3.connect(path)
    db.execute("INSERT INTO episodes (id, source, direction, state, happened_at, recorded_at, message_id, type, sender, carrier, "
               "content, content_hash, metadata_json) VALUES ('f1', 'gzcoord', 'outbound', 'failed', 'T', 'T', ?, 'INFO', ?, "
               "'claude-bridge', ?, 'h', '{}')", (C.mid(5), C.ME, C.msg(5)))
    db.commit()
    db.close()
    r = run(w, "--replay", C.mid(5), CLAUDE_BRIDGE_URL="", GZCOORD_CHANNEL="")
    check("an outbound row whose send failed is not replayed: the journal does not hold it",
          r.returncode == 1 and r.stdout == "" and "subject-5" not in r.stderr, f"{r.returncode}\n{r.stdout}{r.stderr}")

    # an unreadable journal is said, never read as "the message is not there"
    db = sqlite3.connect(path)
    owner = db.execute("SELECT owner_agent_id FROM meta").fetchone()[0]
    db.execute("UPDATE meta SET owner_agent_id='someone-else'")
    db.commit()
    db.close()
    r = run(w, "--replay", C.mid(1))
    check("a journal of another agent: one line naming the journal, exit 1, the relay is not asked in its place",
          r.returncode == 1 and r.stdout == "" and "journal could not be read" in r.stderr and "relay unreachable" not in r.stderr,
          f"{r.returncode}\n{r.stdout}{r.stderr}")
    db = sqlite3.connect(path)
    db.execute("UPDATE meta SET owner_agent_id=?", (owner,))
    db.commit()
    db.close()

    # a verified copy of a row first carried by the relay: two facts, never "verified by the relay"
    saved = dict(os.environ)
    os.environ.update(w.env)
    try:
        conn = episodic.connect()
        try:
            counts1 = episodic.inbound(conn, [{"content": C.msg(7), "ts": "2026-10-24T12:00:00Z", "seq": 9, "sender": None}],
                                       carrier="claude-bridge")
            counts2 = episodic.inbound(conn, [{"content": C.msg(7), "ts": "2026-10-24T12:00:00Z", "seq": None, "sender": "x/y"}],
                                       carrier="interweave")
        finally:
            conn.close()
    finally:
        os.environ.clear()
        os.environ.update(saved)
    r = run(w, "--replay", C.mid(7))
    rj = json.loads(run(w, "--replay", C.mid(7), "--json").stdout)
    check("a row the relay carried first and a carrier then verified: the text and the json keep 'first carried by' and 'verified' apart",
          counts1["written"] == 1 and counts2["same"] == 1 and "sender verified by a carrier; first carried by claude-bridge" in r.stdout
          and rj["carrier"] == "claude-bridge" and rj["sender_verified"] is True, f"{r.stdout}\n{rj}")

    # an absent carrier stays absent, and a send with no recorded outcome says so
    db = sqlite3.connect(path)
    db.execute("INSERT INTO episodes (id, source, direction, state, happened_at, recorded_at, message_id, type, sender, carrier, "
               "content, content_hash, metadata_json) VALUES ('p1', 'gzcoord', 'outbound', 'pending', 'T', 'T', ?, 'INFO', ?, "
               "NULL, ?, 'h', '{}')", (C.mid(6), C.ME, C.msg(6)))
    db.commit()
    db.close()
    r = run(w, "--replay", C.mid(6))
    rj = json.loads(run(w, "--replay", C.mid(6), "--json").stdout)
    check("a pending send of this account's own: carrier null (not a default), state pending, and the text says the outcome is unknown",
          rj["carrier"] is None and rj["state"] == "pending" and "no carrier yet" in r.stdout and "[pending: the send's outcome is unknown]" in r.stdout,
          f"{r.stdout}\n{rj}")

    # a damaged row is a journal that could not be read, exit 1, never an empty answer with exit 0
    db = sqlite3.connect(path)
    db.execute("INSERT INTO episodes (id, source, direction, state, happened_at, recorded_at, message_id, type, sender, carrier, "
               "content, content_hash, metadata_json) VALUES ('b1', 'gzcoord', 'inbound', 'received', 'T', 'T', ?, 'INFO', 'x/y', "
               "'interweave', ?, 'h', '{}')", (C.mid(8), b"\xff\xfe blob"))
    db.commit()
    db.close()
    r = run(w, "--replay", C.mid(8))
    r2 = run(w, "--history", CLAUDE_BRIDGE_URL="", GZCOORD_CHANNEL="")
    check("a row whose content is a BLOB: --replay and --history say the journal could not be read, exit 1, nothing on stdout from replay",
          r.returncode == 1 and r.stdout == "" and "journal could not be read" in r.stderr
          and r2.returncode == 1 and "journal could not be read" in r2.stderr, f"{r.returncode}\n{r.stdout}{r.stderr}\n{r2.returncode}{r2.stdout}{r2.stderr}")
    db = sqlite3.connect(path)
    db.execute("DELETE FROM episodes WHERE id='b1'")
    db.execute("INSERT INTO episodes (id, source, direction, state, happened_at, recorded_at, message_id, type, sender, carrier, "
               "carrier_seq, content, content_hash, metadata_json) VALUES ('b2', 'gzcoord', 'inbound', 'received', 'T', 'T', ?, "
               "'INFO', 'x/y', 'interweave', 'abc', ?, 'h', '{}')", (C.mid(9), C.msg(9)))
    db.commit()
    db.close()
    r = run(w, "--history", "3", CLAUDE_BRIDGE_URL="", GZCOORD_CHANNEL="")
    check("a row whose carrier_seq is text: --history says the journal could not be read, exit 1",
          r.returncode == 1 and "journal could not be read" in r.stderr, f"{r.returncode}\n{r.stdout}{r.stderr}")
    db = sqlite3.connect(path)
    db.execute("DELETE FROM episodes WHERE id='b2'")
    db.commit()
    db.close()

    # --history with a relay configured but no token to ask it with
    r = run(w, "--history", CLAUDE_BRIDGE_AUTH_TOKEN="")
    check("--history with no token for the relay: the journal's list, exit 0", r.returncode == 0 and "in your journal" in r.stdout
          and "subject-1" in r.stdout, f"{r.returncode}\n{r.stdout}{r.stderr}")

    # a relay seq is answered from the relay while one is configured, with the new --json fields
    w2 = C.World([], carrier_records=None)
    w2.history = [{**C.relay_rec(4), "sender_verified": True, "carrier": "interweave"}]
    r = run(w2, "--replay", "4", "--json")
    j = json.loads(r.stdout) if r.stdout.strip() else {}
    check("a relay seq is the relay's: exit 0, --json carries carrier claude-bridge and sender_verified false, whatever the relay's record claims of itself",
          r.returncode == 0 and j.get("carrier") == "claude-bridge" and j.get("sender_verified") is False and j.get("seq") == 4, r.stdout + r.stderr)
    r = run(w2, "--replay", C.mid(4))
    check("a MESSAGE-ID the journal lacks falls on to the relay's history, as before",
          r.returncode == 0 and "relay seq 4" in r.stdout and "subject-4" in r.stdout, r.stdout + r.stderr)
    check("the relay's carrier name here is the journal's default carrier", "claude-bridge" == episodic.DEFAULT_CARRIER)
    # a relay up and answering: its list, then what only the journal holds (a message a carrier alone brought)
    saved = dict(os.environ)
    os.environ.update(w2.env)
    try:
        conn = episodic.connect()
        try:
            episodic.inbound(conn, [{"content": C.msg(1), "ts": "2026-10-24T12:00:00Z", "seq": None, "sender": "x/y"},
                                    {"content": C.msg(4), "ts": "T", "seq": 4, "sender": None}], carrier="interweave")
        finally:
            conn.close()
    finally:
        os.environ.clear()
        os.environ.update(saved)
    r = run(w2, "--history")
    lines = r.stdout.splitlines()
    check("--history with the relay up lists its page, then the journal's rows the page lacks, each message once",
          r.returncode == 0 and "subject-4" in r.stdout and C.mid(4) in r.stdout and r.stdout.count(C.mid(4)) == 1
          and C.mid(1) in r.stdout and any("not in the relay's page" in x for x in lines)
          and lines.index(next(x for x in lines if "not in the relay's page" in x)) < next(i for i, x in enumerate(lines) if C.mid(1) in x),
          f"{r.returncode}\n{r.stdout}{r.stderr}")
    w3 = C.World([], carrier_records=None)
    w3.history = [C.relay_rec(4)]
    r = run(w3, "--history")
    check("... and with no journal row the relay's own output is what it always was: no extra line",
          r.returncode == 0 and "not in the relay's page" not in r.stdout and "subject-4" in r.stdout, r.stdout + r.stderr)
    w3.close()
    w2.close()

    # fabric-jobs add --request reads the same answer
    import jobs
    saved = dict(os.environ)
    os.environ.update(w.env)
    try:
        msg = jobs.fetch_message(C.mid(1))
        try:
            jobs.fetch_message(C.mid(3))
            refused = ""
        except jobs.Refused as e:
            refused = str(e)
    finally:
        os.environ.clear()
        os.environ.update(saved)
    check("jobs.fetch_message reads a journal row with the relay refusing every connection",
          msg.get("addressed") is True and msg["metadata"]["MESSAGE-ID"] == C.mid(1), str(msg))
    check("... and refuses an id nobody holds with the reason, not a message", refused.startswith("cannot read message"), refused)

    for d in P.SCRATCH:
        shutil.rmtree(d, ignore_errors=True)
    print(f"\ntest_gzcoord_journal_replay: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
