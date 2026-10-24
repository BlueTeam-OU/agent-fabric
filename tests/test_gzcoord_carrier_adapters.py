#!/usr/bin/env python3
"""The inbox side of the InterWeave carrier (ADR-064 rules 9, 11; CARRIER-
CONTRACT.md §6): carrier/adapter.py, wait_loop's use of the shown ledger and of
the carrier's `unseen`, the spool behind `unseen`, the arrival log and the
rendering of an InterWeave arrival. The relay's own behaviour stays with
test_gzcoord_protocol.py and test_gzcoord_port.py, which run unchanged.

What is held: with no carrier the adapter is a no-op that costs a stat; a relay
copy is shown unless the LEDGER says it was shown, with no carrier at all; the
pending line is written before the relay is acknowledged; a page the journal
holds writes nothing to the ledger; the carrier's arrivals pass through the same
ledger and are never acknowledged to the relay; a mismatch revealed after the
relay's copy is shown once more, flagged; a showing that died after its pending
line is shown again, flagged; a carrier that does not answer never holds a relay
delivery; an arrival is shown as from the roster's address with the mismatch
said. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from gzcoord import gzmsg  # noqa: E402
from gzcoord.carrier import adapter as A  # noqa: E402
from gzcoord.carrier import arrivals, ledger as L, server  # noqa: E402
from gzcoord.inbox import show_page  # noqa: E402
from gzcoord.inbox_parts import render as R  # noqa: E402
from gzcoord.inbox_parts.tokens import for_me  # noqa: E402
from gzcoord.inbox_parts.watch import wait_loop  # noqa: E402

fails = 0
ME = {"address": "h/beta", "slug": "dev"}
NOW = "2026-10-24T12:00:00Z"


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def text(mid: str, frm: str = "h/alpha", to: str = "h/beta") -> str:
    return f"[GZCOORD/1] INFO\nFROM: {frm}\nROLE: r\nTO: {to}\nMESSAGE-ID: {mid}\nSUBJECT: s\n\nCONTEXT:\nbody of {mid}\n"


def rrec(n: int, mid: str, **kw) -> dict:
    return {"id": f"id{n}", "seq": n, "sender": "h/alpha", "timestamp": NOW, "content": text(mid, **kw)}


def urec(mid: str, verdict: str = "ok", frm: str = "h/alpha") -> dict:
    return {"content": text(mid, frm=frm), "ts": NOW, "seq": None, "message_id": mid, "verdict": verdict,
            "sender": "h/alpha"}


class FakeCarrier:
    """What wait_loop asks of the adapter: `unseen`, nothing else."""

    def __init__(self, records: list[dict] | None = None) -> None:
        self.records = records or []
        self.asked = 0

    def unseen(self) -> list[dict]:
        self.asked += 1
        return [dict(r) for r in self.records]


def loop(pages, led, iw=None, journal=None, on_arrival=None, ack_probe=None, held=lambda: False):
    acked: list = []
    it = iter(pages)

    def fetch(slice_, abort):
        return {"messages": next(it, [])}

    def ack(i):
        acked.append(i)
        if ack_probe:
            ack_probe(i)

    res = wait_loop(fetch, ack, 0, lambda m: for_me(m, ME), [], ME["address"], journal=journal, iw=iw,
                    on_arrival=on_arrival, sleep=lambda ms: None, ledger=led, held=held)
    return res, acked


def lines(path: str) -> list[dict]:
    try:
        return [json.loads(x) for x in open(path) if x.strip()]
    except FileNotFoundError:
        return []


def main() -> int:
    # -- the adapter -------------------------------------------------------
    with tempfile.TemporaryDirectory(prefix="gz-adp-") as d:
        path = os.path.join(d, "none.sock")
        a = A.Adapter(path)
        check("with no carrier socket the adapter is absent and every call is a no-op",
              not a.present() and a.post("M", "t") == "absent" and a.unseen() == [])

        seen: list[dict] = []
        replies = {"send": {"ok": True, "carried": 2, "queued": 2, "posted": 0}}

        def handler(req: dict) -> dict:
            seen.append(req)
            return replies.get(req["op"], {"ok": True, "records": [{"message_id": "X"}]})

        srv = server.Server(path, handler)
        b = A.Adapter(path)
        check("a present carrier that recorded every recipient is accepted", b.post("M", "t") == "accepted")
        replies["send"] = {"ok": True, "carried": 0, "queued": 0, "posted": 0}
        check("an address no roster row carries is not-carried, not a failure", b.post("M", "t") == "not-carried")
        replies["send"] = {"ok": True, "carried": 2, "queued": 1, "posted": 0}
        check("ok:true with queued != carried is a failure, never accepted", b.post("M", "t") == "failed")
        replies["send"] = {"ok": False, "error": "only 1 of 2 recipients recorded", "carried": 2, "queued": 1}
        check("ok:false (partly durable) is a failure", b.post("M", "t") == "failed")
        check("unseen is passed through", b.unseen() == [{"message_id": "X"}])
        replies["send"] = {"ok": True, "carried": 2, "queued": 2, "posted": 0}
        before = len(seen)
        check("a message over 4 MiB is refused before a byte is written: the relay carries it",
              b.post("M", "x" * (4 * 1024 * 1024 + 1)) == "failed" and len(seen) == before
              and b.post("M", "x" * (4 * 1024 * 1024)) == "accepted" and len(seen) == before + 1)
        before = len(seen)
        check("a request line over 9 MiB is refused too: 2 MiB of control characters escape to six bytes each",
              b.post("M", "\x01" * (2 * 1024 * 1024)) == "failed" and len(seen) == before)
        sent_lines: list[dict] = []
        spy = A.Adapter(path, lambda p_, req, timeout=0: sent_lines.append(req) or {"ok": True, "carried": 1, "queued": 1})
        check("neither refusal reaches the socket at all (a spy in the carrier's place is never called)",
              spy.post("M", "\x01" * (2 * 1024 * 1024)) == "failed" and spy.post("M", "x" * (4 * 1024 * 1024 + 1)) == "failed"
              and sent_lines == [] and spy.post("M", "ok") == "accepted" and len(sent_lines) == 1)
        srv.close()
        open(path, "w").close()
        os.unlink(path)
        sock = socket_left_behind(path)
        check("a socket file with no carrier behind it fails open: unseen is nothing, a post fails",
              sock.present() and sock.unseen() == [] and sock.post("M", "t") == "failed")

        now = [0.0]
        calls: list[dict] = []

        def refusing(p, req, timeout=0):
            calls.append(req)
            raise OSError("no answer")
        os.unlink(path)
        open(path, "w").close()
        ad = A.Adapter(path, refusing, clock=lambda: now[0])
        ad.unseen()
        ad.unseen()
        check("a carrier that did not answer is not asked again for a while: the relay is not delayed per pass",
              len(calls) == 1)
        now[0] += A.DOWN_FOR + 1
        ad.unseen()
        check("... and is asked again once the while has passed", len(calls) == 2)

    # -- wait_loop and the ledger ---------------------------------------------
    with tempfile.TemporaryDirectory(prefix="gz-wl-") as d:
        lpath = os.path.join(d, "gzcoord-shown.jsonl")
        led = L.Ledger(lpath, iso_now=lambda: NOW)

        r, acked = loop([[rrec(1, "R-1")]], None)
        check("without a ledger the relay page is exactly as before", r["delivered"] and acked == ["id1"] and "ledger" not in r
              or (r["delivered"] and r.get("ledger") is None))

        seen_when_acked: list[int] = []
        r, acked = loop([[rrec(1, "R-1")]], led, ack_probe=lambda i: seen_when_acked.append(len(lines(lpath))))
        check("a relay copy nothing showed is delivered, with the ledger's lock held for the caller",
              r["delivered"] and r["ledger"] is not None and [c["rec"]["id"] for c in r["classified"]] == ["id1"])
        out = []
        show_page(r, lambda: out.append("written"))
        check("the pending line was on disk when the relay was acknowledged, and the acknowledgement came after the showing",
              seen_when_acked == [2] and lines(lpath)[0].get("pending") is True and acked == ["id1"], str(seen_when_acked))
        check("show_page writes the page, then the final line, and releases the lock",
              out == ["written"] and [x.get("pending") for x in lines(lpath)] == [True, None])
        led.exclusive().release()          # would block for ever if the lock were still held

        r, acked = loop([[rrec(1, "R-1")]], led)
        check("the same relay record again (an acknowledgement that failed): acknowledged, not shown, no lock kept",
              not r["delivered"] and r["classified"] == [] and acked == ["id1"] and r["ledger"] is None if "ledger" in r else
              not r["delivered"] and acked == ["id1"])

        # shown by the carrier first: the relay's copy is not shown
        c2 = FakeCarrier([urec("C-1")])
        r, _ = loop([[]], led, iw=c2)
        check("a carrier arrival nobody showed is delivered, titled from its record, never acknowledged to the relay",
              r["delivered"] and [c["iw"]["mid"] for c in r["classified"]] == ["C-1"], str(r))
        show_page(r, lambda: None)
        r, acked = loop([[rrec(2, "C-1")]], led, iw=c2)
        check("... and the relay's later copy of it is acknowledged and not shown", not r["delivered"] and acked == ["id2"])

        # shown by the relay first: an ok carrier copy is not shown, a mismatch one is, flagged, once
        r, _ = loop([[rrec(3, "S-1", frm="h/gamma")]], led, iw=FakeCarrier([urec("S-1", "mismatch", frm="h/gamma")]))
        kinds = [("iw" if c.get("iw") else "relay", bool(c.get("flagged"))) for c in r["classified"]]
        check("the relay's copy shown, and the carrier's copy that reveals the FROM mismatch shown again, flagged",
              kinds == [("relay", False), ("iw", True)], str(kinds))
        show_page(r, lambda: None)
        r, _ = loop([[]], led, iw=FakeCarrier([urec("S-1", "mismatch", frm="h/gamma")]))
        check("... and that second showing happens once", not r["delivered"])
        r, _ = loop([[rrec(4, "S-2")]], led, iw=FakeCarrier([urec("S-2", "ok")]))
        show_page(r, lambda: None)
        check("an ok carrier copy of a message the relay showed is not shown (the same page: one showing)",
              [("iw" if c.get("iw") else "relay") for c in r["classified"]] == ["relay"])

        # a showing that died after its pending line
        h = led.exclusive()
        h.pending("D-1", "relay")
        h.release()
        r, _ = loop([[rrec(5, "D-1")]], led)
        check("a message whose showing died after the pending line is shown again, flagged may-repeat",
              r["delivered"] and r["classified"][0]["may_repeat"] is True)
        show_page(r, lambda: None)
        r, _ = loop([[rrec(6, "D-1")]], led)
        check("... and then it is settled", not r["delivered"])

        # a page the journal holds writes nothing
        before = lines(lpath)
        r, _ = loop([[rrec(7, "H-1")]], led, journal=lambda recs: {"ok": False, "reason": "held"})
        check("a page the journal holds is not recorded in the ledger (it is shown later)",
              lines(lpath) == before and not r["delivered"])
        r, _ = loop([[rrec(7, "H-1")]], led, journal=lambda recs: {"ok": True, "said": []})
        check("... and when the journal recovers it is shown", r["delivered"])
        show_page(r, lambda: None)

        # the page cannot be written: the lock is released and the pending line stands
        r, _ = loop([[rrec(8, "W-1")]], led)

        def broken():
            raise BrokenPipeError()
        try:
            show_page(r, broken)
        except BrokenPipeError:
            pass
        led.exclusive().release()
        check("a showing that raises releases the lock and leaves the pending line", lines(lpath)[-1].get("pending") is True
              and lines(lpath)[-1]["mid"] == "W-1")

        # a message that reuses a shown id is another message
        r, _ = loop([[rrec(21, "COL-1")]], led)
        show_page(r, lambda: None)
        other = rrec(22, "COL-1")
        other["content"] = other["content"].replace("body of COL-1", "a different body entirely")
        r, acked = loop([[other]], led)
        check("a different message that reuses a shown MESSAGE-ID is shown, not acknowledged away (even with no carrier)",
              r["delivered"] and "a different body" in r["classified"][0]["rec"]["content"])
        show_page(r, lambda: None)
        check("... and acknowledged once shown", acked == ["id22"])

        # a hold: nothing is polled, the carrier's arrivals included
        asked = FakeCarrier([urec("HOLD-1")])
        calls = [0]

        def held_second():
            calls[0] += 1
            return calls[0] >= 2
        r, acked = loop([[rrec(23, "HOLD-0")]], led, iw=asked, held=held_second)
        check("a page dropped for a hold asks the carrier nothing and shows nothing",
              not r["delivered"] and asked.asked == 0 and acked == [], str((r["delivered"], asked.asked, acked)))

        # the relay is acknowledged after the lock is released, not under it
        probe = []
        r, acked = loop([[rrec(31, "ACK-1")]], led, ack_probe=lambda i: probe.append(i))
        check("with the ledger's lock held for a showing, no acknowledgement is sent yet", probe == [] and callable(r["ack_later"]))
        show_page(r, lambda: None)
        check("... they follow once the lock is released", probe == ["id31"])
        led.exclusive().release()

        # presence from the carrier is never shown
        hello = urec("HE-1")
        hello["content"] = hello["content"].replace("[GZCOORD/1] INFO", "[GZCOORD/1] HELLO")
        r, _ = loop([[]], led, iw=FakeCarrier([hello]))
        check("a retired HELLO from the carrier is not shown", not r["delivered"])

        # a carrier that is down does not hold the relay
        down = FakeCarrier([])
        r, acked = loop([[rrec(9, "N-1")]], led, iw=down)
        show_page(r, lambda: None)
        check("a carrier with nothing to say never holds a relay delivery", r["delivered"] and acked == ["id9"])

        # the arrival log hook
        got: list[list[dict]] = []
        order: list[str] = []
        loop([[rrec(10, "L-1"), rrec(11, "L-2", to="h/other")]], None,
             journal=lambda recs: order.append("journal") or {"ok": True, "said": []},
             on_arrival=lambda recs: (order.append("arrival"), got.append(recs)))
        check("the arrival hook sees only the copies addressed here, before the journal",
              order == ["arrival", "journal"] and [x["id"] for x in got[0]] == ["id10"])

    # -- a ledger that cannot be opened ----------------------------------------
    with tempfile.TemporaryDirectory(prefix="gz-nol-") as d:
        blocker = os.path.join(d, "agents")
        open(blocker, "w").write("a file where the state directory should be")
        led = L.Ledger(os.path.join(blocker, "me", "gzcoord-shown.jsonl"), iso_now=lambda: NOW)
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            r, acked = loop([[rrec(1, "NL-1")]], led, iw=FakeCarrier([urec("NL-2")]))
        check("a ledger that cannot be opened is said, the relay's message is shown without it, the carrier's is not (it would repeat)",
              r["delivered"] and [c["rec"]["id"] for c in r["classified"]] == ["id1"] and acked == ["id1"]
              and "shown ledger could not be opened" in err.getvalue(), err.getvalue())

    # -- two inbox paths cannot both show one message -------------------------
    with tempfile.TemporaryDirectory(prefix="gz-two-") as d:
        led = L.Ledger(os.path.join(d, "gzcoord-shown.jsonl"), iso_now=lambda: NOW)
        shown: list[str] = []
        gate = threading.Barrier(2)

        def path(via_relay: bool) -> None:
            gate.wait()
            r, _ = loop([[rrec(1, "T-1")]] if via_relay else [[]], led, iw=None if via_relay else FakeCarrier([urec("T-1")]))
            if r["delivered"]:
                show_page(r, lambda: shown.append("relay" if via_relay else "carrier"))
        ts = [threading.Thread(target=path, args=(v,)) for v in (True, False)]
        [t.start() for t in ts]
        [t.join(30) for t in ts]
        check("the relay path and the carrier path racing for one message: it is shown once", len(shown) == 1, str(shown))

    # -- the spool behind unseen ---------------------------------------------
    with tempfile.TemporaryDirectory(prefix="gz-spool-") as d:
        lpath = os.path.join(d, "gzcoord-shown.jsonl")
        sp = arrivals.Spool(os.path.join(d, "iw"), lpath, iso_now=lambda: NOW)
        sp.keep("K-1", "c1", NOW, "ok", "h/a")
        sp.keep("K-1", "c1", NOW, "ok", "h/a")
        sp.keep("K-2", "c2", NOW, "mismatch", "h/a")
        sp.keep("K-3", "c3", NOW, "ok", "h/a")
        un = sp.unseen()
        check("the spool lists a message once, in arrival order, with the contract's fields",
              [r["message_id"] for r in un] == ["K-1", "K-2", "K-3"] and set(un[0]) == {
                  "content", "ts", "seq", "message_id", "verdict", "sender"} and un[0]["seq"] is None)
        sp.keep("K-1", "c1 but another message", NOW, "ok", "h/a")
        check("another message under the same id is another record", [r["message_id"] for r in sp.unseen()].count("K-1") == 2)
        sp.records = [r for r in sp.records if r["content"] != "c1 but another message"]
        sp._kept.discard(("K-1", L.body_hash("c1 but another message")))
        led = L.Ledger(lpath, iso_now=lambda: NOW)
        h = led.exclusive()
        for mid, via in (("K-1", "relay"), ("K-2", "relay"), ("K-3", "interweave")):
            h.pending(mid, via)
        h.finish()
        check("unseen drops an ok copy on any final line, a carrier-shown one on its own, and keeps a mismatch the relay showed",
              [r["message_id"] for r in sp.unseen()] == ["K-2"])
        check("unseen asks for nothing it already lists again: a record is listed on every call until settled",
              [r["message_id"] for r in sp.unseen()] == ["K-2"])
        h = led.exclusive()
        h.pending("K-2", "interweave", True)
        h.finish()
        check("... until the ledger holds the flagged copy's final line", sp.unseen() == [])
        sp.keep("K-4", "c4", NOW, "ok", "h/a")
        with open(os.path.join(d, "iw", "inbox.jsonl"), "ab") as fh:
            fh.write(b'{"mid":"K-5","con')
        again = arrivals.Spool(os.path.join(d, "iw"), lpath, iso_now=lambda: NOW)
        again.keep("K-6", "c6", NOW, "ok", "h/a")
        check("a torn tail is cut at open and the next record is a whole line, across a restart",
              [r["mid"] for r in arrivals.Spool(os.path.join(d, "iw"), lpath, iso_now=lambda: NOW).records] == ["K-4", "K-6"])
        later = arrivals.Spool(os.path.join(d, "iw"), lpath, iso_now=lambda: "2027-12-01T00:00:00Z")
        check("an arrival nobody has shown stays listed however old, across a restart (no order loses a message)",
              [r["mid"] for r in later.records] == ["K-4", "K-6"])

    # -- the arrival log -------------------------------------------------------
    with tempfile.TemporaryDirectory(prefix="gz-arr-") as d:
        log = arrivals.ArrivalLog(os.path.join(d, "a", "gzcoord-arrivals.jsonl"), iso_now=lambda: NOW)
        A.relay_arrivals(log, "h/beta", [("r1", "L-1"), ("r1", "L-1")])
        A.relay_arrivals(log, "h/beta", [("r1", "L-1")])
        check("a relay copy is a line with the relay's verdict unauthenticated; a re-read of the same record is not another",
              [(x["mid"], x["carrier"], x["verdict"], x["addressee"]) for x in lines(log.path)]
              == [("L-1", "relay", "unauthenticated", "h/beta")] and oct(os.stat(log.path).st_mode & 0o777) == "0o600")

        A.relay_arrivals(log, "h/beta", [("r2", "L-1")])
        check("a second relay record of the same message (a retransmission) is another copy and another line",
              len(lines(log.path)) == 2)

        def writer(n: int) -> None:
            for i in range(25):
                log.append(f"W-{n}-{i}", "h/beta", "interweave", "ok")
        ws = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
        [w.start() for w in ws]
        [w.join(30) for w in ws]
        check("two writers appending at once leave whole lines only", len(lines(log.path)) == 102)

    # -- rendering ---------------------------------------------------------
    me = {"address": "h/beta", "slug": "dev"}
    msg = gzmsg.parse(text("W-2", frm="h/gamma"))
    rec = {"id": None, "seq": "interweave", "sender": "h/alpha", "timestamp": NOW, "content": text("W-2", frm="h/gamma")}

    def entry(**kw) -> dict:
        return {"rec": rec, "msg": msg, "isMine": True, "iw": {"mid": "W-2", "verdict": "mismatch"}, **kw}
    out = R.render({"classified": [entry(flagged=True, may_repeat=True)]}, me, "gzapp:gzcoord", None)
    check("an arrival is titled from the roster's address, not its FROM, with the mismatch, the re-show and the repeat said",
          "InterWeave, from h/alpha" in out and "FROM mismatch" in out and "says FROM h/gamma" in out
          and "relay copy of W-2" in out and "may repeat" in out and "relay seq" not in out, out)
    ok_rec = {"classified": [{**entry(), "msg": gzmsg.parse(text("W-3")), "iw": {"mid": "W-3", "verdict": "ok"}}]}
    check("a verified arrival carries no mismatch flag", "mismatch" not in R.render(ok_rec, me, "gzapp:gzcoord", None))
    relay_repeat = R.render({"classified": [{"rec": rrec(1, "R-9"), "msg": gzmsg.parse(text("R-9")), "isMine": True,
                                             "may_repeat": True}]}, me, "gzapp:gzcoord", None)
    check("a relay copy shown again after an interrupted showing says so", "may repeat" in relay_repeat, relay_repeat)
    big = {"id": None, "seq": "interweave", "sender": "h/alpha", "timestamp": "t",
           "content": text("W-4").replace("body of W-4", "x" * 6000)}
    cut = R.render({"classified": [{"rec": big, "msg": gzmsg.parse(big["content"]), "isMine": True,
                                    "iw": {"mid": "W-4", "verdict": "ok"}}]}, me, "gzapp:gzcoord", None, cap=2000)
    check("an arrival cut for the notification cap names the journal, not a relay replay",
          "fabric-history --thread W-4 --full" in cut and "--replay" not in cut, cut)

    print(f"\ntest_gzcoord_carrier_adapters: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


def socket_left_behind(path: str) -> A.Adapter:
    import socket
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(path)
    s.close()      # the file stays, nobody listens: what a carrier that died leaves
    return A.Adapter(path)


if __name__ == "__main__":
    sys.exit(main())
