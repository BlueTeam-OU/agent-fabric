"""tools/fabric/gzcoord/carrier/ipc.py — a client of an InterWeave daemon's
DATA socket, IPC v2 (InterWeave architecture/contracts/LOCAL-IPC.md; shapes
under architecture/contracts/schemas/ipc/, read at its origin/main).

CONTRACT: the frame is a 4-byte big-endian length (1..131072) and that many
bytes of UTF-8 JSON. The first frame is `hello`; the answer is
`hello_response` or `close`. The client claims one endpoint (the lease),
offers `keepalive`, asks `events` and `commands`, and never `admin.*`: the
carrier does not open the admin socket (ADR-064 rule 5). After that one
thread reads every frame: a response goes to the request waiting for its id,
an event to `events`, a `ping` is answered with the same nonce at once (a
client that stops answering is closed by the daemon as wedged, and loses its
lease), `close` and a read error end the session. A session that has ended
is never reused: the caller opens another, which is a fresh lease and a fresh
`hello` (there is no event replay).

Failure classes the caller tells apart: IpcError(code) for an answer the
daemon gave (`code` is its closed vocabulary), SessionLost for a session that
is gone (retry on a new one), IpcTimeout for a request no answer came to
(unknown outcome). The silence timer of LOCAL-IPC.md §Keepalive (120 s with
no frame read, armed at the first ping) is kept.
"""
from __future__ import annotations

import base64
import binascii
import json
import queue
import re
import socket
import struct
import threading
import time
from typing import Callable

MAX_FRAME = 131072
_B64U = re.compile(r"[A-Za-z0-9_-]*")
IPC_VERSION = {"major": 2, "minor": 0}
SILENCE_TIMEOUT = 120.0
# Error codes of the daemon that mean "the session is gone", not "the send
# failed" (ADR-0055 decision 2).
SESSION_CODES = frozenset({"BackendUnavailable", "ShuttingDown"})
# A refusal a later attempt under the same message_id can mend (ADR-0055
# decision 2); anything else is the sender's to see.
RETRYABLE_CODES = frozenset({"RemoteEndpointUnavailable", "PeerUnreachable", "PeerUnknown",
                             "Overloaded", "Timeout"})


class IpcError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code
        self.message = message

    @property
    def retryable(self) -> bool:
        return self.code in RETRYABLE_CODES

    @property
    def session_lost(self) -> bool:
        return self.code in SESSION_CODES


class SessionLost(IpcError):
    def __init__(self, message: str = "") -> None:
        super().__init__("BackendUnavailable", message)


class IpcTimeout(Exception):
    """No answer within the caller's bound: the request may have been acted on."""


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def unb64u(text: str) -> bytes:
    # b64decode drops characters outside the alphabet unless told to refuse
    # them; a payload with any is not the unpadded base64url the schema fixes.
    if not isinstance(text, str) or _B64U.fullmatch(text) is None or len(text) % 4 == 1:
        raise ValueError("payload is not unpadded base64url")
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError) as e:
        raise ValueError("payload is not base64url") from e


def write_frame(sock: socket.socket, obj: dict) -> None:
    body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    if not 0 < len(body) <= MAX_FRAME:
        raise ValueError("frame past the ceiling")
    sock.sendall(struct.pack(">I", len(body)) + body)


def _read_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise EOFError("daemon closed the socket")
        buf += chunk
    return bytes(buf)


