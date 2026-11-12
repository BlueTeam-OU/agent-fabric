#!/usr/bin/env python3
"""tools/fabric/gzcoord/backfill.py: a message the second carrier alone delivered is put on the relay's record when it
answers again — once, in order, unchanged, within the age bound. A real journal in a scratch directory, a fake relay with a
page, a clock the test sets. Plain script: ok/FAIL, exit 1."""
from __future__ import annotations

import datetime
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import episodic  # noqa: E402
from gzcoord import backfill  # noqa: E402
from gzcoord.inbox_parts import relay as R  # noqa: E402

fails = 0
ME = "h/alpha"
AGENT = "01a0f782-7e06-7dee-811f-0a860ed93bf3"
T0 = datetime.datetime(2026, 11, 12, 10, 0, 0, tzinfo=datetime.timezone.utc)


def check(name: str, ok: bool, detail: object = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f": {detail}"))
    fails += 0 if ok else 1


def text(mid: str, body: str = "body") -> str:
    # Non-ASCII and trailing blank lines: the bytes must come back as they went in.
    return f"[GZCOORD/1] INFO\nFROM: {ME}\nROLE: x\nTO: h/beta\nMESSAGE-ID: {mid}\nSUBJECT: s\n\nINFO:\n{body} ünï\n\n"


class FakeRelay:
    def __init__(self, up: bool = True, held: tuple = (), refuse: bool = False, cap_page: int | None = None) -> None:
        self.is_up, self.refuse = up, refuse
        self.page: list[dict] = []
        self.posts: list[tuple[str, str]] = []
        self.records = [(m, T0 - datetime.timedelta(hours=1)) for m in held]
        self.cap_page = cap_page
        self.address = ME

    def up(self) -> bool:
        return self.is_up

    def newest(self) -> list[dict]:
        recs = [{"ts_full": t.strftime("%Y-%m-%dT%H:%M:%S.000000Z"), "content": text(m)} for m, t in self.records]
        if self.cap_page:   # a page the relay cut at its cap, reaching back only to `cap_page` hours ago
            recs = [{"ts_full": (T0 - datetime.timedelta(hours=self.cap_page)).strftime("%Y-%m-%dT%H:%M:%S.000000Z"),
                                    "content": "[GZCOORD/1] INFO\nFROM: someone\n"}] * backfill.PAGE
        return recs

    def post(self, mid: str, body: str) -> None:
        if self.refuse:
            raise R.RelayError("refused", 503)
        self.posts.append((mid, body))
        self.records.append((mid, T0))


def journal(tmp: str, rows: list[tuple[str, str, int, str]]):
    """rows: (mid, state, minutes after T0-6h, carrier). Written through the journal's own verbs."""
    conn = episodic.connect(os.path.join(tmp, "episodic.db"), AGENT)
    for mid, state, age_min, carrier in rows:
        episodic.out_pending(conn, text(mid), "agent-fabric")
        conn.execute("UPDATE episodes SET happened_at=? WHERE message_id=?",
                     ((T0 - datetime.timedelta(minutes=age_min)).strftime("%Y-%m-%dT%H:%M:%SZ"), mid))
        if state != "pending":
            episodic.out_final(conn, mid, state, None, carrier)
    return conn


def run(tmp: str, conn, relay: FakeRelay | None, now: datetime.datetime = T0, configured: bool = True):
    return backfill.run(state_dir=tmp, address=ME, conn=conn, make_relay=lambda cfg, addr: relay,
                        config=lambda p: {"configured": configured, "channel": "ch", "relay_url": "http://x"}, now=lambda: now)


def log_of(tmp: str) -> list[dict]:
    try:
        with open(os.path.join(tmp, backfill.LOG_NAME)) as f:
            return [json.loads(x) for x in f]
    except FileNotFoundError:
        return []


def scratch():
    tmp = tempfile.mkdtemp(prefix="backfill-")
    os.environ["AGENT_FABRIC_STATE_DIR"] = tmp
    return tmp


