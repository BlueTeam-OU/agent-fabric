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

import calendar
import fcntl
import json
import os
import threading
import time
from typing import Callable

from . import jsonl, ledger

SPOOL_KEPT_DAYS = 14


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
        line = {"mid": mid, "addressee": addressee, "carrier": carrier, "t": self._iso(), "verdict": verdict}
        with self._lock:
            os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                jsonl.repair(self.path)      # under the lock: a torn line from a crashed writer would swallow this one
                jsonl.append(fd, line)
            finally:
                os.close(fd)


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
        self.records = [r for r in records if not self._stale(r) and not ledger.settled(finals.get(r["mid"]), r["verdict"])]
        if len(self.records) != len(records):
            _rewrite(self._path, self.records)
        self._kept = {r["mid"] for r in self.records}

    def _stale(self, r: dict) -> bool:
        try:
            made = calendar.timegm(time.strptime(str(r["ts"]), "%Y-%m-%dT%H:%M:%SZ"))
            now = calendar.timegm(time.strptime(self._iso(), "%Y-%m-%dT%H:%M:%SZ"))
        except (ValueError, KeyError):
            return False        # a clock or a stamp that does not parse prunes nothing
        return now - made > SPOOL_KEPT_DAYS * 86400

    def keep(self, mid: str, content: str, ts: str, verdict: str, sender: str) -> None:
        with self._lock:
            if mid in self._kept:
                return
            rec = {"mid": mid, "content": content, "ts": ts, "verdict": verdict, "sender": sender}
            jsonl.append_path(self._path, rec)
            self.records.append(rec)
            self._kept.add(mid)

    def unseen(self) -> list[dict]:
        """The records the ledger does not yet settle, in arrival order. Settled
        ones leave memory (and the file at the next open)."""
        finals = ledger.final_lines(self._ledger)
        with self._lock:
            self.records = [r for r in self.records if not ledger.settled(finals.get(r["mid"]), r["verdict"])]
            return [{"content": r["content"], "ts": r["ts"], "seq": None, "message_id": r["mid"],
                     "verdict": r["verdict"], "sender": r["sender"]} for r in self.records]
