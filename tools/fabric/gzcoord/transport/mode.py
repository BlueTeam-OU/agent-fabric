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


def read(state_dir: str | None = None) -> dict:
    file = path(state_dir)
    try:
        with open(file, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return {"mode": DEFAULT, "set_by": None, "set_at": None}
    except (OSError, ValueError) as e:
        raise ModeError(f"{file} cannot be read as a transport mode ({e.__class__.__name__}); "
                        f"`fabric-ctl <login> {CARRIER_NAME}-mode --mode <mode>` rewrites it") from None
    if not isinstance(doc, dict) or doc.get("mode") not in MODES:
        raise ModeError(f"{file} does not hold a transport mode ({', '.join(MODES)}); "
                        f"`fabric-ctl <login> {CARRIER_NAME}-mode --mode <mode>` rewrites it")
    return {"mode": doc["mode"], "set_by": doc.get("set_by"), "set_at": doc.get("set_at")}


def write(mode: str, set_by: str, state_dir: str | None = None) -> dict:
    if mode not in MODES:
        raise ValueError(f"the transport mode is one of {', '.join(MODES)}")
    identity = paths.identity()
    directory = identity.agent_state_dir() if state_dir is None else state_dir
    with identity.agent_lock():
        record = {"mode": mode, "set_by": set_by, "set_at": identity.now_iso()}
        os.makedirs(directory, exist_ok=True)
        identity.atomic_write(os.path.join(directory, FILE), json.dumps(record, indent=2, sort_keys=True) + "\n")
    return record


class Watcher:
    """What a running watch asks to learn that the mode changed. The file is read at most once per `every` seconds and a
    read that fails keeps the last mode (the next arm reports it through open_transport): a watch is not ended by a file
    it could not read for one moment. `changed()` is True once per change."""

    def __init__(self, current: str, state_dir: str | None = None, every: float = 5.0,
                 clock: Callable[[], float] | None = None, reader: Callable[[str | None], dict] = read) -> None:
        import time
        self.current = current
        self._dir = state_dir
        self._every = every
        self._clock = clock or time.monotonic
        self._read = reader
        self._next = self._clock() + every

    def changed(self) -> bool:
        now = self._clock()
        if now < self._next:
            return False
        self._next = now + self._every
        try:
            mode = self._read(self._dir)["mode"]
        except ModeError:
            return False
        if mode == self.current:
            return False
        self.current = mode
        return True
