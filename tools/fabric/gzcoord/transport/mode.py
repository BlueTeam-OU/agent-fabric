"""tools/fabric/gzcoord/transport/mode.py — the account's transport mode, the one place it is read and written
(the transport cutover plan's D2 and D10, row W5; agent-fabric ADR-067).

The mode is a fact about the account, kept in the account's own state directory (identity.agent_state_dir) and never in
a committed file: the operator moves one account at a time with the signed action `<carrier>-mode`, and the file is
what that action writes.

CONTRACT
  MODES            relay-record (today's behaviour), carrier-record, carrier-only.
  DEFAULT          carrier-only: what an account with no transport-mode.json is in (W15, after gate 2 of the cutover plan; it was
                   relay-record). Absence is the normal state and a reader never creates the file. Since W15 the GZCoord send and
                   inbox build the carrier alone whatever this says; the file is read by the control plane's presence ask, the
                   carrier's position report and the Stop hook, and is rewritten by the signed action.
  read(state_dir)  the Mode: {"mode", "set_by", "set_at"} (the last two None for the default). A file that is not a regular
                   file (a FIFO would block the watch, a symlink would redirect it), is larger than MAX_BYTES, cannot be
                   opened or read, is not JSON, is not an object, or whose mode is not one of MODES raises ModeError: an unknown mode is never read as the
                   default, because the file was written to move the account and a damaged one must not quietly move it
                   back. The signed action rewrites it, which is the repair.
  write(mode, set_by, state_dir)
                   the record, written atomically; mode names one of MODES. Under the agent lock when state_dir is None (the
                   login's own directory, which its other writers share); with an explicit state_dir no lock is taken, the
                   login's lock protecting nothing there.
  ENV              GZCOORD_TRANSPORT_MODE: the one-command override (plan section 6, D10). When set and not empty it names the mode
                   of THIS command, whatever the state file says, and the file is not read (a damaged file does not stop the
                   command that overrides it: that is what the override is for). A value that is not one of MODES raises
                   ModeError: an unknown mode is never read as the default. Empty is read as unset, as a shell's `VAR= cmd`
                   means. The presence child the sender starts honours it; send, inbox and the watch no longer read the mode.
  effective(state_dir, env, say)
                   the Mode a command runs in: the override when set, else read(). `say` is called once with the line that
                   tells the override is in force ("every time it is used"); a repeated read of the same command (the watch's
                   poll, the presence child) passes none.
  Nothing here says what a mode sends or reads."""
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
DEFAULT = CARRIER_ONLY
FILE = "transport-mode.json"
ENV = "GZCOORD_TRANSPORT_MODE"


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


def effective(state_dir: str | None = None, env: dict | None = None,
              say: Callable[[str], None] | None = None) -> dict:
    value = (os.environ if env is None else env).get(ENV)
    if not value:
        return read(state_dir)
    if value not in MODES:
        shown = value if len(value) <= 40 and value.isprintable() else value[:40].encode("unicode_escape").decode("ascii") + "..."
        raise ModeError(f"{ENV}={shown} is not a transport mode ({', '.join(MODES)}); unset it or name one of them")
    if say is not None:
        say(f"gzcoord: transport mode {value} for this command, from {ENV} (the account's own mode is not read)")
    return {"mode": value, "set_by": ENV, "set_at": None}


def say_stderr(line: str) -> None:
    import sys
    print(line, file=sys.stderr, flush=True)


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