def main() -> int:
    CAR = "interweave"
    # carrier-only row is backfilled, byte for byte, with its delay logged
    tmp = scratch()
    try:
        c = journal(tmp, [("m1", "accepted", 30, CAR)])
        r = FakeRelay()
        rep = run(tmp, c, r)
        check("carrier-only row is posted", r.posts == [("m1", text("m1"))] and rep.posted == ["m1"], r.posts)
        check("the body is byte-identical to the journaled text", r.posts and r.posts[0][1].encode() == text("m1").encode())
        lg = log_of(tmp)
        check("the backfill is logged with its id and delay", len(lg) == 1 and lg[0]["mid"] == "m1"
              and lg[0]["outcome"] == "posted" and lg[0]["delay_s"] == 1800, lg)
        rep = run(tmp, c, r)
        check("a second tick posts nothing more", len(r.posts) == 1 and not rep.posted, r.posts)
        check("the journal row is untouched", c.execute("SELECT state, carrier FROM episodes").fetchall() == [("accepted", CAR)])
    finally:
        shutil.rmtree(tmp)

    # rows the relay took first, pending and failed rows are not candidates
    tmp = scratch()
    try:
        c = journal(tmp, [("a", "accepted", 30, "claude-bridge"), ("b", "pending", 29, ""), ("c", "failed", 28, "")])
        r = FakeRelay()
        run(tmp, c, r)
        check("only carrier-accepted rows are candidates", r.posts == [], r.posts)
    finally:
        shutil.rmtree(tmp)

    # already on the relay: not posted again, and the id is finished
    tmp = scratch()
    try:
        c = journal(tmp, [("m1", "accepted", 30, CAR)])
        r = FakeRelay(held=("m1",))
        rep = run(tmp, c, r)
        check("a row the relay holds is not posted again", r.posts == [] and rep.present == ["m1"], r.posts)
        check("it is finished as present", [x["outcome"] for x in log_of(tmp)] == ["present"])
        # the sent ledger: a hand resend wrote it only after a 2xx
        tmp2 = scratch()
        c2 = journal(tmp2, [("m2", "accepted", 30, CAR)])
        with open(os.path.join(tmp2, backfill.SENT_LEDGER_NAME), "w") as f:
            f.write(json.dumps({"id": "m2", "sha256": "x"}) + "\n")
        r2 = FakeRelay()
        run(tmp2, c2, r2)
        check("an id in the sent ledger is not posted", r2.posts == [], r2.posts)
        shutil.rmtree(tmp2)
        # another sender's record carrying the same id is not the sender's own
        tmp3 = scratch()
        c3 = journal(tmp3, [("m3", "accepted", 30, CAR)])
        r3 = FakeRelay(held=("m3",))
        r3.address = "h/someone-else"
        run(tmp3, c3, r3)
        check("a record from another sender does not count as held", [m for m, _ in r3.posts] == ["m3"], r3.posts)
        shutil.rmtree(tmp3)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # relay still down / refusing keeps rows pending; the next return posts them in order
    tmp = scratch()
    try:
        c = journal(tmp, [("m1", "accepted", 40, CAR), ("m2", "accepted", 30, CAR), ("m3", "accepted", 20, CAR)])
        down = FakeRelay(up=False)
        rep = run(tmp, c, down)
        check("a relay that is down leaves every row pending", down.posts == [] and log_of(tmp) == []
              and rep.waiting == ["m1", "m2", "m3"], rep)
        refusing = FakeRelay(refuse=True)
        rep = run(tmp, c, refusing)
        check("a relay that refuses leaves them pending and says so", log_of(tmp) == [] and rep.notes, rep)
        back = FakeRelay()
        rep = run(tmp, c, back)
        check("on return the rows go in the original order", [m for m, _ in back.posts] == ["m1", "m2", "m3"], back.posts)
    finally:
        shutil.rmtree(tmp)

    # a refusal midway: the earlier row is done, the later ones wait and never overtake
    tmp = scratch()
    try:
        c = journal(tmp, [("m1", "accepted", 40, CAR), ("m2", "accepted", 30, CAR), ("m3", "accepted", 20, CAR)])

        class Once(FakeRelay):
            def post(self, mid: str, body: str) -> None:
                if mid == "m2":
                    raise R.RelayError("boom", 500)
                super().post(mid, body)
        r = Once()
        run(tmp, c, r)
        check("a refusal ends the pass: m1 done, m2 and m3 pending, m3 never overtakes",
              [x["mid"] for x in log_of(tmp)] == ["m1"] and [m for m, _ in r.posts] == ["m1"], (log_of(tmp), r.posts))
    finally:
        shutil.rmtree(tmp)

    # over-age: reported once, not posted
    tmp = scratch()
    try:
        c = journal(tmp, [("old", "accepted", 13 * 60, CAR), ("new", "accepted", 30, CAR)])
        r = FakeRelay()
        rep = run(tmp, c, r)
        check("an over-age row is reported and not posted", rep.over_age == ["old"] and [m for m, _ in r.posts] == ["new"], (rep, r.posts))
        rep = run(tmp, c, FakeRelay())
        check("it is reported once", rep.over_age == [] and [x["outcome"] for x in log_of(tmp)] == ["over-age", "posted"], log_of(tmp))
    finally:
        shutil.rmtree(tmp)

    # a page that does not reach back to the row cannot say it is absent
    tmp = scratch()
    try:
        c = journal(tmp, [("m1", "accepted", 5 * 60, CAR)])
        r = FakeRelay(cap_page=2)
        rep = run(tmp, c, r)
        check("a page that does not reach the row posts nothing", r.posts == [] and rep.waiting == ["m1"] and rep.notes, rep)
    finally:
        shutil.rmtree(tmp)

    # no relay configured / no token
    tmp = scratch()
    try:
        c = journal(tmp, [("m1", "accepted", 30, CAR)])
        rep = run(tmp, c, FakeRelay(), configured=False)
        check("an unconfigured project leaves its rows pending", rep.waiting == ["m1"] and log_of(tmp) == [])
        rep = run(tmp, c, None)
        check("no token leaves its rows pending", rep.waiting == ["m1"] and rep.notes)
    finally:
        shutil.rmtree(tmp)

    # a line that does not parse in the log is passed over
    tmp = scratch()
    try:
        with open(os.path.join(tmp, backfill.LOG_NAME), "w") as f:
            f.write('{"mid": "zz", "outc\n')
        backfill._append(os.path.join(tmp, backfill.LOG_NAME), {"mid": "m9", "outcome": "posted"})
        check("the log passes over a line that does not parse", backfill.finished(os.path.join(tmp, backfill.LOG_NAME)) == {"m9"})
    finally:
        shutil.rmtree(tmp)
    print(f"{fails} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
