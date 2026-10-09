"""tools/fabric/control/gzcoord.py — what the control plane needs of
GZCoord: runtime/control/gzcoord.mjs in Python (ADR-040 Wave 8), unwired
until the cutover.

Who this account is, the role catalogue, the project's relay integration,
the token, the relay API, and whether the account's inbox is held. The
Node module carried its own copy of each, moved out of the GZCoord
scripts so the daemon would never depend on a script that became a shim
(ADR-040 §7, amendment 2026-10-04), and said "a change to what either
answers is made in both". The Python GZCoord tools (Wave 7) are that
other copy, so here they are the one: every name below but four is
theirs, under gzcoord.mjs's name in snake_case.

CONTRACT, frozen from gzcoord.mjs:
  FABRIC_ROOT, whoami, load_taxonomy, find_taxonomy     gzcoord.gzmsg
  integration_config, inbox_root                        gzcoord.inbox_parts.config
  token, synced_var, synced_token, identity             gzcoord.inbox_parts.tokens
  hold_status                                           gzcoord.inbox_parts.hold
  relay_failure, API_TIMEOUT_S, api_timeout_s, api, ApiError, shell_word
                                                        here: the control
                                                        plane's own, below

THE CONTROL PLANE'S API differs from the GZCoord tools' (inbox.mjs's
300 s), as gzcoord.mjs's did: a relay that accepts the connection and
never answers would hold a CLI for good and stop agentd reading
requests. So a call is bounded at API_TIMEOUT_S plus whatever the
request asks the relay to wait (/api/wait's timeout_seconds), body
included; a non-2xx answer is ApiError with its status; no answer in
the bound is ApiError(timed_out=True) — a post that timed out may have
been stored, and the queue reads it as unknown. It opens through
httpsafe: the relay directly, never a proxy, no redirect followed.

WHAT IS NOT NODE'S: api takes its bound in seconds (timeout_s), not
milliseconds, and no abort signal: Python has none, so a caller with a
bound of its own passes it as timeout_s. urllib bounds each socket
operation, not the call,
so the bound is a deadline checked between reads of the body: a relay
that trickles a byte a second can hold one call up to the bound plus one
socket timeout, never longer.
"""
from __future__ import annotations

import json
import math
import os
import shlex
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import httpsafe  # noqa: E402
from control.sign import js_number  # noqa: E402
from gzcoord import gzmsg, paths  # noqa: E402
from gzcoord.inbox_parts.config import default_relay, inbox_root, integration_config  # noqa: E402, F401
from gzcoord.inbox_parts.hold import hold_status  # noqa: E402, F401
from gzcoord.inbox_parts.tokens import checked_token, identity, synced_token, synced_var, token  # noqa: E402, F401

whoami = gzmsg.whoami
load_taxonomy = gzmsg.load_taxonomy
find_taxonomy = gzmsg.find_taxonomy
FABRIC_ROOT = paths.fabric_root()

API_TIMEOUT_S = 30
_OPENER = httpsafe.opener(proxies=False, redirects="none")


class ApiError(Exception):
    """A relay call that failed: `status` when the relay answered non-2xx,
    `timed_out` when it did not answer within the bound (the call may
    have been stored)."""

    def __init__(self, message: str, status: int | None = None, timed_out: bool = False):
        super().__init__(message)
        self.status, self.timed_out = status, timed_out


def relay_failure(e: BaseException, relay_url: str) -> str:
    """What became of a relay call, for a person: one wording for every
    site that reports a final outcome, so a call that got no answer (and
    may have been stored) is never said as one that could not connect."""
    if getattr(e, "timed_out", False):
        return f"the relay at {relay_url} did not answer ({str(e).split(' -> ')[-1]})"
    if isinstance(e, TimeoutError):
        return f"the relay at {relay_url} did not answer within the caller's bound"
    if getattr(e, "status", None):
        return f"the relay refused (HTTP {e.status})"
    return f"the relay is unreachable at {relay_url}"


def api_timeout_s(path_and_query: str) -> float:
    """API_TIMEOUT_S plus the request's own timeout_seconds, when it asks
    the relay to wait: a long poll is never cut short. Read as Node's
    Number(): the first value, a finite number above zero, else nothing."""
    query = path_and_query.split("?", 1)[1] if "?" in path_and_query else ""
    raw = urllib.parse.parse_qs(query, keep_blank_values=True).get("timeout_seconds", [None])[0]
    try:
        waits = float(raw.strip()) if raw is not None and raw.strip() else 0.0
    except ValueError:
        waits = 0.0
    return API_TIMEOUT_S + (waits if math.isfinite(waits) and waits > 0 else 0.0)


def api(tok: str, path_and_query: str, relay_url: str | None = None, method: str = "GET", body: str | None = None,
        timeout_s: float | None = None, headers: dict | None = None):
    """One relay call, its JSON answer. The token goes in a header only
    (checked_token: a line break in it would put it in an error line)."""
    relay_url = default_relay() if relay_url is None else relay_url
    bound = api_timeout_s(path_and_query) if timeout_s is None else timeout_s
    tok = checked_token(tok)
    req = urllib.request.Request(f"{relay_url}{path_and_query}", method=method,
                                 data=None if body is None else body.encode("utf-8"),
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
                                          **(headers or {})})
    deadline = time.monotonic() + bound
    # The bound is said as Node said timeoutMs / 1000, a JavaScript number.
    late = ApiError(f"{path_and_query} -> no answer within {js_number(bound)} s", timed_out=True)
    try:
        with _OPENER.open(req, timeout=max(0.001, bound)) as r:
            chunks = []
            while True:
                if time.monotonic() > deadline:
                    raise late
                chunk = r.read(65536)
                if not chunk:
                    break
                chunks.append(chunk)
    except urllib.error.HTTPError as e:
        raise ApiError(f"{path_and_query} -> HTTP {e.code}", status=e.code) from None
    except (TimeoutError, socket.timeout):
        raise late from None
    except urllib.error.URLError as e:
        if isinstance(e.reason, (TimeoutError, socket.timeout)):
            raise late from None
        raise ApiError(f"{path_and_query} -> {e.reason}") from None
    return json.loads(b"".join(chunks).decode("utf-8"))


def shell_word(text: str) -> str | None:
    """The first word of a line as shlex.split reads it (POSIX, no
    comments), or None: none there, or an unterminated quote or escape,
    which is shlex's ValueError — never a guess at the value."""
    # One token, not shlex.split: Node's shellWord reads the first word
    # and stops, so a bad quote after it is not this word's problem.
    lexer = shlex.shlex(text, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return lexer.get_token()
    except ValueError:
        return None
