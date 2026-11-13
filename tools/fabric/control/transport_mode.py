"""tools/fabric/control/transport_mode.py — `<carrier>-mode`, the signed action that moves this account's GZCoord transport
mode (the transport cutover plan's D2 and D10, row W5; <carrier> is gzcoord.carrier.CARRIER_NAME), and the mode the
`<carrier>` read shows.

The mode is the account's own state (gzcoord/transport/mode.py), written here as the login the control agent runs as and
never kept in a committed file. The record names the operator who signed the action (`from`), never a field the request chose.

CONTRACT
  set_mode(request)  args {"mode": one of mode.MODES}, no other key. Answers {"status": "set", "mode": <record>,
                     "previous": the mode before, or None when the file could not be read} or {"status": "refused",
                     "reason"} for bad arguments or an unsigned-looking request, {"status": "failed", "reason"} when the
                     file was not written. A file that cannot be read is rewritten all the same: the action is the repair.
                     This is the account's own half: that no placed account is still on relay-record before carrier-only
                     is fabric-ctl's check, which sees the fleet (control/ctl.py), because one account cannot.
  section()          what the read adds to its answer: {"mode", "set_by", "set_at"}, or {"mode": None, "error"} when the
                     file cannot be read; unknown is shown as unknown, never as the default."""
from __future__ import annotations

import os
import sys

if sys.path and os.path.realpath(sys.path[0] or ".") == os.path.dirname(os.path.realpath(__file__)):
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from control import js  # noqa: E402
from gzcoord.carrier import CARRIER_NAME  # noqa: E402
from gzcoord.transport import mode as _mode  # noqa: E402

MODE_OP = f"{CARRIER_NAME}-mode"
MODES = _mode.MODES
RELAY_RECORD, CARRIER_ONLY = _mode.RELAY_RECORD, _mode.CARRIER_ONLY


def check_mode(value) -> str | None:
    """Why fabric-ctl refuses this before anything is sent: the daemon's own rule, so the two cannot differ."""
    if value not in MODES:
        return f"the transport mode is one of {', '.join(MODES)}"
    return None


def check_args(args) -> str | None:
    if not isinstance(args, dict):
        return f"{MODE_OP} takes {{ mode }}"
    extra = [k for k in js.keys(args) if k != "mode"]
    if extra:
        return f"{MODE_OP} takes only mode, not {', '.join(extra)}"
    return check_mode(args.get("mode"))


def set_mode(request: dict, state_dir: str | None = None, **_: object) -> dict:
    args = request.get("args")
    bad = check_args(args)
    if bad:
        return {"status": "refused", "reason": bad}
    sender = request.get("from")
    if not isinstance(sender, str) or not sender:
        return {"status": "refused", "reason": "the request does not say who signed it"}
    try:
        previous = _mode.read(state_dir)["mode"]
    except _mode.ModeError:
        previous = None
    try:
        record = _mode.write(args["mode"], sender, state_dir)
    except (OSError, SystemExit, _mode.ModeError) as e:
        return {"status": "failed", "reason": f"{_mode.FILE} was not written: {getattr(e, 'strerror', None) or e}"}
    return {"status": "set", "mode": record, "previous": previous}


def section(state_dir: str | None = None) -> dict:
    try:
        return _mode.read(state_dir)
    except _mode.ModeError as e:
        return {"mode": None, "error": str(e)}
