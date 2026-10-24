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

The carrier reads the ledger under LOCK_SH (`final_lines`) to decide what
`unseen` still lists, and never writes it.
"""
from __future__ import annotations

import fcntl
import json
import os
import time
from dataclasses import dataclass, field
from typing import Callable

from . import jsonl

# Past this the ledger is rewritten without its oldest lines: a relay record is
# never unacknowledged for a month, so a line that old decides nothing.
COMPACT_ABOVE = 1 << 20
KEEP_DAYS = 30


@dataclass
class Decision:
    show: bool
    kind: str = "absent"            # absent | repeat | flagged | repeat-flagged | present
    flagged: bool = False           # the copy is the rule 9 re-show
    may_repeat: bool = False        # an earlier showing was interrupted
    of: str | None = None           # the MESSAGE-ID already shown, for a flagged copy
    append_pending: bool = field(default=True, repr=False)


def _lines_for(lines: list[dict], mid: str) -> list[dict]:
    return [x for x in lines if x.get("mid") == mid]


def decide(lines: list[dict], mid: str, via: str, verdict: str) -> Decision:
    """The ledger's rule for one copy, from the lines already there. Pure."""
    mine = _lines_for(lines, mid)
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
        self.open_for_show: list[tuple[str, str, bool]] = []     # (mid, via, flagged) pending, awaiting the final line
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

    def decide(self, mid: str, via: str, verdict: str) -> Decision:
        # A showing this very lock has begun (a pending line it wrote) is as good as
        # shown for the next copy of the same message in the same pass: both carriers'
        # copies of one message can arrive on one page, and the second must see the first.
        mine = [{"mid": m, "via": v, "t": "", **({"flagged": True} if f else {})} for m, v, f in self.open_for_show]
        pend = {(m, v, f) for m, v, f in self.open_for_show}
        lines = [x for x in self.lines if not (x.get("pending") and (x["mid"], x["via"], bool(x.get("flagged"))) in pend)]
        return decide(lines + mine, mid, via, verdict)

    def _put(self, mid: str, via: str, flagged: bool, pending: bool) -> None:
        line: dict = {"mid": mid, "via": via, "t": self._iso()}
        if pending:
            line["pending"] = True
        if flagged:
            line["flagged"] = True
        jsonl.append(self._fd, line)
        self.lines.append(line)

    def pending(self, mid: str, via: str, flagged: bool = False) -> None:
        self._put(mid, via, flagged, True)
        self.open_for_show.append((mid, via, flagged))

    def final(self, mid: str, via: str, flagged: bool = False) -> None:
        self._put(mid, via, flagged, False)

    def finish(self) -> None:
        """The showing was written: the final line for every pending one, then release."""
        try:
            for mid, via, flagged in self.open_for_show:
                self.final(mid, via, flagged)
        finally:
            self.release()

    def finish_repeat(self, mid: str, via: str, flagged: bool = False) -> None:
        """The final line of a showing that had no pending line of its own (a repeat)."""
        self.open_for_show.append((mid, via, flagged))

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
            self._compact(fd)
            return Held(self.path, fd, self._iso)
        except BaseException:
            os.close(fd)
            raise

    def _compact(self, fd: int) -> None:
        if os.fstat(fd).st_size <= COMPACT_ABOVE:
            return
        cutoff = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - KEEP_DAYS * 86400))
        kept = []
        for raw in os.pread(fd, os.fstat(fd).st_size, 0).split(b"\n"):
            try:
                o = json.loads(raw)
            except ValueError:
                continue
            if isinstance(o, dict) and str(o.get("t", "")) >= cutoff:
                kept.append(raw + b"\n")
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        jsonl.write_all(fd, b"".join(kept))
        os.fsync(fd)


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


def settled(finals: list[dict] | None, verdict: str) -> bool:
    """Whether `unseen` stops listing a record: its final line is
    `"via": "interweave"`, or, for an ok copy, any final line for the id (a
    mismatch copy with only the relay's final line is still owed its re-show)."""
    if not finals:
        return False
    if any(x.get("via") == "interweave" for x in finals):
        return True
    return verdict != "mismatch"
