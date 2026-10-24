"""tools/fabric/gzcoord/carrier/ledger.py — the shown ledger of
CARRIER-CONTRACT.md §6: what decides that a session sees a message once,
whichever carrier brought it first, with no carrier needed.

`<state>/agents/<login>/gzcoord-shown.jsonl` is the inbox's own file, written by
both inbox paths (the relay's and the carrier's) and by nothing else. Before it
shows a message an inbox path takes an exclusive flock on it and looks the
MESSAGE-ID up; the lines it finds decide:
  none                      show it: append a pending line, show, append the
                            final line (the same without `pending`)
  pending, no final         an inbox path died between the two appends: the
                            message may or may not have reached the session, so
                            it is shown once more, flagged "may repeat", and its
                            final line appended
  a final line              do not show it, with one exception (ADR-064 rule 9):
                            a copy whose verdict is `mismatch`, when the copy
                            shown was the relay's, is shown again, flagged, and
                            recorded `"flagged": true` through the same
                            two-step write; a flagged copy is shown at most once
                            (and a flagged pending-only entry is shown once
                            more, flagged "may repeat")
Each line is one write(); the lock is held from the lookup to the final line
and for no longer: "shows" is writing the message to the session's output, never
anything that waits on the session. The relay's acknowledgement follows the
pending line, so a message the relay no longer holds is a message the ledger
already knows.

A line also carries `h`, a hash of the message's text. MESSAGE-ID alone would
let a different message that reuses a shown id be acknowledged and never shown
(an author may write their own id, and a peer may send a colliding one): lines
count for a message only when they have no `h` (an older line) or the same one.
The same message arrives from both carriers with the same text, so the rule is
unchanged for it.

The ledger is NOT rotated during the dual run (CARRIER-CONTRACT.md §6): a line
dropped while a copy of its MESSAGE-ID can still arrive would show that copy
again, and how long a copy can still arrive is what the parity report measures.

The carrier reads the ledger under LOCK_SH (`final_lines`) to decide what
`unseen` still lists, and never writes it.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Callable

from . import jsonl


def body_hash(content: str) -> str:
    """A message's text, as the ledger tells two messages with one id apart. Line
    endings and trailing space are not part of it: the relay and the carrier may not
    carry them alike."""
    return hashlib.sha256(content.replace("\r\n", "\n").strip().encode("utf-8")).hexdigest()[:32]


@dataclass
class Decision:
    show: bool
    kind: str = "absent"            # absent | repeat | flagged | repeat-flagged | present
    flagged: bool = False           # the copy is the rule 9 re-show
    may_repeat: bool = False        # an earlier showing was interrupted
    of: str | None = None           # the MESSAGE-ID already shown, for a flagged copy
    append_pending: bool = field(default=True, repr=False)


def _lines_for(lines: list[dict], mid: str, h: str = "") -> list[dict]:
    return [x for x in lines if x.get("mid") == mid and (not h or not x.get("h") or x["h"] == h)]


def decide(lines: list[dict], mid: str, via: str, verdict: str, h: str = "") -> Decision:
    """The ledger's rule for one copy, from the lines already there. Pure."""
    mine = _lines_for(lines, mid, h)
    if not mine:
        return Decision(True, "absent")
    finals = [x for x in mine if not x.get("pending")]
    pendings = [x for x in mine if x.get("pending")]
    if not finals:
        return Decision(True, "repeat", may_repeat=True, append_pending=False)
    flagged_done = any(x.get("flagged") for x in finals)
    if verdict == "mismatch" and via == "interweave" and finals[0].get("via") == "relay" and not flagged_done:
        if any(x.get("flagged") for x in pendings):
            return Decision(True, "repeat-flagged", flagged=True, may_repeat=True, of=mid, append_pending=False)
        return Decision(True, "flagged", flagged=True, of=mid)
    return Decision(False, "present")


