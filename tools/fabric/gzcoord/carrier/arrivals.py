"""tools/fabric/gzcoord/carrier/arrivals.py — the two files an InterWeave arrival
leaves beside the journal (ADR-064 rules 9, 11); both JSON lines, 0600 in the
account's runtime state.

  gzcoord-arrivals.jsonl  one line per COPY received and addressed to this agent,
                          whichever carrier brought it: {"mid","addressee",
                          "carrier","t","verdict"}; written before the journal
                          collapses the copy, so the parity report can count what
                          the journal's one-row-per-MESSAGE-ID hides. A repeat of a
                          message is another line, by design. Two writers, the
                          carrier and the relay's inbox path: each line is one
                          write() on a descriptor opened O_APPEND, under an
                          exclusive flock. It is the report's evidence and decides
                          nothing about showing.
  interweave/inbox.jsonl  the InterWeave arrivals the journal now holds, for the
                          inbox to pass through the shown ledger (ledger.py): {"mid",
                          "content","ts","sender","verdict"}, in arrival order, first
                          copy only; `sender` is the roster's address for the PeerId
                          that sent it (what the inbox shows), not its FROM.

What the session sees is decided by the ledger, not here: `unseen` lists a record
again on every call until the ledger holds its final line, so an inbox that dies
after asking loses nothing.
"""
from __future__ import annotations

import fcntl
import json
import os
import sys
import threading
from typing import Callable

from . import jsonl, ledger

def _read(path: str) -> list[dict]:
    out: list[dict] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue   # a torn last line from a crash; nothing after it is complete
                if isinstance(o, dict):
                    out.append(o)
    except FileNotFoundError:
        pass
    return out


