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
included; a non-2xx answer is ApiError with its status, a 3xx too (no
redirect is followed); no answer in the bound is ApiError(timed_out=True)
— a post that timed out may have been stored, and the queue reads it as
unknown. It is http.client, not urllib: the relay directly, never a
proxy from the environment, and a timer that shuts the socket at the
deadline, so the bound holds whatever the relay trickles, headers and
body alike (review of e04c5593, F1).

WHAT IS NOT NODE'S: api takes its bound in seconds (timeout_s), not
milliseconds, and no abort signal: Python has none, so a caller with a
bound of its own passes it as timeout_s; API_TIMEOUT_MS is API_TIMEOUT_S.
WHOAMI_TIMEOUT_MS has no counterpart: Node ran `python3 identity.py`
under it, and the GZCoord tools import identity.py in this process,
which starts nothing to bound. The bound does not cover resolving a
relay's host name (getaddrinfo cannot be cut short); the relays the
projects configure are addresses, not names.
"""
from __future__ import annotations

import http.client
import json
import math
import os
import shlex
import socket
import ssl
import sys
import threading
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from control import js  # noqa: E402
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
    the relay to wait: a long poll is never cut short. Read as Node read
    it: the query is the text between the first `?` and the next (Node's
    split('?')[1]), its first timeout_seconds through URLSearchParams,
    then Number() — a finite number above zero, else nothing."""
    parts = path_and_query.split("?")
    query = parts[1] if len(parts) > 1 else ""
    raw = urllib.parse.parse_qs(query, keep_blank_values=True).get("timeout_seconds", [None])[0]
    waits = js.number(raw) if raw is not None else math.nan
    return API_TIMEOUT_S + (waits if math.isfinite(waits) and waits > 0 else 0.0)


def api(tok: str, path_and_query: str, relay_url: str | None = None, method: str = "GET", body: str | None = None,
        timeout_s: float | None = None, headers: dict | None = None):
    """One relay call, its JSON answer. The token goes in a header only
    (checked_token: a line break in it would put it in an error line)."""
    relay_url = default_relay() if relay_url is None else relay_url
    bound = api_timeout_s(path_and_query) if timeout_s is None else timeout_s
    tok = checked_token(tok)
    # The bound is said as Node said timeoutMs / 1000, a JavaScript number.
    late = ApiError(f"{path_and_query} -> no answer within {js_number(bound)} s", timed_out=True)
    u = urllib.parse.urlsplit(f"{relay_url}{path_and_query}")
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ApiError(f"{path_and_query} -> not an http(s) relay: {relay_url}")
    conn_class = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
    conn = conn_class(u.hostname, u.port, timeout=max(0.001, bound))
    fired = threading.Event()
    # Held by cut() and by use(): either the deadline finds the socket, or
    # the call finds the deadline already passed — never a socket that
    # comes into being after cut() looked (re-review of 37b23c5c..5ca0b96e, F1).
    lock = threading.Lock()

    live: list = []      # the socket in use now, a TCP one or its TLS one: what cut() shuts

    def cut():
        # The deadline, whatever phase the call is in: a connect, a TLS
        # handshake or a read blocked on a relay that trickles returns once
        # its socket is shut.
        with lock:
            fired.set()
            for sock in live:
                try:
                    # The descriptor itself: SSLSocket.shutdown would drop its
                    # SSL object first, and a handshake about to start would
                    # meet None, an AttributeError, not a timeout.
                    socket.socket.shutdown(sock, socket.SHUT_RDWR)
                except OSError:
                    pass

    def remaining() -> float:
        left = deadline - time.monotonic()
        if left <= 0:
            raise late
        return left

    def use(sock) -> None:
        with lock:
            if fired.is_set():
                sock.close()
                raise late
            live[:] = [sock]

    def connect() -> None:
        # Not create_connection: its socket is its own until it returns, so
        # cut() could not reach it, and each address it tries gets the whole
        # bound (three unreachable ones, three bounds; re-review of
        # b1378227..2abf77c4). Each attempt here gets what is left.
        err: OSError | None = None
        for family, kind, proto, _, addr in socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80),
                                                               type=socket.SOCK_STREAM):
            sock = socket.socket(family, kind, proto)
            try:
                use(sock)
                sock.settimeout(remaining())
                sock.connect(addr)
                break
            except ApiError:
                sock.close()
                raise
            except OSError as e:
                sock.close()
                if fired.is_set():
                    raise late from None
                err = e
        else:
            raise err or OSError(f"no address for {u.hostname}")
        if u.scheme == "https":
            tls = ssl.create_default_context().wrap_socket(sock, server_hostname=u.hostname, do_handshake_on_connect=False)
            use(tls)
            tls.settimeout(remaining())
            tls.do_handshake()
            sock = tls
        sock.settimeout(remaining())
        conn.sock = sock
    deadline = time.monotonic() + bound
    timer = threading.Timer(max(0.001, bound), cut)
    timer.daemon = True
    timer.start()
    target = u.path or "/"
    if u.query:
        target += "?" + u.query
    try:
        connect()
        conn.request(method, target, body=None if body is None else body.encode("utf-8"),
                     headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json", **(headers or {})})
        resp = conn.getresponse()
        data = resp.read()
    except ApiError:
        raise
    except (OSError, http.client.HTTPException) as e:
        if fired.is_set() or isinstance(e, TimeoutError):
            raise late from None
        raise ApiError(f"{path_and_query} -> {e}") from None
    finally:
        timer.cancel()
        conn.close()
        for sock in live:
            # A socket that never became the connection's (a TLS handshake
            # that failed) is closed here, not left to the collector.
            if sock is not conn.sock:
                sock.close()
    if fired.is_set():
        raise late
    if not 200 <= resp.status < 300:
        raise ApiError(f"{path_and_query} -> HTTP {resp.status}", status=resp.status)
    return json.loads(data.decode("utf-8"))


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
