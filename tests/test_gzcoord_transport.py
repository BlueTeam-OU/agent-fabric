#!/usr/bin/env python3
"""tools/fabric/gzcoord/transport/ (agent-fabric ADR-067): the carrier's verbs against a fake adapter, the factory and the mux
that the inbox and the sender hold, and the shown-ledger decision of dedup.py. The behaviour of the inbox and the sender through
the real commands is pinned by test_gzcoord_message_transport.py, test_gzcoord_protocol.py and test_gzcoord_carrier_*.py; this
file covers what they reach only through a process: a verb's answer, a failure's class. A fake adapter, a real carrier stand-in
for the sender, scratch directories. Plain script: ok/FAIL, exit 1."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import test_gzcoord_protocol as P  # noqa: E402 — the real commands' minimal environment and carrier stand-in
from gzcoord import transport  # noqa: E402
from gzcoord.carrier import CARRIER_NAME  # noqa: E402
from gzcoord.carrier import ledger as L  # noqa: E402
from gzcoord.carrier import adapter  # noqa: E402
from gzcoord.transport import dedup  # noqa: E402

fails = 0
ME = {"address": "h/beta", "slug": "dev"}
NOW = "2026-10-24T12:00:00Z"


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def text(mid: str, to: str = "h/beta") -> str:
    return f"[GZCOORD/1] INFO\nFROM: h/alpha\nROLE: r\nTO: {to}\nMESSAGE-ID: {mid}\nSUBJECT: s\n\nCONTEXT:\nbody of {mid}\n"


class FakeAdapter:
    def __init__(self, post: str = "accepted", unseen: list[dict] | None = None, present: bool = True,
                 wait_error: Exception | None = None) -> None:
        self._wait_error = wait_error
        self._post, self._unseen, self._present, self.posted = post, unseen or [], present, []

    def post_result(self, mid: str, text: str, *, fail_open: bool = False):
        self.posted.append(mid)
        return adapter.Post(self._post, "" if self._post == "accepted" else f"why {self._post}")

    def unseen(self) -> list[dict]:
        return [dict(r) for r in self._unseen]

    def present(self) -> bool:
        return self._present

    def wait(self, seconds: float, abort: threading.Event) -> list[dict]:
        if self._wait_error is not None:
            raise self._wait_error
        return self.unseen()


def _refuses(**kw: object) -> bool:
    try:
        transport.open_transport(me=ME, **kw)  # type: ignore[arg-type]
    except TypeError:
        return True
    return False


def main() -> int:
    scratch = tempfile.mkdtemp(prefix="transport-")
    try:
        # ── the carrier's verbs over an adapter ──────────────────────────────────────────────────────────────────
        for state in ("accepted", "not-carried", "absent", "failed", "no-answer"):
            fake = FakeAdapter(post=state)
            c = transport.CarrierTransport(fake)
            check(f"carrier send answers the adapter's {state!r} under the carrier's own name, with its reason",
                  c.send("m", "T") == transport.Sent(CARRIER_NAME, state, detail="" if state == "accepted" else f"why {state}")
                  and fake.posted == ["m"])
        fake = FakeAdapter(unseen=[{"message_id": "u1"}], present=False)
        c = transport.CarrierTransport(fake)
        check("carrier receive is what the adapter lists unseen, ack tells it nothing, health is whether it is running",
              c.receive(5, threading.Event()) == [{"message_id": "u1"}] and c.ack("x") is None
              and c.health() == transport.Health(CARRIER_NAME, False))

        # ── the carrier as the primary: what the mirror swallows is raised ───────────────────────────────────────
        check("primary send of an accepted post is Sent with no seq: the MESSAGE-ID names the message",
              transport.CarrierPrimary(FakeAdapter(post="accepted")).send("m", "T") == transport.Sent(CARRIER_NAME, "accepted"))
        for state, absent in (("absent", True), ("failed", False), ("not-carried", False)):
            try:
                transport.CarrierPrimary(FakeAdapter(post=state)).send("m", "T")
                raised = None
            except adapter.CarrierError as e:
                raised = e
            check(f"primary send the adapter answers {state!r} with is raised, carrying the state and whether none ran",
                  raised is not None and raised.state == state and raised.absent is absent, f"{raised!r}")
        tp = transport.CarrierPrimary(FakeAdapter(), address="h/beta")
        check("the carrier has no token to refresh, and its failure is exit 0 (down), never the exit 4 of a refusal",
              tp.refresh(OSError("x")) is False and tp.explain(OSError("x"))["code"] == 0
              and tp.explain(adapter.CarrierError("gone", absent=True))["code"] == 0)
        check("never_delivered holds only for a carrier error that proves nothing was recorded",
              [tp.never_delivered(e) for e in (adapter.CarrierError("x", never_reached_it=True), adapter.CarrierError("x"),
                                               OSError("x"))] == [True, False, False])
        try:
            tp.newest(5)
            raised = False
        except adapter.CarrierError:
            raised = True
        check("newest without a journal to read is refused, not an empty list", raised)
        check("newest is the journal's rows, in the page shape",
              transport.CarrierPrimary(FakeAdapter(), journal_newest=lambda n: [{"n": n}]).newest(7) == {"messages": [{"n": 7}]})

        # ── the factory and the mux ──────────────────────────────────────────────────────────────────────────────
        state_dir = os.path.join(scratch, "state")
        os.makedirs(state_dir)
        mux = transport.open_transport(me=ME, state_dir=state_dir, iso_now=lambda: NOW)
        check("the factory makes the carrier the primary, with no mirror, a shown ledger beside the journal, and itself as iw",
              isinstance(mux.primary, transport.CarrierPrimary) and mux.primary.name == CARRIER_NAME and mux.iw is mux
              and mux.ledger is not None and not hasattr(mux, "mirrors") and not hasattr(mux, "send_mirrors"))
        check("a mux for a send, or for the record (--replay, --history), has no ledger: it logs nothing it shows",
              transport.open_transport(me=ME).ledger is None
              and transport.open_transport(me=ME, state_dir=state_dir, iso_now=lambda: NOW, record_only=True).ledger is None)
        try:
            transport.open_transport(me=ME, journal_off=True, state_dir=state_dir, iso_now=lambda: NOW)
            refused = False
        except transport.ModeError:
            refused = True
        check("with the journal off, receiving is refused (ADR-064 rule 8)", refused)
        check("... a send, and the read of the record, are not",
              transport.open_transport(me=ME, journal_off=True, for_send=True).iw is not None
              and transport.open_transport(me=ME, journal_off=True, record_only=True).iw is not None)
        check("the factory takes no relay and no mode: the old keywords are a TypeError, not an ignored choice",
              all(_refuses(**{k: v}) for k, v in (("cfg", {}), ("token", "t"), ("account_mode", {"mode": "relay-record"}))))
        waiter = FakeAdapter(unseen=[{"message_id": "a"}, {"message_id": "b"}])
        m1 = transport.TransportMux(transport.CarrierPrimary(waiter), me=ME)
        page = m1.fetch_page(1, threading.Event())
        first, second = m1.unseen(), m1.unseen()
        check("fetch_page is an empty page whatever the carrier brought; unseen hands what its wait listed, once",
              page == {"messages": []} and [r["message_id"] for r in first] == ["a", "b"] and second == [], f"{page} {first} {second}")
        check("ack tells nothing to anyone, and health is the one carrier's", m1.ack("r1") is None
              and m1.health() == [transport.Health(CARRIER_NAME, True)])
        down = transport.TransportMux(transport.CarrierPrimary(FakeAdapter(wait_error=adapter.CarrierError("down"))), me=ME)
        try:
            down.fetch_page(1, threading.Event())
            raised = False
        except adapter.CarrierError:
            raised = True
        check("a wait the carrier did not answer is raised: a dead carrier is not an idle watch", raised)

        # ── through the sender: the journal row names the carrier that accepted it ───────────────────────────────
        r, state, store, seen = P.carrier_send(P.addressed("TO: h/alpha"), extra=["--force"])
        rows = P.journal_rows(state, store, "state, carrier")
        check("send with a carrier that takes it: the carrier is asked once and the row names it",
              len(seen) == 1 and rows == [["accepted", CARRIER_NAME]], f"{r.code} {r.err}\n{rows}")

        # ── through the sender: with the journal off the carrier is the route all the same (ADR-064 rule 8) ──────
        r, state, store, seen = P.carrier_send(P.addressed("TO: h/alpha"), extra=["--force"], GZCOORD_JOURNAL="off")
        check("send, journal off and a carrier running: the carrier is asked once and takes it",
              r.code == 0 and len(seen) == 1, f"{r.code} {r.err}\n{seen}")

        # ── the shown ledger's decision ──────────────────────────────────────────────────────────────────────────
        lg = L.Ledger(os.path.join(scratch, "shown.jsonl"), iso_now=lambda: NOW)
        rec = {"id": "r1", "seq": 1, "content": text("D-1")}
        mirror = {"content": text("D-1"), "ts": NOW, "message_id": "D-1", "verdict": "ok", "sender": "h/alpha"}
        lock = lg.exclusive()
        c1 = {"rec": rec, "msg": {"metadata": {"MESSAGE-ID": "D-1"}}, "isMine": True}
        classified = [c1]
        dedup.admit(lock, classified, [c1], [mirror])
        lock.finish()
        check("a primary record is shown and a mirror's copy of the same text is not added",
              "quiet" not in c1 and len(classified) == 1, f"{classified}")
        lock = lg.exclusive()
        c2 = {"rec": dict(rec), "msg": {"metadata": {"MESSAGE-ID": "D-1"}}, "isMine": True}
        classified = [c2]
        dedup.admit(lock, classified, [c2], [mirror])
        lock.release()
        check("... shown again by either, it is quiet (journaled and acknowledged, not shown twice) and not added again",
              c2.get("quiet") is True and len(classified) == 1, f"{classified}")
        lock = lg.exclusive()
        classified = []
        dedup.admit(lock, classified, [], [{**mirror, "message_id": "D-2", "content": text("D-2")}])
        lock.finish()
        check("a mirror's record not shown before becomes a message of its own, tagged with the mirror's name",
              len(classified) == 1 and classified[0]["iw"]["mid"] == "D-2" and classified[0]["rec"]["seq"] == CARRIER_NAME,
              f"{classified}")
    finally:
        for d in [scratch, *P.SCRATCH]:
            shutil.rmtree(d, ignore_errors=True)
    print(f"\ntest_gzcoord_transport: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
