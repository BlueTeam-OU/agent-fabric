#!/usr/bin/env python3
"""tools/fabric/gzcoord/carrier/engine.py (ADR-064 rules 5-9) with two or
three engines joined by fake daemons (tests/interweave_fake.py): a send is
done on the recipient's receipt and not on the daemon's acceptance; a loss
the daemon cannot see is resent under the same transport id and journaled
once; TO-ROLE and broadcast are receipted by members that filter them; an
unreadable copy, an unrostered sender and a journal that fails earn no
receipt and no admission; FROM against the roster is a verdict; a lost
session is reopened; a roster that does not verify carries nothing. Plain
script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from gzcoord.carrier import arrivals, engine, framing, ipc, record, roster  # noqa: E402
from gzcoord.inbox_parts.tokens import for_me  # noqa: E402
from interweave_fake import FakeDaemon  # noqa: E402

fails = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def until(cond, seconds: float = 8.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def parse(text: str):
    first, _, rest = text.partition("\n")
    if not first.startswith("[GZCOORD/1] "):
        raise ValueError("not a GZCOORD/1 message")
    meta = {}
    for line in rest.split("\n"):
        if not line.strip():
            break
        k, _, v = line.partition(": ")
        meta[k] = v
    return first[12:], meta


def msg(mid: str, frm: str, *, to: str | None = None, to_role: str | None = None, broadcast=False,
        body: str = "hello") -> str:
    addr = f"TO: {to}\n" if to else f"TO-ROLE: {to_role}\n" if to_role else "BROADCAST: true\n" if broadcast else ""
    return f"[GZCOORD/1] INFO\nFROM: {frm}\nROLE: r\n{addr}MESSAGE-ID: {mid}\nSUBJECT: s\n\nCONTEXT:\n{body}\n"


def receipts_for(node, mid: str) -> int:
    """How many receipts this node's daemon was asked to send for `mid`."""
    return sum(1 for s in node.daemon.sends if s["payload"]["media_type"] == framing.MEDIA_RECEIPT
               and ipc.unb64u(s["payload"]["bytes"]).decode() == mid)


def gone(node, mid: str, to: str) -> bool:
    """The delivery is done (receipt or abandon), not merely absent."""
    d = node.box.deliveries.get((mid, to))
    return d is not None and d.receipt_at is not None


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def pid(n: int) -> str:
    return f"12D3KooWFake{n:040d}"[:52]


class Node:
    def __init__(self, root: str, login: str, n: int, slug: str, rows: list[dict], clock: Clock,
                 journal_fail: list | None = None) -> None:
        self.login, self.slug, self.clock = login, slug, clock
        d = os.path.join(root, login)
        os.makedirs(d)
        self.daemon = FakeDaemon(d, peer=pid(n))
        self.journal_rows: list[tuple[str, str]] = []
        self.already: set[str] = set()        # ids the relay's inbox journaled first: the journal answers "same"
        self.arrivals_when_journaled: dict[str, int] = {}     # how many arrival lines existed when the journal was called
        self.journal_fail = journal_fail if journal_fail is not None else [False]
        iso = lambda: "2026-10-24T12:00:00Z"  # noqa: E731
        self.rows = rows
        self.me = engine.Me(f"agent-{login}", login, f"h/{login}", slug)
        self.box = record.Outbox(os.path.join(d, "iw"), iso_now=iso)
        self.ledger_path = os.path.join(d, "gzcoord-shown.jsonl")
        self.spool = arrivals.Spool(os.path.join(d, "iw"), self.ledger_path, iso_now=iso)
        self.log = arrivals.ArrivalLog(os.path.join(d, "arrivals.jsonl"), iso_now=iso)
        self.roster_ok = [True]
        self.carrier = engine.Carrier(
            me_fn=lambda: self.me, roster_fn=self._roster, outbox=self.box, spool=self.spool, arrival_log=self.log,
            connect=lambda: ipc.Session.open(self.daemon.path, endpoint="gzcoord", kind="automated-client"),
            journal=self._journal, parse=parse, for_me=for_me, host="h", clock=clock, iso_now=iso)
        self.thread = threading.Thread(target=self.carrier.run, daemon=True)

    def _roster(self):
        if not self.roster_ok[0]:
            raise roster.RosterError("does not verify")
        if getattr(self, "roster_breaks", False):
            raise OSError("git could not run")
        return roster.Roster("gzcoord", "gzcoord", (47100, 47199), tuple(self.rows)), self.rows

    def _journal(self, text: str, ts: str) -> str:
        if self.journal_fail[0]:
            raise OSError("journal is held")
        _, meta = parse(text)
        self.arrivals_when_journaled.setdefault(meta["MESSAGE-ID"], len(self.arrivals()))
        if meta["MESSAGE-ID"] in self.already:
            return "same"
        key = (meta["MESSAGE-ID"], text)
        if key in self.journal_rows:
            return "same"
        self.journal_rows.append(key)
        return "written"

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.carrier.stop.set()
        self.thread.join(timeout=10)
        self.daemon.close()
        self.box.close()

    def arrivals(self) -> list[dict]:
        try:
            return [json.loads(l) for l in open(self.log.path)]
        except FileNotFoundError:
            return []


