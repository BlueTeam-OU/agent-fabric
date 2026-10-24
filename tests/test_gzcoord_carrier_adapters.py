#!/usr/bin/env python3
"""The inbox side of the InterWeave carrier (ADR-064 rules 9, 11; CARRIER-
CONTRACT.md §6): carrier/adapter.py, wait_loop's use of it and the rendering
of an InterWeave arrival. The relay's own behaviour stays with
test_gzcoord_protocol.py and test_gzcoord_port.py, which run unchanged.

What is held: with no carrier the adapter is a no-op that costs a stat and
the relay page is untouched; a relay copy is shown unless the carrier ANSWERS
that the message was shown over InterWeave; the claim is made after the
journal kept the page, so a page held by the journal is shown later; an
InterWeave arrival is delivered with no relay acknowledgement; a carrier that
does not answer fails open; the arrival log gets one line per relay copy
before the journal sees it; an arrival is shown as from the roster's address
with the mismatch said. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from gzcoord import gzmsg  # noqa: E402
from gzcoord.carrier import adapter as A  # noqa: E402
from gzcoord.carrier import arrivals, server  # noqa: E402
from gzcoord.inbox_parts import render as R  # noqa: E402
from gzcoord.inbox_parts.tokens import for_me  # noqa: E402
from gzcoord.inbox_parts.watch import wait_loop  # noqa: E402

fails = 0
ME = {"address": "h/beta", "slug": "dev"}


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def text(mid: str, frm: str = "h/alpha", to: str = "h/beta") -> str:
    return f"[GZCOORD/1] INFO\nFROM: {frm}\nROLE: r\nTO: {to}\nMESSAGE-ID: {mid}\nSUBJECT: s\n\nCONTEXT:\nbody of {mid}\n"


def rrec(n: int, mid: str, **kw) -> dict:
    return {"id": f"id{n}", "seq": n, "sender": "h/alpha", "timestamp": "2026-10-24T12:00:00Z",
            "content": text(mid, **kw)}


class FakeAdapter:
    def __init__(self) -> None:
        self.claims: dict[str, str] = {}
        self.records: list[dict] = []
        self.calls: list[tuple] = []
        self.down = False

    def claim(self, mid: str, via: str) -> dict:
        self.calls.append(("claim", mid, via))
        if self.down:
            return {"first": True, "shown_via": None, "reshow": False}
        if mid in self.claims:
            if via == "interweave" and self.claims[mid] == "relay" and self.reshow_ok(mid):
                self.claims[mid] = "both"
                return {"first": True, "shown_via": "relay", "reshow": True}
            return {"first": False, "shown_via": self.claims[mid], "reshow": False}
        self.claims[mid] = via
        return {"first": True, "shown_via": None, "reshow": False}

    def reshow_ok(self, mid: str) -> bool:
        return any(r["mid"] == mid and r["verdict"] == "mismatch" for r in self.records)

    def unseen(self) -> list[dict]:
        self.calls.append(("unseen",))
        return [] if self.down else [dict(r) for r in self.records if self.claims.get(r["mid"]) is None
                                    or (r["verdict"] == "mismatch" and self.claims.get(r["mid"]) == "relay")]


def loop(pages: list[list[dict]], iw, journal=None, on_arrival=None, wait_total: float = 0):
    acked: list = []
    it = iter(pages)

    def fetch(slice_, abort):
        return {"messages": next(it, [])}

    res = wait_loop(fetch, lambda i: acked.append(i), wait_total, lambda m: for_me(m, ME), [], ME["address"],
                    journal=journal, iw=iw, on_arrival=on_arrival, sleep=lambda ms: None)
    return res, acked


def main() -> int:
    # -- the adapter -------------------------------------------------------
    with tempfile.TemporaryDirectory(prefix="gz-adp-") as d:
        path = os.path.join(d, "none.sock")
        a = A.Adapter(path)
        check("with no carrier socket the adapter is absent and every call is a no-op",
              not a.present() and a.post("M", "t") == "absent" and a.claim("M", "relay")["first"] is True
              and a.unseen() == [])

        seen: list[dict] = []
        replies = {"send": {"ok": True, "carried": 2, "queued": 2, "posted": 0}}

        def handler(req: dict) -> dict:
            seen.append(req)
            return replies.get(req["op"], {"ok": True, "first": False, "shown_via": "interweave", "reshow": False,
                                           "records": [{"mid": "X"}]})

        srv = server.Server(path, handler)
        b = A.Adapter(path)
        check("a present carrier that queued every recipient is accepted", b.post("M", "t") == "accepted")
        replies["send"] = {"ok": True, "carried": 0, "queued": 0, "posted": 0}
        check("an address no roster row carries is not-carried, not a failure", b.post("M", "t") == "not-carried")
        replies["send"] = {"ok": True, "carried": 2, "queued": 1, "posted": 0}
        check("a recipient that was not durably queued is a failure, never accepted", b.post("M", "t") == "failed")
        replies["send"] = {"ok": False, "error": "no"}
        check("a refusal is a failure", b.post("M", "t") == "failed")
        replies["send"] = {"ok": True, "carried": 2, "queued": 2, "posted": 0}
        before = len(seen)
        check("a message over 4 MiB is refused before a byte is written: the relay carries it",
              b.post("M", "x" * (4 * 1024 * 1024 + 1)) == "failed" and len(seen) == before
              and b.post("M", "x" * (4 * 1024 * 1024)) == "accepted" and len(seen) == before + 1)
        check("claim and unseen are passed through", b.claim("M", "relay")["first"] is False and b.unseen() == [{"mid": "X"}])
        srv.close()
        open(path, "w").close()
        os.unlink(path)
        dead = socket_left_behind(path)
        check("a socket file with no carrier behind it fails open: claim says show it",
              dead.present() and dead.claim("M", "relay")["first"] is True and dead.unseen() == []
              and dead.post("M", "t") == "failed")

    # -- wait_loop ---------------------------------------------------------
    r, acked = loop([[rrec(1, "R-1")]], None)
    check("without an adapter the relay page is exactly as before",
          r["delivered"] and len(r["classified"]) == 1 and acked == ["id1"])

    iw = FakeAdapter()
    r, acked = loop([[rrec(1, "R-1")]], iw)
    check("a relay copy nobody showed first is shown, and claimed after the journal",
          r["delivered"] and [c["rec"]["id"] for c in r["classified"]] == ["id1"] and iw.claims == {"R-1": "relay"})

    iw = FakeAdapter()
    iw.claims["R-2"] = "interweave"
    r, acked = loop([[rrec(1, "R-2")]], iw)
    check("a relay copy of a message already shown over InterWeave is acknowledged and not shown again",
          not r["delivered"] and r["classified"] == [] and acked == ["id1"])

    iw = FakeAdapter()
    iw.records = [{"mid": "W-1", "content": text("W-1"), "ts": "2026-10-24T12:01:00Z", "verdict": "ok", "sender": "h/alpha",
                   "mismatch_of": None}]
    r, acked = loop([[]], iw)
    shown = r["classified"]
    check("an InterWeave arrival the relay has not shown is delivered",
          r["delivered"] and len(shown) == 1 and shown[0]["iw"]["mid"] == "W-1" and iw.claims == {"W-1": "interweave"})
    check("  and no relay acknowledgement is made for it", acked == [])

    iw = FakeAdapter()
    iw.down = True
    r, acked = loop([[rrec(1, "R-3")]], iw)
    check("a carrier that cannot be asked never holds a relay delivery", r["delivered"] and acked == ["id1"])

    # the claim comes after the journal: a page the journal holds is shown later
    iw = FakeAdapter()
    state = {"fail": True}

    def journal(recs):
        return {"ok": False, "reason": "held"} if state["fail"] else {"ok": True, "said": []}

    def run_held():
        loop([[rrec(1, "H-1")]], iw, journal=journal, wait_total=0)
    run_held()
    check("a page held by the journal has claimed nothing", "H-1" not in iw.claims)
    state["fail"] = False
    r, _ = loop([[rrec(1, "H-1")]], iw, journal=journal)
    check("  so when the journal recovers the message is shown", r["delivered"] and iw.claims == {"H-1": "relay"})

    # rule 9: relay copy first, the InterWeave copy reveals a mismatch
    iw = FakeAdapter()
    iw.records = [{"mid": "S-1", "content": text("S-1", frm="h/gamma"), "ts": "t", "verdict": "mismatch",
                   "sender": "h/alpha", "mismatch_of": "S-1"}]
    r, _ = loop([[rrec(1, "S-1", frm="h/gamma")]], iw)
    kinds = [("iw" if c.get("iw") else "relay", bool(c.get("reshow"))) for c in r["classified"]]
    check("a relay copy shown, and the InterWeave copy that reveals its FROM mismatch shown again, flagged",
          kinds == [("relay", False), ("iw", True)], str(kinds))
    r, _ = loop([[]], iw)
    check("  and that re-show happens once", not r["delivered"])

    # -- the arrival log hook ---------------------------------------------
    got: list[list[dict]] = []
    order: list[str] = []
    loop([[rrec(1, "L-1"), rrec(2, "L-2", to="h/other")]], None,
         journal=lambda recs: order.append("journal") or {"ok": True, "said": []},
         on_arrival=lambda recs: (order.append("arrival"), got.append(recs)))
    check("the arrival hook sees only the copies addressed here, before the journal",
          order == ["arrival", "journal"] and [r["id"] for r in got[0]] == ["id1"])

    with tempfile.TemporaryDirectory(prefix="gz-arr-") as d:
        log = arrivals.ArrivalLog(os.path.join(d, "a", "gzcoord-arrivals.jsonl"), iso_now=lambda: "T")
        A.relay_arrivals(log, "h/beta", ["L-1", "L-1"])
        lines = [json.loads(l) for l in open(log.path)]
        A.relay_arrivals(log, "h/beta", ["L-1"])
        lines = [json.loads(l) for l in open(log.path)]
        check("a relay copy is a line with the relay's verdict unauthenticated; a re-read of the same record is not another",
              [(x["mid"], x["carrier"], x["verdict"], x["addressee"]) for x in lines]
              == [("L-1", "relay", "unauthenticated", "h/beta")]
              and oct(os.stat(log.path).st_mode & 0o777) == "0o600")

    with tempfile.TemporaryDirectory(prefix="gz-spool-") as d:
        box = arrivals.Inbox(d, iso_now=lambda: "T")
        box.keep("K-1", "c", "t", "ok", "h/a")
        box.keep("K-1", "c", "t", "ok", "h/a")
        again = arrivals.Inbox(d, iso_now=lambda: "T")
        check("the spool keeps the first copy of a message once, across a restart too",
              len(box.spool) == 1 and len(again.spool) == 1 and len(open(os.path.join(d, "inbox.jsonl")).readlines()) == 1)

    with tempfile.TemporaryDirectory(prefix="gz-pend-") as d:
        calls: list[dict] = []
        state = {"up": False}

        def call(path, req, timeout=0):
            calls.append(req)
            if not state["up"]:
                raise OSError("no answer")
            return {"ok": True, "first": True, "shown_via": None, "reshow": False, "records": []}
        sock = os.path.join(d, "c.sock")
        open(sock, "w").close()
        now = [0.0]
        pend = os.path.join(d, "pending.jsonl")
        ad = A.Adapter(sock, call, pending=pend, clock=lambda: now[0])
        got = ad.claim("P-1", "relay")
        check("a relay show the carrier could not be told of fails open and is noted for later",
              got["first"] is True and open(pend).read().strip() == '{"mid":"P-1"}')
        n = len(calls)
        ad.claim("P-2", "relay")
        ad.unseen()
        check("a carrier that did not answer is not asked again for a while: the relay is not delayed per record",
              len(calls) == n and "P-2" in open(pend).read() or False)
        state["up"] = True
        now[0] += A.DOWN_FOR + 1
        calls.clear()
        ad.unseen()
        check("when it answers again the noted shows reach it first, then the question, and the note is gone",
              [(c["op"], c.get("message_id"), c.get("via")) for c in calls]
              == [("claim", "P-1", "relay"), ("claim", "P-2", "relay"), ("unseen", None, None)] and not os.path.exists(pend),
              str(calls))
        os.unlink(sock)
        spool = os.path.join(d, "inbox.jsonl")
        open(spool, "w").write('{"mid":"X"}\n')
        ad2 = A.Adapter(sock, call, pending=pend, spool=spool, clock=lambda: now[0])
        ad2.claim("P-3", "relay")
        check("with the carrier gone but its arrivals left behind, a relay show is still noted",
              os.path.exists(pend) and "P-3" in open(pend).read())
        os.unlink(pend)
        ad3 = A.Adapter(sock, call, pending=pend, clock=lambda: now[0])
        ad3.claim("P-4", "relay")
        check("with no carrier and no arrivals nothing is noted (the relay alone, as before)", not os.path.exists(pend))

    with tempfile.TemporaryDirectory(prefix="gz-prune-") as d:
        iso = [f"2026-10-{day:02d}T00:00:00Z" for day in (1, 20)]
        box = arrivals.Inbox(d, iso_now=lambda: iso[0])
        box.keep("S-1", "c1", "t", "ok", "h/a")
        box.keep("S-2", "c2", "t", "ok", "h/a")
        box.keep("S-3", "c3", "t", "mismatch", "h/a")
        box.claim("S-1", "interweave")
        box.claim("S-3", "relay")
        check("a settled record leaves memory at once; an owed re-show and an unclaimed one stay",
              sorted(r["mid"] for r in box.spool) == ["S-2", "S-3"])
        with open(os.path.join(d, "inbox.jsonl"), "ab") as fh:
            fh.write(b'{"mid":"S-9","content":"to')                     # a torn tail
        again = arrivals.Inbox(d, iso_now=lambda: iso[1])
        check("at open the file drops settled records and a torn tail; a claim past the bound goes with its record",
              [r["mid"] for r in again.spool] == ["S-2"] and again.claims == {}
              and len(open(os.path.join(d, "inbox.jsonl")).readlines()) == 1, str(again.claims))
        again.keep("S-10", "c", "t", "ok", "h/a")
        third = arrivals.Inbox(d, iso_now=lambda: iso[1])
        check("an append after the repaired tail is a whole line", "S-10" in {r["mid"] for r in third.spool})

    with tempfile.TemporaryDirectory(prefix="gz-torn-") as d:
        box = arrivals.Inbox(d, iso_now=lambda: "T")
        box.keep("T-1", "c", "t", "ok", "h/a")
        with open(os.path.join(d, "inbox.jsonl"), "ab") as fh:
            fh.write(b'{"mid":"T-2","con')                  # a crash mid-append; nothing else to rewrite
        again = arrivals.Inbox(d, iso_now=lambda: "T")
        again.keep("T-3", "c", "t", "ok", "h/a")
        check("a spool with a torn tail and nothing to prune: the next record is still a whole line after a restart",
              [r["mid"] for r in arrivals.Inbox(d, iso_now=lambda: "T").spool] == ["T-1", "T-3"])

    # -- rendering ---------------------------------------------------------
    me = {"address": "h/beta", "slug": "dev"}
    tax = None
    msg = gzmsg.parse(text("W-2", frm="h/gamma"))
    rec = {"id": None, "seq": "interweave", "sender": "h/alpha", "timestamp": "2026-10-24T12:01:00Z",
           "content": text("W-2", frm="h/gamma")}
    out = R.render({"classified": [{"rec": rec, "msg": msg, "isMine": True,
                                    "iw": {"mid": "W-2", "verdict": "mismatch"}, "reshow": True}]},
                   me, "gzapp:gzcoord", tax)
    check("an arrival is titled from the roster's address, not its FROM, with the mismatch and the re-show said",
          "interweave, from h/alpha" in out and "FROM mismatch" in out and "says FROM h/gamma" in out
          and "relay copy of W-2" in out and "relay seq" not in out, out)
    ok_rec = {"classified": [{"rec": rec, "msg": gzmsg.parse(text("W-3")), "isMine": True,
                              "iw": {"mid": "W-3", "verdict": "ok"}, "reshow": False}]}
    check("a verified arrival carries no mismatch flag", "mismatch" not in R.render(ok_rec, me, "gzapp:gzcoord", tax))
    big = {"id": None, "seq": "interweave", "sender": "h/alpha", "timestamp": "t",
           "content": text("W-4").replace("body of W-4", "x" * 6000)}
    cut = R.render({"classified": [{"rec": big, "msg": gzmsg.parse(big["content"]), "isMine": True,
                                    "iw": {"mid": "W-4", "verdict": "ok"}, "reshow": False}]},
                   me, "gzapp:gzcoord", tax, cap=2000)
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
