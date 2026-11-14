"""tools/fabric/gzcoord/transport/relay.py — the relay as a Primary transport, over inbox_parts/relay.py (the HTTP client
and the hosted relay's start) and inbox_parts/tokens.py (the credential).

No behaviour of its own: each verb is the call the inbox and the sender made themselves before agent-fabric ADR-067, with
the same path, query, body, timeout and error."""
from __future__ import annotations

import sys
import threading
import time
import urllib.parse
from typing import Any, Callable

from .. import i18n
from .. import jsvalues as js
from ..inbox_parts import relay as _relay
from ..inbox_parts.config import relay_runtime_dir
from ..inbox_parts.tokens import TokenRefused, synced_token
from .base import Health, Sent

NAME = "relay"


def start(cfg: dict, t: i18n.Printer | None = None) -> dict:
    """What the session owns first: the hosting working copy brings its relay up (inbox_parts.relay.ensure_relay). A client
    returns {"hosted": False, ...} at once."""
    return _relay.ensure_relay(relay_runtime_dir(cfg), cfg["relay_url"], t)


class RelayTransport:
    name = NAME

    def __init__(self, relay_url: str, channel: str, address: str, token: str) -> None:
        self.relay_url, self.channel, self.address, self._token = relay_url, channel, address, token

    def _api(self, path_and_query: str, **kw: Any) -> Any:
        # Looked up at the call, so a test that replaces inbox_parts.relay.api sees every verb.
        return _relay.api(self._token, path_and_query, self.relay_url, **kw)

    def send(self, message_id: str, text: str) -> Sent:
        """Posts the message; a refused token is taken fresh from the synced file once (the shell snapshot of a rotated token
        is the usual cause) and the post made again. Raises what the relay's client raises."""
        body = js.stringify({"channel": self.channel, "sender": self.address, "content": text})
        try:
            res = self._api("/api/send", method="POST", body=body)
        except _relay.RelayError as e:
            if not self.refresh(e):
                raise
            res = self._api("/api/send", method="POST", body=body)
        return Sent(self.name, "accepted", js.get(res, "seq") if isinstance(res, dict) else js.UNDEFINED,
                    res.get("deduplicated") if isinstance(res, dict) else None)

    def receive(self, seconds: float, abort: threading.Event) -> list[dict]:
        q = urllib.parse.urlencode({"channel": self.channel, "consumer_id": self.address,
                                    "timeout_seconds": js.string(seconds), "limit": "50"})
        page = self._api(f"/api/wait?{q}", timeout=seconds + _relay.API_TIMEOUT)
        msgs = page.get("messages") if isinstance(page, dict) else None
        return msgs if isinstance(msgs, list) else []

    def ack(self, record_id: Any) -> None:
        self._api("/api/ack", method="POST", body=js.stringify(
            {"consumer_id": self.address, "channel": self.channel, "message_id": record_id}))

    def health(self) -> Health:
        return Health(self.name, _relay._relay_up(self.relay_url, 2))

    def newest(self, limit: int, timeout: float | None = None) -> Any:
        q = "/api/messages?" + urllib.parse.urlencode({"channel": self.channel, "limit": str(limit), "full": "1"})
        return self._api(q) if timeout is None else self._api(q, timeout=timeout)

    def refresh(self, error: BaseException) -> bool:
        if not (isinstance(error, _relay.RelayError) and error.status in (401, 403)):
            return False
        fresh = synced_token()
        if not fresh or fresh == self._token:
            return False
        self._token = fresh
        return True

    def explain(self, error: BaseException, t: i18n.Printer | None = None) -> dict:
        return _relay.explain_relay_error(error, self.relay_url, t)

    def never_delivered(self, error: BaseException) -> bool:
        """A post that failed in a way that proves the relay does not hold the message: refused with a 4xx (the request was
        judged and turned away), a connection that never reached it, or a token refused before it left. Anything else (no
        answer, a timeout, a reset, a body that is not the relay's, a 5xx from the relay or a proxy in front of it) may come
        after the relay stored it: delivered or not is unknown."""
        status = getattr(error, "status", None)
        return ((isinstance(status, int) and 400 <= status < 500) or getattr(error, "reached", None) is False
                or isinstance(error, TokenRefused))


# After a relay that did not answer, nothing is asked of it for this long: a mirror that is down must not cost the carrier's
# watch a connection attempt a slice (the carrier adapter's DOWN_FOR is the same rule on the other side).
MIRROR_DOWN_FOR_S = 30.0


class RelayMirror:
    """The relay as a mirror of the carrier (mode carrier-record, ADR-064 rule 11): every message goes to it too, and what
    it holds for this login is read beside the carrier's and shown once (dedup.py). It is never the record, so nothing it
    does changes an exit status or what is shown: a send that fails is `failed` and a line, a page it cannot give is an empty
    one and a line, said once per outage. Its acknowledgement is the one call that raises, for the mux logs it; the caller
    that acknowledges swallows it."""
    name = NAME

    def __init__(self, relay: RelayTransport, clock: Callable[[], float] = time.monotonic) -> None:
        self._relay, self._clock = relay, clock
        self._down_until = 0.0
        self._said = False

    def _fell(self, what: str, e: BaseException) -> None:
        self._down_until = self._clock() + MIRROR_DOWN_FOR_S
        if not self._said:
            self._said = True
            print(f"gzcoord: the relay did not answer ({what}: {e}); the InterWeave carrier is the record", file=sys.stderr)

    def send(self, message_id: str, text: str) -> Sent:
        try:
            return self._relay.send(message_id, text)
        except Exception as e:  # noqa: BLE001 — a mirror's failure is a line, whatever it was
            self._fell("send", e)
            return Sent(self.name, "failed")

    def receive(self, seconds: float, abort: threading.Event) -> list[dict]:
        if self._clock() < self._down_until:
            return []
        try:
            page = self._relay.receive(0, abort)
        except Exception as e:  # noqa: BLE001
            self._fell("wait", e)
            return []
        self._said = False
        return page

    def ack(self, record_id: Any) -> None:
        self._relay.ack(record_id)

    def health(self) -> Health:
        return self._relay.health()
