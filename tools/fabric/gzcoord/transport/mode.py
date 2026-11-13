"""tools/fabric/gzcoord/transport/mode.py — the account's transport mode, the one place it is read and written
(the transport cutover plan's D2 and D10, row W5; agent-fabric ADR-067).

The mode is a fact about the account, kept in the account's own state directory (identity.agent_state_dir) and never in
a committed file: the operator moves one account at a time with the signed action `<carrier>-mode`, and the file is
what that action writes.

CONTRACT
  MODES            relay-record (today's behaviour), carrier-record, carrier-only.
  DEFAULT          relay-record: what an account with no transport-mode.json is in. Absence is the normal state and a reader
                   never creates the file, so an account nobody moved behaves byte for byte as before this module.
  read(state_dir)  the Mode: {"mode", "set_by", "set_at"} (the last two None for the default). A file that is not JSON, not
                   an object, or whose mode is not one of MODES raises ModeError: an unknown mode is never read as the
                   default, because the file was written to move the account and a damaged one must not quietly move it
                   back. The signed action rewrites it, which is the repair.
  write(mode, set_by, state_dir)
                   the record, written atomically under the agent lock; mode names one of MODES.
  Nothing here says what a mode sends or reads: that is the transports' (W6 to W8). open_transport only carries the mode
  on the mux it returns."""
from __future__ import annotations

import json
import os
import stat
from typing import Callable

from .. import paths
from ..carrier import CARRIER_NAME

RELAY_RECORD = "relay-record"
CARRIER_RECORD = "carrier-record"
CARRIER_ONLY = "carrier-only"
MODES = (RELAY_RECORD, CARRIER_RECORD, CARRIER_ONLY)
DEFAULT = RELAY_RECORD
FILE = "transport-mode.json"


class ModeError(Exception):
    """The mode could not be read as one; the message names the file and the fact that fixes it, never its content."""


def path(state_dir: str | None = None) -> str:
    try:
        return os.path.join(paths.identity().agent_state_dir() if state_dir is None else state_dir, FILE)
    except SystemExit as e:        # identity.current_agent refuses with a line when the login cannot be told
        raise ModeError(f"the account's state directory is unknown ({e})") from None


MAX_BYTES = 4096     # a record is a few dozen bytes; anything larger is not one, and is not parsed


def _fix() -> str:
    return f"`fabric-ctl <login> {CARRIER_NAME}-mode --mode <mode>` rewrites it"


def read(state_dir: str | None = None) -> dict:
    file = path(state_dir)
    try:
        st = os.lstat(file)
        # Regular files only: a FIFO would block the reader (the watch's main thread) and a symlink would redirect it.
        if not stat.S_ISREG(st.st_mode):
            raise ModeError(f"{file} is not a regular file; {_fix()}")
        fd = os.open(file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as fh:
            raw = fh.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ModeError(f"{file} is larger than a transport mode record; {_fix()}")
        doc = json.loads(raw.decode("utf-8"))
    except (FileNotFoundError, NotADirectoryError):
        # A state directory that is not one holds no mode file; the journal reports that failure in its own words, as before.
        return {"mode": DEFAULT, "set_by": None, "set_at": None}
    except (OSError, ValueError, RecursionError) as e:    # RecursionError: nesting inside the size bound is still a parse failure
        raise ModeError(f"{file} cannot be read as a transport mode ({e.__class__.__name__}); {_fix()}") from None
    if not isinstance(doc, dict) or doc.get("mode") not in MODES:
        raise ModeError(f"{file} does not hold a transport mode ({', '.join(MODES)}); {_fix()}")
    return {"mode": doc["mode"], "set_by": doc.get("set_by"), "set_at": doc.get("set_at")}


def write(mode: str, set_by: str, state_dir: str | None = None) -> dict:
    if mode not in MODES:
        raise ValueError(f"the transport mode is one of {', '.join(MODES)}")
    identity = paths.identity()
    record = {"mode": mode, "set_by": set_by, "set_at": identity.now_iso()}
    body = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if state_dir is None:
        directory = identity.agent_state_dir()
        with identity.agent_lock():     # the login's own state: serialized with its other writers
            os.makedirs(directory, exist_ok=True)
            identity.atomic_write(os.path.join(directory, FILE), body)
    else:
        # An explicit directory is not the login's: the login's lock protects nothing there, and the rename is atomic alone.
        os.makedirs(state_dir, exist_ok=True)
        identity.atomic_write(os.path.join(state_dir, FILE), body)
    return record


class Watcher:
    """What a running watch asks to learn that the mode changed. The file is read at most once per `every` seconds and a
    read that fails keeps the last mode and is said once per distinct reason to `on_error`: a watch is not ended by a file
    it could not read, and it is never moved by one. `changed()` is True once per change."""

    def __init__(self, current: str, state_dir: str | None = None, every: float = 5.0,
                 clock: Callable[[], float] | None = None, reader: Callable[[str | None], dict] = read,
                 on_error: Callable[[str], None] = lambda reason: None) -> None:
        import time
        self.current = current
        self._dir = state_dir
        self._every = every
        self._clock = clock or time.monotonic
        self._read = reader
        self._on_error = on_error
        self._said: str | None = None
        self._next = self._clock() + every

    def changed(self) -> bool:
        now = self._clock()
        if now < self._next:
            return False
        self._next = now + self._every
        try:
            mode = self._read(self._dir)["mode"]
        except ModeError as e:
            if str(e) != self._said:
                self._said = str(e)
                self._on_error(str(e))
            return False
        self._said = None
        if mode == self.current:
            return False
        self.current = mode
        return True
