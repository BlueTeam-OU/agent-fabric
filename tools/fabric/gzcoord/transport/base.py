"""tools/fabric/gzcoord/transport/base.py — what a transport is, for the callers that must not know which one they hold
(agent-fabric ADR-067, message-transport in policies/mechanisms.json).

A transport carries GZCOORD/1 text from one login to another. Four verbs: `send` one message, `receive` what is waiting
for this login, `ack` a record received, `health` of the carrier. The grammar and the wire are not here; each transport
speaks its own (relay.py, carrier.py) and this module only names the shapes both answer with.

`Primary` is the transport of record (ADR-064 rule 11): the one whose answer is the exit status, whose record `--history`
and `--replay` read, and which starts, refuses a token and explains its failures in its own terms. A mirror carries a copy
and is never asked for those, so it need not implement them; moving the record to another transport is the day it must."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Protocol

from .. import i18n
from .. import jsvalues as js


@dataclass(frozen=True)
class Sent:
    """What a transport answered to a send that did not fail. `state`: `accepted` (every recipient durably recorded, or the
    record kept), `not-carried` (no recipient on this transport: nothing to carry), `absent` (the transport is not running),
    `failed`. A primary's failure is raised, not returned: its error carries what the sender must tell the person."""
    name: str
    state: str
    seq: Any = js.UNDEFINED
    deduplicated: Any = None


@dataclass(frozen=True)
class Health:
    name: str
    ok: bool


class Transport(Protocol):
    name: str

    def send(self, message_id: str, text: str) -> Sent: ...

    def receive(self, seconds: float, abort: threading.Event) -> list[dict]:
        """The records waiting for this login, at most `seconds` of waiting for them where the transport can wait.
        A transport that fails raises; an empty list is "nothing waiting"."""

    def ack(self, record_id: Any) -> None: ...

    def health(self) -> Health: ...


class Primary(Transport, Protocol):
    def newest(self, limit: int, timeout: float | None = None) -> Any:
        """The newest `limit` records of the channel's record, whole, as the transport answered; no cursor moves."""

    def refresh(self, error: BaseException) -> bool:
        """True when `error` was a refused credential and a fresh one has been taken, so the call may be made once more.
        False for every other error: it stands."""

    def explain(self, error: BaseException, t: i18n.Printer | None = None) -> dict:
        """{"line": the one line to say, "code": 4 for a refusal no retry cures, 0 for a transport that is down}."""

    def never_delivered(self, error: BaseException) -> bool:
        """True only when `error` proves the transport does not hold the message; anything else may come after it did."""
