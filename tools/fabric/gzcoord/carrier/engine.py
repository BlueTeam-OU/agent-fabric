"""tools/fabric/gzcoord/carrier/engine.py — the carrier of ADR-064: what one
account's long-lived process does between its daemon's data socket and the
adapters. The contract is communication/gzcoord/docs/CARRIER-CONTRACT.md
(the framing is framing.py, the delivery record record.py, the roster
roster.py, the arrival files arrivals.py).

The engine holds no sockets of its own: a `connect` callable gives it an
ipc.Session, so a test drives it with a fake daemon and the process with the
real one. Time is an input (`clock` for the schedule, `iso_now` for lines).

FAILURE CLASSES it keeps apart:
  daemon down / session lost   reconnect (1 s doubling to 30 s), a fresh
                               lease; deliveries stay outstanding
  refusal a retry can mend     the delivery's next attempt is scheduled
  refusal no retry mends       recorded on the delivery as blocked, retried
                               on the long schedule: never given up
  roster lacks the recipient   blocked 'NotInRoster' (a removed login's
                               messages wait for its operator)
  copy that cannot be read     dropped and counted, no receipt: the sender
                               retries and a bad sender stays visible
  journal cannot keep it       no receipt: the sender retries
"""
from __future__ import annotations

import hashlib
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from .. import gzmsg
from . import CARRIER_NAME, arrivals, framing, ipc, record, roster

# After an Overloaded refusal nothing is sent for this long: the receiving
# daemon's ingress bucket for this peer refills at two a second (InterWeave
# ADR-0055 decision 2), so a retry sooner finds it empty again.
OVERLOAD_PAUSE = 0.5
RECONNECT_FIRST = 1.0
RECONNECT_CAP = 30.0
SEND_TIMEOUT = 30.0
MID_RE = re.compile(r"[\x21-\x7e]{1,128}")


def log(msg: str) -> None:
    print(f"gzcoord-carrier: {msg}", file=sys.stderr, flush=True)


@dataclass
class Me:
    agent_id: str
    login: str
    address: str            # <host>/<login>
    slug: str | None        # the role, for TO-ROLE; read per message (a relaunch rebinds it)


@dataclass
class Counters:
    unrostered: int = 0
    unreadable: int = 0
    not_journaled: int = 0
    received: int = 0
    receipts_in: int = 0
    receipts_out: int = 0
    reconnects: int = 0