class Held:
    """The ledger with its exclusive lock held."""

    def __init__(self, path: str, fd: int, iso_now: Callable[[], str]) -> None:
        self.path, self._fd, self._iso = path, fd, iso_now
        self.open_for_show: list[tuple[str, str, bool, str]] = []     # (mid, via, flagged, h) pending, awaiting the final line
        self.lines: list[dict] = self._read()

    def _read(self) -> list[dict]:
        out: list[dict] = []
        size = os.fstat(self._fd).st_size
        data = os.pread(self._fd, size, 0) if size else b""
        for raw in data.split(b"\n"):
            try:
                o = json.loads(raw)
            except ValueError:
                continue
            if isinstance(o, dict) and isinstance(o.get("mid"), str):
                out.append(o)
        return out

    def decide(self, mid: str, via: str, verdict: str, h: str = "") -> Decision:
        # A showing this very lock has begun (a pending line it wrote) is as good as
        # shown for the next copy of the same message in the same pass: both carriers'
        # copies of one message can arrive on one page, and the second must see the first.
        mine = [{"mid": m, "via": v, "t": "", **({"flagged": True} if f else {}), **({"h": hh} if hh else {})}
                for m, v, f, hh in self.open_for_show]
        pend = {(m, v, f, hh) for m, v, f, hh in self.open_for_show}
        lines = [x for x in self.lines
                 if not (x.get("pending") and (x["mid"], x["via"], bool(x.get("flagged")), x.get("h", "")) in pend)]
        return decide(lines + mine, mid, via, verdict, h)

    def _put(self, mid: str, via: str, flagged: bool, pending: bool, h: str = "") -> None:
        line: dict = {"mid": mid, "via": via, "t": self._iso()}
        if h:
            line["h"] = h
        if pending:
            line["pending"] = True
        if flagged:
            line["flagged"] = True
        jsonl.append(self._fd, line)
        self.lines.append(line)

    def pending(self, mid: str, via: str, flagged: bool = False, h: str = "") -> None:
        self._put(mid, via, flagged, True, h)
        self.open_for_show.append((mid, via, flagged, h))

    def final(self, mid: str, via: str, flagged: bool = False, h: str = "") -> None:
        self._put(mid, via, flagged, False, h)

    def finish(self) -> None:
        """The showing was written: the final line for every pending one, then release."""
        try:
            for mid, via, flagged, h in self.open_for_show:
                self.final(mid, via, flagged, h)
        finally:
            self.release()

    def finish_repeat(self, mid: str, via: str, flagged: bool = False, h: str = "") -> None:
        """The final line of a showing that had no pending line of its own (a repeat)."""
        self.open_for_show.append((mid, via, flagged, h))

    def release(self) -> None:
        if self._fd >= 0:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd = -1


class Ledger:
    def __init__(self, path: str, *, iso_now: Callable[[], str]) -> None:
        self.path, self._iso = path, iso_now

    def exclusive(self) -> Held:
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            jsonl.repair(self.path)       # a torn last line would swallow the next append
            return Held(self.path, fd, self._iso)
        except BaseException:
            os.close(fd)
            raise


def final_lines(path: str) -> dict[str, list[dict]]:
    """MESSAGE-ID -> its final lines, read under LOCK_SH, for the carrier's
    `unseen`. A ledger that is not there holds nothing."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except FileNotFoundError:
        return {}
    try:
        fcntl.flock(fd, fcntl.LOCK_SH)
        size = os.fstat(fd).st_size
        data = os.pread(fd, size, 0) if size else b""
    finally:
        os.close(fd)
    out: dict[str, list[dict]] = {}
    for raw in data.split(b"\n"):
        try:
            o = json.loads(raw)
        except ValueError:
            continue
        if isinstance(o, dict) and isinstance(o.get("mid"), str) and not o.get("pending"):
            out.setdefault(o["mid"], []).append(o)
    return out


def settled(finals: list[dict] | None, verdict: str, h: str = "") -> bool:
    """Whether `unseen` stops listing a record: its final line is
    `"via": "interweave"`, or, for an ok copy, any final line for the id (a
    mismatch copy with only the relay's final line is still owed its re-show).
    A final line of a different message that shares the id (another `h`) settles nothing."""
    finals = [x for x in (finals or []) if not h or not x.get("h") or x["h"] == h]
    if not finals:
        return False
    if any(x.get("via") == "interweave" for x in finals):
        return True
    return verdict != "mismatch"
