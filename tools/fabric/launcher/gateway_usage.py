"""tools/fabric/launcher/gateway_usage.py — the gateway's subscription usage, relayed to where the fabric reads it
(gateway-switch s11, the gateway repository's plan-v0 README "Usage (s11)").

The gateway reads `anthropic-ratelimit-unified-*` off each upstream response and answers `{"op":"usage"}` on the
control descriptor it was started with, which only this launcher holds. So the launcher asks, on a timer, and
writes the answer whole to <state>/gateway-usage.json; `fabric-ctl <login> gateway` and `fabric-usage` read that
file. Never gateway.json (the session record) or gateway-install.json (the install marker).

THE FILE, written by rename, mode 0600:
  {"version": 1, "gateway_pid": N, "fetched_at": "<UTC, ms>", "credentials": [<the gateway's entries, verbatim>]}
  or, when the last ask could not be answered,
  {"version": 1, "gateway_pid": N, "fetched_at": "...", "error": "<why>"}  — no `credentials`, so an old reading
  is never shown beside a failure. The entries carry what the contract says they carry (a source's path or profile
  id, a generation, a reading or null, never a credential); the reader decides how old is too old from fetched_at.

THE CHANNEL is one request line, one reply line (newline-ended JSON), strictly in turn. A reply that does not
arrive in time, is too long, is not one line of JSON or not a usage event leaves the channel out of step with
the gateway (the late reply would answer the next ask), so the relay says why in the file and stops asking: it
does not guess at resynchronising. The gateway and the session are not affected; the file says it stopped.

This module never sends an activation and never a request on the session's behalf: usage is read-only.
"""
from __future__ import annotations

import datetime
import json
import os
import socket
import threading
from typing import Callable

FILE = "gateway-usage.json"
REQUEST = b'{"op":"usage"}\n'
INTERVAL_S = 60.0
IO_TIMEOUT_S = 10.0
# 256 sources at the contract's bound, each a few hundred bytes.
REPLY_MAX_BYTES = 1 << 20
VERSION = 1


class OutOfStep(Exception):
    """The channel can no longer be trusted to answer the next ask with its own reply."""


def ask(control: socket.socket, timeout: float = IO_TIMEOUT_S) -> list[dict]:
    """One usage ask: the gateway's entries. OutOfStep for anything but one line that is a usage event."""
    try:
        control.settimeout(timeout)
        control.sendall(REQUEST)
        line = bytearray()
        while True:
            chunk = control.recv(65536)
            if not chunk:
                raise OutOfStep("the gateway closed its control channel")
            line += chunk
            if b"\n" in chunk:
                break
            if len(line) > REPLY_MAX_BYTES:
                raise OutOfStep(f"the reply is longer than {REPLY_MAX_BYTES} bytes")
    except socket.timeout:
        raise OutOfStep(f"no reply within {timeout:g} s") from None
    except OSError as exc:
        raise OutOfStep(f"the control channel failed ({exc.strerror or exc})") from None
    head, _, rest = bytes(line).partition(b"\n")
    if rest:
        raise OutOfStep("more than one line came back for one ask")
    if len(head) > REPLY_MAX_BYTES:
        raise OutOfStep(f"the reply is longer than {REPLY_MAX_BYTES} bytes")
    try:
        doc = json.loads(head.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise OutOfStep("the reply is not JSON") from None
    if not isinstance(doc, dict) or doc.get("event") != "usage":
        event = doc.get("event") if isinstance(doc, dict) else None
        # A refusal ({"event":"refused",...}) is still one reply to one ask: the channel is in step, the answer is not usable.
        raise OutOfStep(f"the reply is not a usage event ({event!r})")
    entries = doc.get("credentials")
    if not isinstance(entries, list) or not all(isinstance(e, dict) and isinstance(e.get("source"), dict) for e in entries):
        raise OutOfStep("the usage event's credentials are not a list of sources")
    return entries


def now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def write(state_dir: str, doc: dict) -> str | None:
    """Atomic; the reason it could not, else None."""
    path = os.path.join(state_dir, FILE)
    tmp = f"{path}.tmp-{os.getpid()}"
    try:
        os.makedirs(state_dir, exist_ok=True)
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return exc.strerror or str(exc)
    return None


def forget(state_dir: str, pid: int) -> None:
    """Remove the file, but only if it is this gateway's: a second launch of the login has written its own."""
    path = os.path.join(state_dir, FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            if json.load(fh).get("gateway_pid") != pid:
                return
        os.unlink(path)
    except (OSError, ValueError, AttributeError):
        pass


class Relay:
    """Asks on a timer from a thread of its own; the only user of `control` while it runs."""

    def __init__(self, control: socket.socket, pid: int, state_dir: str, *, interval: float = INTERVAL_S,
                 timeout: float = IO_TIMEOUT_S, now: Callable[[], str] = now_utc,
                 say: Callable[[str], None] = lambda text: None):
        self.control, self.pid, self.state_dir = control, pid, state_dir
        self.interval, self.timeout, self.now, self.say = interval, timeout, now, say
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="gateway-usage", daemon=True)
        self.stopped_on: str | None = None
        self._write_failed = False

    def poll(self) -> bool:
        """One ask and one write. False when the channel is out of step (nothing more should be asked)."""
        doc: dict = {"version": VERSION, "gateway_pid": self.pid, "fetched_at": self.now()}
        try:
            doc["credentials"] = ask(self.control, self.timeout)
            ok = True
        except OutOfStep as exc:
            doc["error"] = f"{exc}; the relay has stopped asking"
            self.stopped_on, ok = str(exc), False
        failed = write(self.state_dir, doc)
        if failed and not self._write_failed:
            self.say(f"launch: could not write {os.path.join(self.state_dir, FILE)}: {failed}")
        self._write_failed = bool(failed)
        return ok

    def _run(self) -> None:
        while not self._stop.is_set():
            if not self.poll():
                return
            self._stop.wait(self.interval)

    def start(self) -> "Relay":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        # An ask in flight (a gateway that does not answer) would hold the end of the session for its timeout.
        try:
            self.control.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass   # already closed
        if self._thread.is_alive():
            self._thread.join(self.timeout + 1)
