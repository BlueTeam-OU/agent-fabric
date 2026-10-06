"""tools/fabric/gzcoord/bypass.py — the record of GZCOORD_JOURNAL=off.

ADR-041 keeps every message in the agent's journal before it is posted and
before an inbound one is shown or acknowledged. GZCOORD_JOURNAL=off is the
break-glass that skips the journal; this is what it leaves instead, so an
escape from the invariant is never an escape without a trace:

  <agent state dir>/journal-bypass.jsonl, one JSON object per crossing:
    {"at", "direction": "out"|"in", "message_id", "sha256", "seq", "reason"}

  at          UTC, milliseconds, Z (as send.py's ledger stamps)
  message_id  the message's MESSAGE-ID, null when it has none or does not parse
  sha256      of the text the journal would have hashed (the posted text out,
              the record's content in), so a bypass line and a journal row
              match; UTF-8, a lone surrogate passed through as its bytes
  seq         the carrier's seq when known: an inbound record's; null out,
              since the line is written before the post
  reason      "GZCOORD_JOURNAL=off"

A line is one crossing, not one message: a record the relay shows again
(its acknowledgement was lost) crossed again, and gets another line;
(direction, seq, sha256) names the message across them.

Never the body. Each line is ASCII JSON, so no text the relay sends can
fail to be written. Appended under identity.agent_lock (ADR-003), the
file created 0600, never followed through a symlink nor waited on as a
FIFO (the lock is held while it opens); a directory or a socket there
fails the open too. Kept whole: an audit record is not trimmed, and
holds whole lines only: a write that lands short or fails after landing
bytes is truncated back to where it began. A line that cannot be written
raises BypassUnrecorded, and the caller refuses the bypass: fail closed.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import sys
from typing import Any

from . import gzmsg

REASON = "GZCOORD_JOURNAL=off"
FILE = "journal-bypass.jsonl"


class BypassUnrecorded(Exception):
    """The bypass record could not be written; the message must not cross."""


def is_off() -> bool:
    return os.environ.get("GZCOORD_JOURNAL") == "off"


def _identity():
    """runtime/identity.py, the one source of the state directory and its lock."""
    runtime = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.realpath(__file__))))), "runtime")
    if runtime not in sys.path:
        sys.path.insert(0, runtime)
    import identity  # noqa: E402 — runtime/, found by its path
    return identity


def path() -> str:
    return os.path.join(_identity().agent_state_dir(), FILE)


def _now_iso() -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def entry(direction: str, text: str, seq: Any = None) -> dict:
    """One line's content: the message by id and hash, never its body."""
    try:
        mid = gzmsg.parse(text)["metadata"].get("MESSAGE-ID") or None
    except (gzmsg.NotGzcoord, AttributeError, TypeError, KeyError):
        mid = None
    return {"at": _now_iso(), "direction": direction, "message_id": mid,
            # surrogatepass: the same bytes as the journal's for any valid text;
            # a lone surrogate the relay may send (JSON \ud800) is hashed, not
            # raised past the inbox's hold as a transport failure.
            "sha256": hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest(),
            "seq": seq if isinstance(seq, int) and not isinstance(seq, bool) else None, "reason": REASON}


def record(entries: list[dict]) -> None:
    """Append the lines in one write, under the agent's lock, or raise."""
    if not entries:
        return
    data = "".join(json.dumps(e, ensure_ascii=True, separators=(",", ":")) + "\n" for e in entries).encode("ascii")
    try:
        identity = _identity()
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
                try:
                    written = os.write(fd, data)
                    if written != len(data):
                        # A full disk or quota takes a prefix: those bytes are
                        # in the file, a line cut short before every later one.
                        raise OSError(f"wrote {written} of {len(data)} bytes")
                    os.fsync(fd)
                except OSError as e:
                    # Refused, so not one byte of it stays: the file is whole
                    # lines at every instant, and a refused crossing has none.
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