def mkrows(names: list[str]) -> list[dict]:
    return [{"agent_id": f"agent-{n}", "login": n, "peer_id": pid(i), "endpoint": "gzcoord", "port": 47100 + i,
             "identity_show": "", "login_signature": "", "countersignature": ""} for i, n in enumerate(names)]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gz-eng-") as d:
        clock = Clock()
        rows = mkrows(["alpha", "beta", "gamma"])
        a = Node(d, "alpha", 0, "dev", rows, clock)
        b = Node(d, "beta", 1, "dev", rows, clock)
        c = Node(d, "gamma", 2, "ops", rows, clock)
        nodes = [a, b, c]
        full = {pid(0): a.daemon, pid(1): b.daemon, pid(2): c.daemon}
        for n in nodes:
            n.daemon.routes = dict(full)
        try:
            for n in nodes:
                n.start()
            check("every engine holds its lease with the carrier's hello",
                  until(lambda: all(n.carrier.session is not None for n in nodes))
                  and all(n.daemon.hellos[0]["endpoint"] == {"id": "gzcoord"} for n in nodes))

            # -- a direct send: done on the receipt ------------------------
            m1 = msg("M-1", "h/alpha", to="h/beta")
            res = a.carrier.handle_request({"op": "send", "message_id": "M-1", "text": m1})
            check("send answers with the recipients carried and durably queued",
                  res["ok"] and res["carried"] == 1 and res["queued"] == 1, str(res))
            check("beta journals it once and alpha's delivery ends on beta's receipt",
                  until(lambda: gone(a, "M-1", "beta")) and len(b.journal_rows) == 1,
                  f"{a.carrier.status()} {b.carrier.status()} {b.journal_rows}")
            check("the arrival is logged with the verdict ok, before the journal",
                  [(x["mid"], x["carrier"], x["verdict"], x["addressee"]) for x in b.arrivals()]
                  == [("M-1", "interweave", "ok", "h/beta")])
            check("the arrival line was already written when the journal was called (rule 11: before it collapses the copy)",
                  b.arrivals_when_journaled.get("M-1") == 1, str(b.arrivals_when_journaled))
            check("the arrival is offered to the inbox", [r["message_id"] for r in b.carrier.handle_request({"op": "unseen"})["records"]] == ["M-1"])
            sent = a.daemon.sends[0]
            check("the transport message_id is 32 hex and the endpoint the roster's",
                  len(sent["message_id"]) == 32 and sent["endpoint"] == "gzcoord" and sent["peer"] == pid(1))

            # -- AcceptedV2 is not delivery -------------------------------
            a.daemon.routes = {}                                  # accepted, never delivered
            m2 = msg("M-2", "h/alpha", to="h/beta")
            a.carrier.handle_request({"op": "send", "message_id": "M-2", "text": m2})
            check("accepted by the daemon is posted, and still outstanding without a receipt",
                  until(lambda: a.box.deliveries[("M-2", "beta")].posted) and not gone(a, "M-2", "beta"))
            first_id = a.box.deliveries[("M-2", "beta")].tmids[0]
            n_sends = len(a.daemon.sends)
            clock.t += 0.5
            time.sleep(0.5)
            check("it is not resent before its backoff", len(a.daemon.sends) == n_sends)
            a.daemon.routes = dict(full)                          # the loss ends
            clock.t += 2.0
            check("after the backoff it is resent under the SAME transport id and ends on the receipt",
                  until(lambda: gone(a, "M-2", "beta"))
                  and {s["message_id"] for s in a.daemon.sends[n_sends - 1:]} == {first_id})
            check("beta journaled it once", len([r for r in b.journal_rows if r[0] == "M-2"]) == 1)

            # -- a copy that arrives twice: two arrival lines, one row, a receipt each time
            b.carrier.handle_event(b.carrier.session, {"event_type": "message.direct", "data": {
                "message_id": "f" * 32, "mode": "direct", "source_peer": pid(0), "source_endpoint": "gzcoord",
                "destination_endpoint": "gzcoord", "received_at": 0,
                "payload": {"media_type": framing.MEDIA_MESSAGE, "bytes": ipc.b64u(m2.encode())}}})
            lines = [x for x in b.arrivals() if x["mid"] == "M-2"]
            check("a repeat is another arrival line, the journal still one row, and a receipt again",
                  len(lines) >= 2 and len([r for r in b.journal_rows if r[0] == "M-2"]) == 1
                  and b.carrier.counters.receipts_out >= 3)

            # -- TO-ROLE and broadcast ------------------------------------
            m3 = msg("M-3", "h/alpha", to_role="dev")
            a.carrier.handle_request({"op": "send", "message_id": "M-3", "text": m3})
            check("a TO-ROLE message goes to every other member, none to the sender",
                  {x.to for x in a.box.deliveries.values() if x.mid == "M-3"} == {"beta", "gamma"})
            check("the member holding the role journals it, the member that does not only receipts",
                  until(lambda: any(r[0] == "M-3" for r in b.journal_rows))
                  and not any(r[0] == "M-3" for r in c.journal_rows)
                  and until(lambda: not [x for x in a.box.outstanding() if x.mid == "M-3"]))
            check("the filtering member logs no arrival line (it is no addressee of the pair), yet receipted",
                  not any(x["mid"] == "M-3" for x in c.arrivals()) and receipts_for(c, "M-3") == 1)

            # -- verdict ---------------------------------------------------
            b.carrier.handle_event(b.carrier.session, {"event_type": "message.direct", "data": {
                "message_id": "e" * 32, "mode": "direct", "source_peer": pid(0), "source_endpoint": "gzcoord",
                "destination_endpoint": "gzcoord", "received_at": 0,
                "payload": {"media_type": framing.MEDIA_MESSAGE,
                            "bytes": ipc.b64u(msg("M-4", "h/gamma", to="h/beta").encode())}}})
            v = [x for x in b.arrivals() if x["mid"] == "M-4"]
            check("a FROM that is not the sender's roster address is a mismatch verdict",
                  v and v[0]["verdict"] == "mismatch" and any(r["verdict"] == "mismatch" for r in b.spool.unseen()))

            # the relay's copy was journaled first (the usual order): the journal says "same"
            b.already.update({"M-RS1", "M-RS2"})
            for mid_, frm_ in (("M-RS1", "h/gamma"), ("M-RS2", "h/alpha")):
                b.carrier.handle_event(b.carrier.session, {"event_type": "message.direct", "data": {
                    "message_id": mid_.encode().hex()[:32].ljust(32, "0"), "mode": "direct", "source_peer": pid(0),
                    "source_endpoint": "gzcoord", "destination_endpoint": "gzcoord", "received_at": 0,
                    "payload": {"media_type": framing.MEDIA_MESSAGE,
                                "bytes": ipc.b64u(msg(mid_, frm_, to="h/beta").encode())}}})
            kept = {r["message_id"]: r["verdict"] for r in b.spool.unseen()}
            check("every addressed arrival is listed whatever the journal answered: whether it is shown is the ledger's to say",
                  kept.get("M-RS1") == "mismatch" and kept.get("M-RS2") == "ok", str(kept))

            n_rows = len(b.journal_rows)
            b.carrier.handle_event(b.carrier.session, {"event_type": "message.direct", "data": {
                "message_id": "d" * 32, "mode": "direct", "source_peer": pid(9), "source_endpoint": "gzcoord",
                "destination_endpoint": "gzcoord", "received_at": 0,
                "payload": {"media_type": framing.MEDIA_MESSAGE,
                            "bytes": ipc.b64u(msg("M-5", "h/alpha", to="h/beta").encode())}}})
            check("a PeerId absent from the roster is never admitted: counted, no row, no arrival line",
                  b.carrier.counters.unrostered == 1 and len(b.journal_rows) == n_rows
                  and not [x for x in b.arrivals() if x["mid"] == "M-5"])

            # -- a journal that fails -> no receipt -----------------------
            b.journal_fail[0] = True
            a.carrier.handle_request({"op": "send", "message_id": "M-6", "text": msg("M-6", "h/alpha", to="h/beta")})
            until(lambda: b.carrier.counters.not_journaled >= 1)
            time.sleep(0.6)       # a receipt sent in error would be on the wire by now
            check("a journal that cannot keep the message earns no receipt: none is sent, the delivery stays outstanding",
                  receipts_for(b, "M-6") == 0 and not gone(a, "M-6", "beta"), str(receipts_for(b, "M-6")))
            b.journal_fail[0] = False
            clock.t += 400
            check("after the journal recovers the retry is journaled and receipted",
                  until(lambda: gone(a, "M-6", "beta"))
                  and len([r for r in b.journal_rows if r[0] == "M-6"]) == 1)

            # -- big message ------------------------------------------------
            import hashlib
            big = "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(3200))   # ~200 KB, incompressible-ish
            a.carrier.handle_request({"op": "send", "message_id": "M-7", "text": msg("M-7", "h/alpha", to="h/beta", body=big)})
            check("a message past the ceiling is chunked, reassembled, journaled once and receipted",
                  until(lambda: gone(a, "M-7", "beta"))
                  and len([r for r in b.journal_rows if r[0] == "M-7"]) == 1
                  and any(s["payload"]["media_type"] == framing.MEDIA_CHUNK for s in a.daemon.sends)
                  and all(len(ipc.unb64u(s["payload"]["bytes"])) <= framing.CEILING for s in a.daemon.sends))

            # -- refusals ---------------------------------------------------
            a.daemon.send_answers = ["Overloaded"]
            with a.carrier.lock:      # both queued before the engine looks: one round holds both
                a.carrier.handle_request({"op": "send", "message_id": "M-8", "text": msg("M-8", "h/alpha", to="h/beta")})
                a.carrier.handle_request({"op": "send", "message_id": "M-8b", "text": msg("M-8b", "h/alpha", to="h/beta")})
            check("a retryable refusal is retried and then delivered",
                  until(lambda: a.box.deliveries.get(("M-8", "beta")) is not None and a.box.deliveries[("M-8", "beta")].attempts >= 1))
            time.sleep(0.5)
            second = a.box.deliveries[("M-8b", "beta")].tmids
            check("an Overloaded refusal pauses sending: the next recipient waits until the pause has passed",
                  not [x for x in a.daemon.sends if x["message_id"] in second])
            clock.t += engine.OVERLOAD_PAUSE + 0.1
            check("  and is sent once it has", until(lambda: [x for x in a.daemon.sends if x["message_id"] in second]))
            clock.t += 500
            check("  ... both reach their receipt", until(lambda: gone(a, "M-8", "beta") and gone(a, "M-8b", "beta")))
            a.daemon.send_answers = ["UnauthorizedPeer"]
            a.carrier.handle_request({"op": "send", "message_id": "M-9", "text": msg("M-9", "h/alpha", to="h/beta")})
            d9 = a.box.deliveries[("M-9", "beta")]
            check("a refusal no retry mends is recorded as blocked and the delivery stays outstanding",
                  until(lambda: d9.blocked == "UnauthorizedPeer") and d9 in a.box.outstanding())
            check("the operator can end it, and it is recorded who",
                  a.carrier.handle_request({"op": "abandon", "message_id": "M-9", "recipient": "beta", "by": "user"})["abandoned"]
                  and gone(a, "M-9", "beta"))

            # -- a copy that breaks the handler does not end the carrier --------
            real_parse = b.carrier.parse

            def boom_parse(text):
                if "BOOM" in text:
                    raise RuntimeError("a copy that breaks the handler")
                return real_parse(text)
            b.carrier.parse = boom_parse
            before = b.carrier.counters.unreadable
            ev = {"event_type": "message.direct", "data": {
                "message_id": "c" * 32, "mode": "direct", "source_peer": pid(0), "source_endpoint": "gzcoord",
                "destination_endpoint": "gzcoord", "received_at": 0,
                "payload": {"media_type": framing.MEDIA_MESSAGE,
                            "bytes": ipc.b64u(msg("M-BOOM", "h/alpha", to="h/beta", body="BOOM").encode())}}}
            b.carrier._handle_guarded(b.carrier.session, ev)
            b.carrier.parse = real_parse
            check("a copy that breaks the handler is logged and counted, earns no receipt, and the carrier goes on",
                  b.carrier.counters.unreadable == before + 1 and receipts_for(b, "M-BOOM") == 0)

            # -- a call that records only some recipients is not ok:true (the records written stay)
            real_queue = a.box.queue
            n_calls = [0]

            def flaky(*args, **kw):
                n_calls[0] += 1
                if n_calls[0] == 2:
                    raise OSError("disk full")
                return real_queue(*args, **kw)
            a.box.queue = flaky
            res = a.carrier.handle_request({"op": "send", "message_id": "M-PART", "text": msg("M-PART", "h/alpha", broadcast=True)})
            a.box.queue = real_queue
            check("a send that records only some of its recipients is ok:false with the count, and keeps what it wrote",
                  res["ok"] is False and res["carried"] == 2 and res["queued"] == 1 and "disk full" in res["error"]
                  and ("M-PART", "beta") in a.box.deliveries, str(res))
            res = a.carrier.handle_request({"op": "send", "message_id": "M-PART", "text": msg("M-PART", "h/alpha", broadcast=True)})
            check("the same send again completes the rest, without a second record for the first",
                  res["ok"] is True and res["queued"] == 2, str(res))

            # -- an address that is not on the roster ------------------------
            res = a.carrier.handle_request({"op": "send", "message_id": "M-10", "text": msg("M-10", "h/alpha", to="elsewhere/delta")})
            check("an address with no roster row is not carried (relay alone)", res["carried"] == 0 and res["queued"] == 0)
            res = a.carrier.handle_request({"op": "send", "message_id": "M-11", "text": msg("M-11", "h/alpha", to="h/alpha")})
            check("a message to itself is not sent to itself", res["carried"] == 0)

            # -- the lost session -------------------------------------------
            before = len(a.daemon.hellos)
            a.daemon.drop_connections()
            check("a dropped session is reopened with a fresh hello", until(lambda: len(a.daemon.hellos) > before, 15))
            a.carrier.handle_request({"op": "send", "message_id": "M-12", "text": msg("M-12", "h/alpha", to="h/beta")})
            check("and sending continues on it", until(lambda: gone(a, "M-12", "beta"), 15))

            # -- unseen and the shown ledger (the carrier reads it, the inbox writes it) --------
            def ledger_put(mid_: str, via_: str, flagged_: bool = False) -> None:
                from gzcoord.carrier import ledger as Lg
                h = Lg.Ledger(b.ledger_path, iso_now=lambda: "2026-10-24T12:00:00Z").exclusive()
                h.pending(mid_, via_, flagged_)
                h.finish()
            listed = lambda: {r["message_id"]: r["verdict"] for r in b.carrier.handle_request({"op": "unseen"})["records"]}  # noqa: E731
            check("unseen lists a journaled arrival on every call until the ledger settles it",
                  "M-1" in listed() and "M-1" in listed() and "M-4" in listed())
            ledger_put("M-1", "relay")
            check("an ok copy is settled by any final line", "M-1" not in listed() and "M-4" in listed())
            ledger_put("M-4", "relay")
            check("a mismatch copy the relay's final line settled is still listed: it is owed its flagged re-show",
                  listed().get("M-4") == "mismatch")
            ledger_put("M-4", "interweave", True)
            check("... and is settled once the flagged copy's final line is there", "M-4" not in listed())

            # -- a roster that does not verify -------------------------------
            a.roster_breaks = True
            a.carrier.refresh_roster()
            res = a.carrier.handle_request({"op": "send", "message_id": "M-12b", "text": msg("M-12b", "h/alpha", to="h/beta")})
            check("whatever stops the roster verifying (a git that cannot run) leaves it carrying nothing, not ending the carrier",
                  res["carried"] == 0)
            a.roster_breaks = False
            a.roster_ok[0] = False
            a.carrier.refresh_roster()
            res = a.carrier.handle_request({"op": "send", "message_id": "M-13", "text": msg("M-13", "h/alpha", to="h/beta")})
            check("a roster that fails to verify leaves the carrier with no recipient, not the last good one",
                  res["carried"] == 0)
        finally:
            for n in nodes:
                n.stop()
    print(f"\ntest_gzcoord_carrier_engine: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
