"""tools/fabric/jobsparts/queue.py — the control plane's queue (tools/fabric/control/queue.py) and the waits read from its stream.
A part of tools/fabric/jobs.py, whose docstring is the contract."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from fabric_jobs.base import FABRIC_ROOT, Stale
from fabric_jobs.ranking import message_of


QUEUE = os.path.join(FABRIC_ROOT, "tools", "fabric", "control", "queue.py")


# queue.py bounds each relay call well under this (QUEUE_CALL_TIMEOUT_MS), so a
# relay that does not answer is said in its words before this kills it.
QUEUE_TIMEOUT_S = 30


class Unreachable(Exception):
    """The control plane did not answer; the message says why, and `sent`
    whether a request left this account before it went quiet: True, False
    only where queue.py knows nothing left, None when nobody knows (a
    timeout, an answer that is not its JSON)."""

    def __init__(self, message: str, sent: bool | None = None):
        super().__init__(message)
        self.sent = sent


def ask_queue(*argv: str) -> dict:
    """tools/fabric/control/queue.py's answer, or Unreachable: a timeout, an
    interpreter that cannot run and an answer that is not its JSON are each said."""
    try:
        p = subprocess.run([sys.executable, QUEUE, *argv], capture_output=True, text=True, timeout=QUEUE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise Unreachable(f"no answer within {QUEUE_TIMEOUT_S} s")
    except OSError as e:
        # the interpreter never started, so queue.py posted nothing: a claim that never
        # left is said without how to land it.
        raise Unreachable(f"python could not run ({e.strerror or e})", sent=False)
    try:
        said = json.loads((p.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        said = None
    if not isinstance(said, dict):
        why = ((p.stderr or "").strip().splitlines() or [f"exit {p.returncode}"])[-1][:160]
        raise Unreachable(f"no answer ({why})")
    if p.returncode != 0:
        sent = said.get("sent")
        raise Unreachable(str(said.get("error") or f"exit {p.returncode}")[:160],
                          sent=sent if isinstance(sent, bool) else None)
    return said


def stream_waits(doc: dict, *, stored: bool = False) -> tuple[dict[str, list[str]] | None, Stale]:
    """({message id: [waiting address, ...]}, stale waiters) from the state
    stream; ({}, {}) when no queued job came from a message (nothing could
    match), (None, {}) when the stream could not be read — said here, once,
    and stored priorities decide."""
    if stored or not any(j["state"] == "queued" and message_of(j) for j in doc["jobs"]):
        return {}, {}
    try:
        said = ask_queue("waits")
    except Unreachable as e:
        print(f"fabric-jobs: the state stream could not be read ({e}): stored priorities decide", file=sys.stderr)
        return None, {}
    waits = said.get("waits")
    if not isinstance(waits, dict):
        print("fabric-jobs: the state stream's answer has no waits: stored priorities decide", file=sys.stderr)
        return None, {}
    stale = said.get("stale")
    if not isinstance(stale, dict):
        # The ranking stands; what is unknown is only how old each wait is.
        print("fabric-jobs: the state stream's answer has no record ages: a waiter's age is unknown", file=sys.stderr)
        stale = {}
    ages: Stale = {str(a): (v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None)
                   for a, v in stale.items()}
    return {str(k): [str(a) for a in v] for k, v in waits.items() if isinstance(v, list)}, ages
