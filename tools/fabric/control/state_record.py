"""tools/fabric/control/state_record.py — an account's newest state record kept on its own disk, and the `state` op that
answers it (agent-fabric ADR-029 rule 16; the cutover plan §2.5, row 2).

The relay's state channel gave every reader each account's newest record out of stored history. The second carrier stores none, so
each agentd keeps the one record it last posted and answers for it.

CONTRACT
  store(file, record)    writes the record, JSON and a newline, mode 0600: a temporary file in the same directory,
                         fsynced, renamed over `file`. A reader never sees half a record; a failure leaves the old
                         record and raises OSError, and removes its temporary file.
  load(file)             the record as written, or None when none was written yet. A file that cannot be read or is
                         not a JSON object raises StateRecordError: absent and broken stay apart.
  state(request, me, file)  the op's answer, {"address": me, "state": <record>} or {"address": me, "state": None,
                         "why": <text>}; `why` says whether no record was written yet or the file cannot be read.
                         The address is the answering account's own, which a reader holds to the one it asked.
                         Never a made-up record, never {"sessions": []}: a reader takes None as unknown.
"""
from __future__ import annotations

import os
import sys

if sys.path and os.path.realpath(sys.path[0] or ".") == os.path.dirname(os.path.realpath(__file__)):
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from control import js  # noqa: E402

RECORD_FILE = "state-record.json"
STATE_OP = "state"


class StateRecordError(Exception):
    """The record file exists and cannot be used."""


def store(file: str, record: dict) -> None:
    tmp = f"{file}.{os.getpid()}.tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(js.stringify(record) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.rename(tmp, file)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load(file: str) -> dict | None:
    try:
        with open(file, encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as e:
        raise StateRecordError(f"{os.path.basename(file)} cannot be read ({e.__class__.__name__})") from None
    try:
        record = js.json_parse(text)
    except ValueError:
        raise StateRecordError(f"{os.path.basename(file)} is not JSON") from None
    if not isinstance(record, dict):
        raise StateRecordError(f"{os.path.basename(file)} is not a JSON object")
    return record


def state(request: dict, *, me: str, file: str) -> dict:  # noqa: ARG001 — the op takes no args
    try:
        record = load(file)
    except StateRecordError as e:
        return {"address": me, "state": None, "why": str(e)}
    if record is None:
        return {"address": me, "state": None, "why": "no state record has been written yet"}
    return {"address": me, "state": record}
