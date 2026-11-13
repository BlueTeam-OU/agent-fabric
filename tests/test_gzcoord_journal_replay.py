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
    check("the journal was only read: no replay or history changed any journal file (db, -wal, -shm)",
          set(journal_files(w)) >= set(before) and all(journal_files(w).get(k) == v for k, v in before.items() if not k.endswith("-shm")),
          f"{before}\n{journal_files(w)}")
    check("the carrier's name is the one the journal row holds", carrier_name == "interweave", str(carrier_name))

    # a relay seq is answered from the relay while one is configured, with the new --json fields
    w2 = C.World([], carrier_records=None)
    w2.history = [C.relay_rec(4)]
    r = run(w2, "--replay", "4", "--json")
    j = json.loads(r.stdout) if r.stdout.strip() else {}
    check("a relay seq is the relay's: exit 0, --json carries carrier claude-bridge and sender_verified false",
          r.returncode == 0 and j.get("carrier") == "claude-bridge" and j.get("sender_verified") is False and j.get("seq") == 4, r.stdout + r.stderr)
    r = run(w2, "--replay", C.mid(4))
    check("a MESSAGE-ID the journal lacks falls on to the relay's history, as before",
          r.returncode == 0 and "relay seq 4" in r.stdout and "subject-4" in r.stdout, r.stdout + r.stderr)
    check("the relay's carrier name here is the journal's default carrier", "claude-bridge" == episodic.DEFAULT_CARRIER)
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
