"""tools/fabric/gzcoord/bypass.py — the record of GZCOORD_JOURNAL=off.

ADR-041 keeps every message in the agent's journal before it is posted and
before an inbound one is shown or acknowledged. GZCOORD_JOURNAL=off is the
break-glass that skips the journal; this is what it leaves instead, so an
escape from the invariant is never an escape without a trace:

  <agent state dir>/journal-bypass.jsonl, one JSON object per crossing:
    {"at", "direction": "out"|"in", "message_id", "sha256", "seq", "reason"}
    and, on an out line, "outcome": "pending" | "accepted" | "failed" | "unknown"

  at          UTC, milliseconds, Z (as send.py's ledger stamps)
  message_id  the message's MESSAGE-ID, null when it has none or does not parse
  sha256      of the text the journal would have hashed (the posted text out,
              the record's content in), so a bypass line and a journal row
              match; UTF-8, a lone surrogate passed through as its bytes
  seq         the carrier's seq when known: an inbound record's, an accepted
              send's; null on a pending or failed one
  reason      "GZCOORD_JOURNAL=off"
  outcome     a send has two lines: "pending" before the post (written, or
              the send is refused), then one once the post is over:
              "accepted" (the relay took it, with its seq), "failed" (the
              relay answered and refused it, or it never left this
              process), or "unknown" (no answer that could be read: it may
              have reached the relay). A pending line with no second one is
              a send whose outcome was never recorded: it may have too.

A line is one crossing, not one message: a record the relay shows again
(its acknowledgement was lost) crossed again, and gets another line;
(direction, seq, sha256) names the message across them.

Never the body. Each line is ASCII JSON, so no text the relay sends can
fail to be written. Appended under identity.agent_lock (ADR-003), the
file created 0600, never followed through a symlink nor waited on as a
FIFO (the lock is held while it opens); a directory or a socket there
fails the open too. Kept whole: an audit record is not trimmed.

What is guaranteed, and what is not: a write that lands short or fails
after landing bytes is truncated back to where it began, so a refused
crossing leaves no line. A process killed between its write and that
truncate, or a truncate that itself fails (said, in the refusal), can
leave a fragment at the end. So a reader skips a line that does not parse,
and a writer that finds the file not ending in a newline starts on a fresh
line: one fragment never swallows the line after it. A line that cannot be
written raises BypassUnrecorded, and the caller refuses the bypass: fail
closed.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from typing import Any

from . import gzmsg, paths

REASON = "GZCOORD_JOURNAL=off"
FILE = "journal-bypass.jsonl"


class BypassUnrecorded(Exception):
    """The bypass record could not be written; the message must not cross."""


def is_off() -> bool:
    return os.environ.get("GZCOORD_JOURNAL") == "off"


def path() -> str:
    return os.path.join(paths.identity().agent_state_dir(), FILE)


def _now_iso() -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def entry(direction: str, text: str, seq: Any = None, outcome: str | None = None) -> dict:
    """One line's content: the message by id and hash, never its body;
    `outcome` on a send's lines (see the contract above)."""
    try:
        mid = gzmsg.parse(text)["metadata"].get("MESSAGE-ID") or None
    except (gzmsg.NotGzcoord, AttributeError, TypeError, KeyError):
        mid = None
    return {"at": _now_iso(), "direction": direction, "message_id": mid,
            # surrogatepass: the same bytes as the journal's for any valid text;
            # a lone surrogate the relay may send (JSON \ud800) is hashed, not
            # raised past the inbox's hold as a transport failure.
            "sha256": hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest(),
            "seq": seq if isinstance(seq, int) and not isinstance(seq, bool) else None, "reason": REASON,
            **({"outcome": outcome} if outcome is not None else {})}


def _last_byte(target: str, fd: int) -> bytes:
    """The file's last byte, read through a second, read-only descriptor of
    the same file: the record's own is write-only, which is what makes a
    FIFO there fail its open."""
    rfd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        here, there = os.fstat(fd), os.fstat(rfd)
        if (here.st_dev, here.st_ino) != (there.st_dev, there.st_ino):
            raise OSError(f"{target} was replaced while it was opened")
        return os.pread(rfd, 1, here.st_size - 1)
    finally:
        os.close(rfd)


def record(entries: list[dict]) -> None:
    """Append the lines in one write, under the agent's lock, or raise."""
    if not entries:
        return
    data = "".join(json.dumps(e, ensure_ascii=True, separators=(",", ":")) + "\n" for e in entries).encode("ascii")
    try:
        identity = paths.identity()
        target = path()
    except Exception as e:  # noqa: BLE001 — no state directory is no record: refused, never a default path
        raise BypassUnrecorded(f"the journal-bypass record has no place: this login's state directory is"
                               f" unknown ({e})") from None
    try:
        with identity.agent_lock():
            # O_NONBLOCK: a FIFO placed here fails the open (no reader) instead
            # of blocking it, and the agent's lock with it; it changes nothing
            # for a regular file, the only kind written to.
            fd = os.open(target, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC
                         | os.O_NONBLOCK, 0o600)
            try:
                os.fchmod(fd, 0o600)
                # The end before this write: every writer appends under the
                # lock, so nothing else moves it until the lock is released.
                start = os.fstat(fd).st_size
                if start and _last_byte(target, fd) != b"\n":
                    # A fragment (a kill, or an undo that failed) ends the
                    # file: this line starts on its own, readable after it.
                    data = b"\n" + data
                try:
                    written = os.write(fd, data)
                    if written != len(data):
                        # A full disk or quota takes a prefix: those bytes are
                        # in the file, a line cut short before every later one.
                        raise OSError(f"wrote {written} of {len(data)} bytes")
                    os.fsync(fd)
                except OSError as e:
                    # Refused, so not one byte of it stays: a refused crossing
                    # leaves no line, not even the start of one.
                    try:
                        os.ftruncate(fd, start)
                    except OSError as undo:
                        raise BypassUnrecorded(
                            f"the journal-bypass record {target} could not be written ({e.strerror or e}), and"
                            f" the partial line could not be removed ({undo.strerror or undo}): the record may"
                            f" end in a fragment") from None
                    raise
            finally:
                os.close(fd)
    except OSError as e:
        raise BypassUnrecorded(f"the journal-bypass record {target} could not be written"
                               f" ({e.strerror or e})") from None
