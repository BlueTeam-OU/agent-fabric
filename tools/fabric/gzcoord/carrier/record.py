"""tools/fabric/gzcoord/carrier/record.py — the carrier's own delivery record
(ADR-064 rule 7), per recipient, in the account's runtime state.

CONTRACT. One append-only JSON-lines file, `deliveries.jsonl`, 0600 in a 0700
directory, one writer (the carrier process; an exclusive flock refuses a
second). A delivery is (MESSAGE-ID, recipient login). Its events:
  queued   MESSAGE-ID, recipient, the transport message_ids (one per payload,
           kept across every retry: the receiving daemon collapses a retry
           inside its window, ADR-0019), the message text
  posted   the daemon accepted every payload (queue admission, not delivery)
  blocked  a refusal no retry mends (the code is kept; the delivery stays
           pending: a send is never given up without its operator)
  receipt  the recipient's carrier answered after its journal append
A delivery is DONE on its receipt and not before. Each fsync'd event is on
disk before the carrier acts on it, so a carrier that dies between a post and
its record resends under the same transport ids and the receiving carrier
collapses it by MESSAGE-ID (and answers a receipt again). On open, DONE
deliveries move to `delivered.jsonl` (no text) so the file stays the size of
what is outstanding; the move is a rewrite by atomic replace, delivered.jsonl
first, so an interruption between the two repeats the move and a duplicate
line is skipped by key.

The retry schedule is 1 s doubling to 5 min, with no count after which a send
is given up (InterWeave AUTOMATED-CLIENT.md §3's known-good shape). Time is an
input: every method that needs it takes `now` (seconds, any monotonic origin).
"""
from __future__ import annotations

import fcntl
import json
import os
import secrets
import tempfile
from dataclasses import dataclass, field
from typing import Callable

BACKOFF_FIRST = 1.0
BACKOFF_CAP = 300.0


class RecordError(Exception):
    pass


def backoff(attempts: int) -> float:
    return min(BACKOFF_FIRST * (2 ** max(attempts - 1, 0)), BACKOFF_CAP)


@dataclass
class Delivery:
    mid: str
    to: str
    tmids: list[str]
    text: str
    queued_at: str
    posted: bool = False
    blocked: str | None = None
    receipt_at: str | None = None
    attempts: int = 0
    next_at: float = 0.0           # in memory only: a restart retries at once
    key: tuple[str, str] = field(init=False)

    def __post_init__(self) -> None:
        self.key = (self.mid, self.to)