@dataclass
class Carrier:
    me_fn: Callable[[], Me]
    roster_fn: Callable[[], tuple[roster.Roster, list[dict]]]
    outbox: record.Outbox
    spool: arrivals.Spool
    arrival_log: arrivals.ArrivalLog
    connect: Callable[[], ipc.Session]
    journal: Callable[[str, str], str]          # (text, iso ts) -> "written" | "same" | raises
    parse: Callable[[str], tuple[str | None, dict]]
    for_me: Callable[[dict, dict], bool]
    host: str
    clock: Callable[[], float] = time.monotonic
    iso_now: Callable[[], str] = lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    stop: threading.Event = field(default_factory=threading.Event)
    wake: threading.Event = field(default_factory=threading.Event)
    counters: Counters = field(default_factory=Counters)
    # Anything that changes when the roster file does; polled, and the roster
    # re-verified when it moves (verification runs gpg: not per message).
    roster_stamp: Callable[[], object] = lambda: None

    def __post_init__(self) -> None:
        self.lock = threading.RLock()
        self.reasm = framing.Reassembler()
        self.session: ipc.Session | None = None
        self._encoded: dict[tuple[str, str], list[framing.Payload]] = {}
        self.pause_until = 0.0
        self._stamp = self.roster_stamp()
        self.refresh_roster()

    # -- roster ----------------------------------------------------------
    def refresh_roster(self) -> None:
        """A roster that does not verify, or in which this agent has no valid
        row, leaves the carrier running with NO recipient and admitting no
        inbound, never with the last good roster (ADR-064 rule 2)."""
        try:
            r, good = self.roster_fn()
            if not any(row["agent_id"] == self.me_fn().agent_id for row in good):
                raise roster.RosterError("this agent has no valid row in the roster")
        except Exception as e:  # noqa: BLE001 — whatever stops the roster verifying, the answer is the same: nothing is carried
            log(f"the roster does not verify, carrying nothing: {type(e).__name__}: {e}")
            r = getattr(self, "roster", None)
            good = []
        with self.lock:
            self.roster, self.rows = r, good
            self.by_peer = {row["peer_id"]: row for row in good}
            self.by_login = {row["login"]: row for row in good}

    # -- the adapters' calls ---------------------------------------------
    def recipients(self, meta: dict) -> list[str]:
        """Logins of the roster members a message goes to (rule 6)."""
        me = self.me_fn()
        with self.lock:
            others = [row["login"] for row in sorted(self.rows, key=lambda r: r["port"])
                      if row["agent_id"] != me.agent_id]
        if "TO" in meta and meta.get("BROADCAST") != "true":
            host, _, login = meta["TO"].partition("/")
            return [login] if host == self.host and login in others else []
        return others

    def send(self, mid: str, text: str) -> dict:
        _, meta = self.parse(text)
        if meta.get("MESSAGE-ID") != mid:
            raise ValueError("MESSAGE-ID is not the message's own")
        payloads = framing.encode(mid, text)
        to = self.recipients(meta)
        problem = None
        with self.lock:
            queued = 0
            for login in to:
                try:
                    d = self.outbox.queue(mid, login, text, len(payloads), framing.encoding_of(payloads))
                except (record.RecordError, OSError) as e:
                    # The records already written stay: they are durable and will be sent.
                    problem = f"{login}: {e}"
                    break
                self._encoded[d.key] = payloads
                queued += 1
            posted = sum(1 for login in to if self.outbox.deliveries.get((mid, login)) is not None
                         and self.outbox.deliveries[(mid, login)].posted)
        self.wake.set()
        out = {"carried": len(to), "queued": queued, "posted": posted}
        if problem:
            out["problem"] = problem
        return out

    def abandon(self, mid: str, recipient: str, by: str) -> bool:
        with self.lock:
            self._encoded.pop((mid, recipient), None)
            return self.outbox.abandon(mid, recipient, by)

    def status(self) -> dict:
        with self.lock:
            now = self.clock()
            pending = self.outbox.outstanding()
            out = [{"mid": d.mid, "to": d.to, "posted": d.posted, "blocked": d.blocked,
                    "attempts": d.attempts, "queued_at": d.queued_at} for d in pending]
            per: dict[str, dict] = {}
            for d in pending:
                p = per.setdefault(d.to, {"outstanding": 0, "blocked": {}, "awaiting_receipt": 0, "oldest": d.queued_at})
                p["outstanding"] += 1
                if d.blocked:
                    p["blocked"][d.blocked] = p["blocked"].get(d.blocked, 0) + 1
                if d.posted:
                    p["awaiting_receipt"] += 1
                p["oldest"] = min(p["oldest"], d.queued_at)
            return {"outstanding": out, "recipients": per, "counters": self.counters.__dict__.copy(),
                    "connected": bool(self.session and self.session.alive), "now": now}

    def handle_request(self, req: dict) -> dict:
        """The adapter channel's ops (CARRIER-CONTRACT.md §6)."""
        op = req["op"]
        if op == "send":
            mid, text = req["message_id"], req["text"]
            if not isinstance(mid, str) or not isinstance(text, str):
                raise TypeError("message_id and text are strings")
            try:
                out = self.send(mid, text)
            except framing.FramingError as e:
                return {"ok": False, "error": str(e)}
            # ok:true is every recipient durable; a partly durable call is ok:false
            # with its count, and what was written stays (CARRIER-CONTRACT.md §6).
            if out["queued"] != out["carried"]:
                return {"ok": False, "error": f"only {out['queued']} of {out['carried']} recipients recorded: "
                                              f"{out.get('problem', 'unknown')}", **{k: v for k, v in out.items() if k != 'problem'}}
            return {"ok": True, **out}
        if op == "unseen":
            return {"ok": True, "records": self.spool.unseen()}
        if op == "status":
            return {"ok": True, **self.status()}
        if op == "abandon":
            return {"ok": True, "abandoned": self.abandon(str(req["message_id"]), str(req["recipient"]),
                                                             str(req["by"]))}
        return {"ok": False, "error": f"unknown op {op!r}"}

    # -- sending ---------------------------------------------------------
    def send_due(self, session: ipc.Session) -> None:
        with self.lock:
            if self.clock() < self.pause_until:
                return
            due = self.outbox.due(self.clock())
        for d in due:
            if self.stop.is_set():
                return
            with self.lock:
                row = self.by_login.get(d.to)
                payloads = self._encoded.get(d.key) or framing.encode(d.mid, d.text)
                self._encoded[d.key] = payloads
            if row is None or self.roster is None:
                with self.lock:
                    self.outbox.blocked(d, "NotInRoster")
                    self.outbox.retry_after(d, self.clock())
                continue
            try:
                for tmid, p in zip(d.tmids, payloads):
                    session.direct_send(row["peer_id"], self.roster.endpoint, tmid, p.media_type, p.data,
                                        timeout=SEND_TIMEOUT)
            except ipc.IpcTimeout:
                # Unknown outcome: the same transport ids go again, which the
                # receiving daemon collapses inside its window.
                with self.lock:
                    self.outbox.retry_after(d, self.clock())
                continue
            except ipc.IpcError as e:
                if e.session_lost:
                    raise
                with self.lock:
                    if not e.retryable:
                        self.outbox.blocked(d, e.code)
                    self.outbox.retry_after(d, self.clock())
                if e.code == "Overloaded":
                    self.pause_until = self.clock() + OVERLOAD_PAUSE
                    return
                continue
            with self.lock:
                self.outbox.posted(d)
                self.outbox.retry_after(d, self.clock())

    # -- receiving -------------------------------------------------------
    def handle_event(self, session: ipc.Session, event: dict) -> None:
        msg = ipc.inbound(event)
        if msg is None:
            return
        with self.lock:
            row = self.by_peer.get(msg["source_peer"])
        if row is None:
            self.counters.unrostered += 1       # never admitted (rule 9, by rule 2)
            return
        base = msg["media_type"].partition(";")[0]
        try:
            if base == framing.MEDIA_RECEIPT:
                mid = msg["data"].decode("utf-8")
                if MID_RE.fullmatch(mid):
                    with self.lock:
                        if self.outbox.receipt(mid, row["login"]):
                            self.counters.receipts_in += 1
                return
            if base == framing.MEDIA_MESSAGE:
                text = framing.decode_message(msg["media_type"], msg["data"])
            elif base == framing.MEDIA_CHUNK:
                done = self.reasm.add(msg["source_peer"], msg["data"])
                if done is None:
                    return
                text = done[1]
            else:
                self.counters.unreadable += 1
                return
        except (framing.FramingError, UnicodeDecodeError) as e:
            self.counters.unreadable += 1
            log(f"a copy from {row['login']} could not be read: {e}")
            return
        self.finish(session, row, text)

    def _handle_guarded(self, session: ipc.Session, ev: dict) -> None:
        """One copy that breaks the handler must not end the carrier: it earns
        no receipt (the sender's retry shows it again), and the line says why."""
        try:
            self.handle_event(session, ev)
        except ipc.IpcError:
            raise
        except Exception as e:  # noqa: BLE001 — logged with its class; no receipt was sent for this copy
            self.counters.unreadable += 1
            log(f"a copy broke the handler, no receipt: {type(e).__name__}: {e}")

    def finish(self, session: ipc.Session, row: dict, text: str) -> None:
        me = self.me_fn()
        try:
            mtype, meta = self.parse(text)
        except ValueError as e:
            self.counters.unreadable += 1
            log(f"a copy from {row['login']} is not a GZCOORD/1 message: {e}")
            return
        if mtype in gzmsg.RETIRED_TYPES:
            # Presence never enters a journal or an inbox, whichever carrier brings it (ADR-041
            # rule 2); the relay acknowledges it unshown. The sender still gets its receipt.
            mid_r = meta.get("MESSAGE-ID")
            if mid_r:
                self.send_receipt(session, row, mid_r)
            return
        mid = meta.get("MESSAGE-ID") or "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
        verdict = "ok" if meta.get("FROM") == f"{self.host}/{row['login']}" else "mismatch"
        self.counters.received += 1
        if self.for_me({"metadata": meta}, {"address": me.address, "slug": me.slug}):
            # A line per copy ADDRESSED here, as the relay's inbox writes, and before
            # the journal: it collapses repeats, the log keeps them. A copy this agent
            # only filters out (a TO-ROLE it does not hold) is no pair of the report.
            self.arrival_log.append(mid, me.address, CARRIER_NAME, verdict)
            try:
                ts = self.iso_now()
                self.journal(text, ts)
            except Exception as e:  # noqa: BLE001 — a journal that cannot keep it is a refusal to receipt
                self.counters.not_journaled += 1
                log(f"the journal could not keep {mid}: {type(e).__name__}: {e}")
                return
            # Every addressed arrival is listed by `unseen` until the shown ledger settles
            # it: whether it is SHOWN is the ledger's to say, not the journal's outcome.
            self.spool.keep(mid, text, ts, verdict, f"{self.host}/{row['login']}")
        self.send_receipt(session, row, mid)

    def send_receipt(self, session: ipc.Session, row: dict, mid: str) -> None:
        import secrets
        try:
            session.direct_send(row["peer_id"], self.roster.endpoint, secrets.token_hex(16),
                                framing.MEDIA_RECEIPT, mid.encode("utf-8"), timeout=SEND_TIMEOUT)
            self.counters.receipts_out += 1
        except ipc.IpcError as e:
            if e.session_lost:
                raise
            # A receipt that did not go is the sender's retry: it resends the
            # message and this side answers again without a second append.
            log(f"receipt for {mid} to {row['login']} not accepted: {e.code}")
        except ipc.IpcTimeout:
            log(f"receipt for {mid} to {row['login']} not answered")

    # -- the loop --------------------------------------------------------
    def serve_session(self, session: ipc.Session) -> None:
        self.session = session
        while session.alive and not self.stop.is_set():
            stamp = self.roster_stamp()
            if stamp != self._stamp:
                self._stamp = stamp
                self.refresh_roster()
            self.send_due(session)
            try:
                ev = session.events.get(timeout=0.2)
            except Exception:  # queue.Empty
                ev = False
            if ev is None:
                return
            while ev:
                self._handle_guarded(session, ev)
                try:
                    ev = session.events.get_nowait()
                except Exception:
                    ev = False
                if ev is None:
                    return
        self.session = None

    def run(self) -> None:
        delay = RECONNECT_FIRST
        while not self.stop.is_set():
            try:
                session = self.connect()
            except ipc.IpcError as e:
                if e.code in ("EndpointInUse", "EndpointClientKindDenied", "EndpointUnknown",
                              "EndpointDisabled", "CapabilityDenied", "VersionIncompatible"):
                    # Not a daemon that is down: another holder, or a profile that does not allow us.
                    log(f"the daemon refused the lease: {e}")
                else:
                    log(f"no session: {e}")
                self.stop.wait(delay)
                delay = min(delay * 2, RECONNECT_CAP)
                continue
            delay = RECONNECT_FIRST
            self.counters.reconnects += 1
            try:
                self.serve_session(session)
            except ipc.IpcError as e:
                log(f"session lost: {e}")
            finally:
                session.close()
                self.session = None