def read_frame(sock: socket.socket) -> dict:
    (n,) = struct.unpack(">I", _read_exact(sock, 4))
    if not 0 < n <= MAX_FRAME:
        raise ValueError(f"frame length {n} is outside 1..{MAX_FRAME}")
    obj = json.loads(_read_exact(sock, n).decode("utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("frame is not an object")
    return obj


class Session:
    """One lease on one data socket."""

    def __init__(self, sock: socket.socket, hello: dict, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._sock = sock
        self.hello = hello
        self.peer: str = hello["peer"]
        self.endpoint: str | None = hello.get("endpoint")
        self.events: queue.Queue = queue.Queue()
        self.end_reason: str | None = None
        self._clock = clock
        self._wlock = threading.Lock()
        self._lock = threading.Lock()
        self._waiting: dict[str, queue.Queue] = {}
        self._next = 0
        self._last_read = clock()
        self._pinged = False
        self._reader = threading.Thread(target=self._read_loop, name="ipc-reader", daemon=True)
        self._reader.start()

    @classmethod
    def open(cls, path: str, *, endpoint: str, kind: str, version: str = "1",
             timeout: float = 10.0) -> "Session":
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(path)
            write_frame(sock, {"type": "hello", "ipc_version": IPC_VERSION,
                               "client": {"kind": kind, "version": version},
                               "endpoint": {"id": endpoint},
                               "requested_capabilities": ["events", "commands"],
                               "features": ["keepalive"]})
            reply = read_frame(sock)
        except (OSError, EOFError, ValueError) as e:
            sock.close()
            raise SessionLost(f"hello failed: {e}") from e
        if reply.get("type") == "close" or reply.get("type") != "hello_response":
            sock.close()
            code = reply.get("code") if reply.get("type") == "close" else "ProtocolViolation"
            raise IpcError(str(code), str(reply.get("message", "")))
        if reply.get("endpoint") != endpoint or "peer" not in reply:
            sock.close()
            raise IpcError("ProtocolViolation", "hello_response without the claimed endpoint")
        sock.settimeout(None)
        return cls(sock, reply)

    # -- reading ---------------------------------------------------------
    def _read_loop(self) -> None:
        reason = "closed"
        try:
            while True:
                self._sock.settimeout(SILENCE_TIMEOUT if self._pinged else None)
                try:
                    frame = read_frame(self._sock)
                except socket.timeout:
                    reason = "Timeout"
                    break
                self._last_read = self._clock()
                kind = frame.get("type")
                if kind == "ping" and isinstance(frame.get("nonce"), str):
                    self._pinged = True
                    self._send({"type": "pong", "nonce": frame["nonce"]})
                elif kind == "response":
                    with self._lock:
                        box = self._waiting.pop(frame.get("id"), None)
                    if box is not None:
                        box.put(frame)
                elif kind == "event":
                    self.events.put(frame)
                elif kind == "close":
                    reason = str(frame.get("code", "closed"))
                    break
                # server_state and anything else carries nothing the carrier acts on
        except (OSError, EOFError, ValueError) as e:
            reason = f"{type(e).__name__}: {e}"
        self.end_reason = reason
        with self._lock:
            waiting, self._waiting = self._waiting, {}
        for box in waiting.values():
            box.put(None)
        self.events.put(None)
        try:
            self._sock.close()
        except OSError:
            pass

    def _send(self, obj: dict) -> None:
        with self._wlock:
            write_frame(self._sock, obj)

    @property
    def alive(self) -> bool:
        return self.end_reason is None

    # -- requests --------------------------------------------------------
    def request(self, method: str, params: dict, timeout: float = 30.0) -> dict:
        if not self.alive:
            raise SessionLost(self.end_reason or "")
        with self._lock:
            self._next += 1
            rid = f"r{self._next}"
            box: queue.Queue = queue.Queue(maxsize=1)
            self._waiting[rid] = box
        try:
            self._send({"type": "request", "id": rid, "method": method, "params": params})
        except OSError as e:
            with self._lock:
                self._waiting.pop(rid, None)
            raise SessionLost(str(e)) from e
        try:
            frame = box.get(timeout=timeout)
        except queue.Empty:
            with self._lock:
                self._waiting.pop(rid, None)
            raise IpcTimeout(method) from None
        if frame is None:
            raise SessionLost(self.end_reason or "")
        if frame.get("ok") is True:
            result = frame.get("result", {})
            return result if isinstance(result, dict) else {}
        err = frame.get("error") or {}
        raise IpcError(str(err.get("code", "Internal")), str(err.get("message", "")))

    def direct_send(self, peer: str, endpoint: str, message_id: str, media_type: str, data: bytes,
                    timeout: float = 30.0) -> str:
        """One direct send; the endpoint it resolved to. AcceptedV2 is queue
        admission at the receiver, never delivery (ADR-0055 decision 2)."""
        result = self.request("direct.send", {
            "peer": peer, "endpoint": endpoint, "message_id": message_id,
            "payload": {"media_type": media_type, "bytes": b64u(data)}}, timeout)
        return str(result.get("resolved_endpoint", endpoint))

    def close(self) -> None:
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass
        self._reader.join(timeout=5)


def inbound(event: dict) -> dict | None:
    """The direct message an event carries: source_peer, source_endpoint,
    message_id, media_type, data; None for any other event. A malformed
    message event is dropped here, never half-read."""
    if event.get("event_type") != "message.direct":
        return None
    d = event.get("data")
    try:
        payload = d["payload"]
        return {"source_peer": d["source_peer"], "source_endpoint": d["source_endpoint"],
                "message_id": d["message_id"], "media_type": payload.get("media_type", ""),
                "data": unb64u(payload["bytes"])}
    except (KeyError, TypeError, ValueError):
        return None