class Outbox:
    def __init__(self, directory: str, *, iso_now: Callable[[], str]) -> None:
        os.makedirs(directory, mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)
        self.directory = directory
        self._iso = iso_now
        self.path = os.path.join(directory, "deliveries.jsonl")
        self.done_path = os.path.join(directory, "delivered.jsonl")
        self._fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self._fd)
            raise RecordError(f"{self.path} is held by another carrier") from None
        self.deliveries: dict[tuple[str, str], Delivery] = {}
        self._load()

    # -- storage ---------------------------------------------------------
    def _append(self, event: dict) -> None:
        os.write(self._fd, (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
        os.fsync(self._fd)

    def _load(self) -> None:
        with open(self.path, "rb") as fh:
            lines = fh.read().split(b"\n")
        for n, raw in enumerate(lines):
            if not raw:
                continue
            try:
                ev = json.loads(raw)
                self._apply(ev)
            except (ValueError, KeyError, TypeError) as e:
                # A torn last line is the one a crash can leave; anywhere else the
                # record is damaged and a guess would lose or duplicate a send.
                if n == len(lines) - 2 or (n == len(lines) - 1):
                    continue
                raise RecordError(f"{self.path} line {n + 1} is damaged: {e}") from e
        self._compact()

    def _apply(self, ev: dict) -> None:
        key = (ev["mid"], ev["to"])
        kind = ev["e"]
        if kind == "queued":
            self.deliveries[key] = Delivery(ev["mid"], ev["to"], list(ev["tmids"]), ev["text"], ev["t"])
            return
        d = self.deliveries[key]
        if kind == "posted":
            d.posted, d.blocked = True, None
        elif kind == "blocked":
            d.blocked = str(ev["code"])
        elif kind == "receipt":
            d.receipt_at = ev["t"]
        else:
            raise ValueError(f"unknown event {kind!r}")

    def _compact(self) -> None:
        done = [d for d in self.deliveries.values() if d.receipt_at]
        if not done:
            return
        have: set[tuple[str, str]] = set()
        if os.path.exists(self.done_path):
            with open(self.done_path, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        o = json.loads(line)
                        have.add((o["mid"], o["to"]))
                    except (ValueError, KeyError):
                        continue
        fd = os.open(self.done_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            for d in done:
                if d.key not in have:
                    os.write(fd, (json.dumps({"mid": d.mid, "to": d.to, "queued": d.queued_at,
                                              "receipt": d.receipt_at}, sort_keys=True) + "\n").encode())
            os.fsync(fd)
        finally:
            os.close(fd)
        for d in done:
            del self.deliveries[d.key]
        tmp = tempfile.NamedTemporaryFile("wb", dir=self.directory, prefix=".deliveries.", delete=False)
        try:
            for d in self.deliveries.values():
                for ev in self._events_of(d):
                    tmp.write((json.dumps(ev, sort_keys=True, separators=(",", ":")) + "\n").encode())
            tmp.flush()
            os.fsync(tmp.fileno())
            os.chmod(tmp.name, 0o600)
            tmp.close()
            # The held flock is on the old inode; take the new file's before the
            # old is unlinked, so there is no moment two carriers could both hold one.
            new_fd = os.open(tmp.name, os.O_RDWR | os.O_APPEND)
            fcntl.flock(new_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.replace(tmp.name, self.path)
            os.close(self._fd)
            self._fd = new_fd
        except BaseException:
            tmp.close()
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)
            raise

    @staticmethod
    def _events_of(d: Delivery) -> list[dict]:
        evs = [{"e": "queued", "mid": d.mid, "to": d.to, "tmids": d.tmids, "text": d.text, "t": d.queued_at}]
        if d.posted:
            evs.append({"e": "posted", "mid": d.mid, "to": d.to, "t": d.queued_at})
        if d.blocked:
            evs.append({"e": "blocked", "mid": d.mid, "to": d.to, "code": d.blocked, "t": d.queued_at})
        return evs

    def close(self) -> None:
        os.close(self._fd)

    # -- the record ------------------------------------------------------
    def queue(self, mid: str, to: str, text: str, payload_count: int) -> Delivery:
        """The delivery of `mid` to `to`, made if new. The same message again
        is the same delivery (its transport ids kept); another body under a
        known id is refused, as the journal refuses it (ADR-041 rule 5)."""
        d = self.deliveries.get((mid, to))
        if d is not None:
            if d.text != text:
                raise RecordError(f"MESSAGE-ID {mid} is already queued to {to} with another body")
            return d
        ev = {"e": "queued", "mid": mid, "to": to, "text": text, "t": self._iso(),
              "tmids": [secrets.token_hex(16) for _ in range(payload_count)]}
        self._append(ev)
        self._apply(ev)
        return self.deliveries[(mid, to)]

    def posted(self, d: Delivery) -> None:
        self._append({"e": "posted", "mid": d.mid, "to": d.to, "t": self._iso()})
        d.posted, d.blocked = True, None

    def blocked(self, d: Delivery, code: str) -> None:
        if d.blocked != code:
            self._append({"e": "blocked", "mid": d.mid, "to": d.to, "code": code, "t": self._iso()})
        d.blocked = code

    def receipt(self, mid: str, to: str) -> bool:
        """The recipient's receipt. False for one that names nothing this
        carrier sent (or already settled): ignored, never an error."""
        d = self.deliveries.get((mid, to))
        if d is None or d.receipt_at:
            return False
        t = self._iso()
        self._append({"e": "receipt", "mid": mid, "to": to, "t": t})
        d.receipt_at = t
        return True

    def retry_after(self, d: Delivery, now: float) -> None:
        d.attempts += 1
        d.next_at = now + backoff(d.attempts)

    def outstanding(self) -> list[Delivery]:
        return [d for d in self.deliveries.values() if not d.receipt_at]

    def due(self, now: float) -> list[Delivery]:
        return [d for d in self.outstanding() if d.next_at <= now]