def _rewrite(path: str, records: list[dict]) -> None:
    tmp = path + ".new"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        for r in records:
            jsonl.write_all(fd, (json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


class ArrivalLog:
    def __init__(self, path: str, *, iso_now: Callable[[], str]) -> None:
        self.path, self._iso = path, iso_now
        self._lock = threading.Lock()

    def append(self, mid: str, addressee: str, carrier: str, verdict: str) -> None:
        self._append({"mid": mid, "addressee": addressee, "carrier": carrier, "t": self._iso(), "verdict": verdict})

    def _append(self, line: dict) -> None:
        with self._lock:
            os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                jsonl.repair(self.path)      # under the lock: a torn line from a crashed writer would swallow this one
                jsonl.append(fd, line)
            finally:
                os.close(fd)


class WatchLog(ArrivalLog):
    """gzcoord-watch.jsonl: when a watch (gzcoord-inbox --follow or --until-delivery) started and how it ended, one line each:
    {"t","event":"start","pid"} and {"t","event":"end","pid","reason","code"}. The relay-outage drill (ADR-064 rule 11 / Gate 1 item 3)
    asks whether a watch was restarted inside the outage and whether one gave up after its 15 minutes, and neither the shown
    ledger nor the acknowledgement log says: the give-up (exit 5) leaves only a marker the next fetch deletes. A watch the
    kernel ends (SIGKILL, a host crash), or that leaves by an interrupt or an exception inside the process (a closed stdout,
    Ctrl-C), writes no end line; a start with no end of its pid is one of those, or a watch still running,
    and the report says so rather than naming a reason it does not have."""

    END_REASONS = ("delivery", "quiet", "session-ended", "gave-up", "token-refused", "journal-held")

    def append_start(self, pid: int) -> None:
        self._append({"t": self._iso(), "event": "start", "pid": pid})

    def append_end(self, pid: int, reason: str, code: int) -> None:
        assert reason in self.END_REASONS, reason
        self._append({"t": self._iso(), "event": "end", "pid": pid, "reason": reason, "code": code})


class MirrorLog(ArrivalLog):
    """gzcoord-mirror.jsonl, in the SENDER's state beside gzcoord-sent.jsonl: one line for each send the InterWeave carrier
    did not accept: {"mid","t","outcome","reason","as"}, `outcome` one of OUTCOMES, `as` the carrier's place in that send: "mirror"
    (a relay-record send's second copy; the relay's record then holds the message alone) or "primary" (the transport of record,
    carrier-record and carrier-only: the send exited 3 and, in carrier-only, no relay copy is left to find). A line without `as`
    was written before the field and is a mirror's. The parity report (ADR-064 rule 11) sees a pair with no InterWeave copy and
    no sender record; before this log the reason was a stderr line of a send nobody kept. A send the carrier accepted leaves no
    line here: it has a delivery row in the carrier's own outbox. The log is bounded (a sender with no carrier at all writes a
    line per send). A primary is never "not-carried": a roster without a recipient is a refusal that recorded nothing, "failed"."""

    OUTCOMES = ("absent", "not-carried", "failed", "no-answer")
    ROLES = ("primary", "mirror")
    MAX_BYTES = 256 * 1024
    REASON_MAX = 200

    def append_refused(self, mid: str, outcome: str, reason: str, role: str = "primary") -> None:
        assert outcome in self.OUTCOMES, outcome
        assert role in self.ROLES, role
        self._append({"mid": mid, "t": self._iso(), "outcome": outcome, "reason": " ".join(reason.split())[:self.REASON_MAX], "as": role})

    def _append(self, line: dict) -> None:
        # The lock is a file of its own, never the log: the trim replaces the log by rename, and a lock on the replaced inode would
        # let a second appender write into a file that no longer has a name (a lost line, silently).
        with self._lock:
            os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
            lock = os.open(self.path + ".lock", os.O_WRONLY | os.O_CREAT, 0o600)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX)
                jsonl.repair(self.path)
                jsonl.append_path(self.path, line)
                if os.stat(self.path).st_size > self.MAX_BYTES:
                    try:
                        self._trim()
                    except OSError as e:
                        # The line is written; only the bound failed (a full disk): said as that, never as an unwritten line.
                        print(f"gzcoord: the mirror refusal log was written but could not be trimmed ({e.strerror or e})", file=sys.stderr)
            finally:
                os.close(lock)


    def _trim(self) -> None:
        # An undecodable byte is replaced: a line it breaks is dropped, one where it sits inside a string is kept with U+FFFD, and the
        # trim bounds the log either way (it would otherwise stay over its bound for good).
        rows: list[dict] = []
        with open(self.path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if isinstance(o, dict):
                    rows.append(o)
        _rewrite(self.path, rows[len(rows) // 2:])


class Spool:
    """The arrivals the journal holds, as `unseen` lists them. `ledger_path` is the
    inbox's shown ledger, which the carrier only reads."""

    def __init__(self, directory: str, ledger_path: str, *, iso_now: Callable[[], str]) -> None:
        os.makedirs(directory, mode=0o700, exist_ok=True)
        self._iso, self._ledger = iso_now, ledger_path
        self._path = os.path.join(directory, "inbox.jsonl")
        jsonl.repair(self._path)
        self._lock = threading.Lock()
        records = _read(self._path)
        finals = ledger.final_lines(ledger_path)
        # Only a settled record leaves: an arrival nobody has shown is listed until
        # someone has, however old (CARRIER-CONTRACT.md §6: no order loses a message).
        self.records = [r for r in records if not self._settled(finals, r)]
        if len(self.records) != len(records):
            _rewrite(self._path, self.records)
        self._kept = {(r["mid"], r.get("h", "")) for r in self.records}

    @staticmethod
    def _settled(finals: dict, r: dict) -> bool:
        return ledger.settled(finals.get(r["mid"]), r["verdict"], r.get("h", ""))

    def keep(self, mid: str, content: str, ts: str, verdict: str, sender: str) -> None:
        with self._lock:
            h = ledger.body_hash(content)
            if (mid, h) in self._kept:
                return        # the same message again; another message under the same id is another record
            rec = {"mid": mid, "content": content, "ts": ts, "verdict": verdict, "sender": sender,
                   "h": h}
            jsonl.append_path(self._path, rec)
            self.records.append(rec)
            self._kept.add((mid, h))

    def unseen(self) -> list[dict]:
        """The records the ledger does not yet settle, in arrival order. Settled
        ones leave memory (and the file at the next open)."""
        finals = ledger.final_lines(self._ledger)
        with self._lock:
            self.records = [r for r in self.records if not self._settled(finals, r)]
            return [{"content": r["content"], "ts": r["ts"], "seq": None, "message_id": r["mid"],
                     "verdict": r["verdict"], "sender": r["sender"]} for r in self.records]
