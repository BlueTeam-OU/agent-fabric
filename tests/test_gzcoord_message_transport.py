#!/usr/bin/env python3
"""Message delivery across the relay and the second carrier, characterised as it is on main (j215, W2-B0 of the
one-owner-per-mechanism plan, agent-fabric ADR-067): the points tests/test_gzcoord_carrier_inbox.py, test_gzcoord_port.py,
test_gzcoord_bypass.py and test_gzcoord_protocol.py do not already pin. Through the real commands (bin/gzcoord-inbox,
bin/gzcoord-send) against a stub relay and, where a carrier is wanted, a fake one on its adapter socket, in the protocol
suite's minimal environment; no network.

Each check says what it pins and which line, when planted with a mutation, turns it red (the mutation table is in the
delivery's PR). A check that records a disagreement with ADR-064, SEMANTICS.md or the inbox's own docstring is marked
EXPECTED_FAILURE: it asserts what the text says, fails today, and the harness reports "expected failure" for it; it turns into
an unexpected pass the day the code agrees, which fails the suite so the mark is removed. Plain script: ok/FAIL, exit 1."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import test_gzcoord_carrier_inbox as C  # noqa: E402 — its World (stub relay, fake carrier), message builders, checks' env
import test_gzcoord_protocol as P  # noqa: E402

ME = C.ME
fails = 0


def check(name: str, ok: bool, detail: str = "", expected_failure: bool = False) -> None:
    """ok/FAIL; an expected failure prints "expected failure" and counts as passing, an unexpected pass counts as failing."""
    global fails
    if expected_failure:
        print(("FAIL (unexpected pass: remove the mark) " if ok else "xfail ") + name)
        fails += 1 if ok else 0
        return
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def request(n: int) -> str:
    return (f"[GZCOORD/1] REQUEST\nFROM: x/y\nROLE: backend-dev\nPROJECT: fixture\nTO: {ME}\nMESSAGE-ID: {C.mid(n)}\n"
            f"SUBJECT: do-{n}\n\nREQUEST:\ndo it\n\nACCEPTANCE:\nok\n")


def request_rec(n: int) -> dict:
    return {"seq": n, "id": f"r{n}", "ts": "T", "sender": "x/y", "content": request(n)}


def without_id(n: int) -> dict:
    return {"seq": n, "id": f"r{n}", "ts": "T", "sender": "x/y",
            "content": C.msg(n).replace(f"MESSAGE-ID: {C.mid(n)}\n", "")}


def break_journal(w: "C.World") -> None:
    """The journal's database where a directory is: the journal cannot take a row, and nothing else of the account changes."""
    w.drain()                      # makes the account's state directory
    d = w.agent_dir() or os.path.join(w.state, "agents", subprocess.run(["id", "-un"], capture_output=True, text=True, timeout=10).stdout.strip())
    os.makedirs(d, exist_ok=True)
    db = os.path.join(d, "episodic.db")
    for suffix in ("", "-wal", "-shm", "-journal"):
        try:
            os.remove(db + suffix)
        except FileNotFoundError:
            pass
    os.makedirs(db)


def main() -> int:
    # ── the relay's acknowledgement waits for the journal, the intake write and the showing ──────────────────────────
    w = C.World([[request_rec(1)]])
    r = w.drain()
    snap = w.at_ack[0] if w.at_ack else {}
    check("the relay is acknowledged once, after the journal row, the queued job and both ledger lines",
          r.returncode == 0 and w.acks == ["r1"]
          and [x[1] for x in snap.get("journal", [])] == [C.mid(1)]                       # journal row first (watch.py: journal before ack)
          and C.mid(1) in json.dumps(snap.get("jobs"))                                    # intake: the REQUEST is on the job list (inbox.with_queued)
          and snap.get("ledger") == [(True, C.mid(1)), (False, C.mid(1))],                # pending and final: the page was shown (show_page)
          f"{r.stdout}{r.stderr}\n{w.acks}\n{snap}")
    check("... and what the session saw was printed whole, the queued line below the message",
          "do it" in r.stdout and "queued as j1: do-1" in r.stdout and r.stdout.index("ACCEPTANCE") < r.stdout.index("queued as j1"),
          r.stdout)
    w.close()

    # ── a copy not shown is never acknowledged ───────────────────────────────────────────────────────────────────────
    # (a) the journal cannot take it
    w = C.World([[]])
    break_journal(w)
    w.pages = [[C.relay_rec(1)]]
    r = w.watch()
    check("the journal cannot keep it (--until-delivery): exit 6, the held line on stdout, nothing shown, nothing acknowledged, no ledger line",
          r.returncode == 6 and "held, not shown" in r.stdout and "subject-1" not in r.stdout and w.acks == [] and w.ledger_lines() == [],
          f"{r.returncode}\n{r.stdout}{r.stderr}\n{w.acks}\n{w.ledger_lines()}")
    check("... the arrival log still has the copy (written before the journal sees it) and the acknowledgement log has none",
          [(x["mid"], x["carrier"]) for x in w.read("gzcoord-arrivals.jsonl")] == [(C.mid(1), "relay")] and w.read("gzcoord-acks.jsonl") == [],
          f"{w.read('gzcoord-arrivals.jsonl')}\n{w.read('gzcoord-acks.jsonl')}")
    w.close()
    # (b) shown to a session that is gone: the write fails after the pending line
    w = C.World([[C.relay_rec(2)]])
    rd, wr = os.pipe()
    os.close(rd)                   # nobody reads stdout: the showing's write fails
    env = {**w.env, "GZCOORD_UNTIL_DELIVERY_DOWN_S": "3"}
    try:
        r = subprocess.run([P.INBOX_CMD, "--until-delivery", "--deadline", "8"], env=env, stdout=wr, stderr=subprocess.PIPE, text=True,
                           timeout=120, stdin=subprocess.DEVNULL)
    finally:
        os.close(wr)
    check("a showing whose write fails is not acknowledged, and leaves only the pending line",
          w.acks == [] and [(bool(x.get("pending")), x["mid"]) for x in w.ledger_lines()] == [(True, C.mid(2))],
          f"{r.returncode}\n{r.stderr}\n{w.acks}\n{w.ledger_lines()}")
    w.pages = [[C.relay_rec(2)]]
    r2 = w.drain()
    check("... the relay shows it again and the next showing says it may repeat, then acknowledges",
          "subject-2" in r2.stdout and "may repeat" in r2.stdout and w.acks == ["r2"], f"{r2.stdout}{r2.stderr}\n{w.acks}")
    w.close()

    # ── the arrival log: one line per relay copy addressed here, the shape ADR-064 rule 11 states ────────────────────
    w = C.World([[C.relay_rec(1), {"seq": 2, "id": "r2", "ts": "T", "sender": "x/y",
                                   "content": C.msg(2).replace(f"TO: {ME}", "TO: x/someone-else")}, without_id(3)]])
    w.drain()
    lines = w.read("gzcoord-arrivals.jsonl")
    check("an arrival line is (mid, addressee, carrier, t, verdict) and nothing else, for a copy addressed here only",
          [sorted(x) for x in lines] == [["addressee", "carrier", "mid", "t", "verdict"]] * 2
          and [x["addressee"] for x in lines] == [ME, ME] and {x["carrier"] for x in lines} == {"relay"}
          and {x["verdict"] for x in lines} == {"unauthenticated"} and lines[0]["mid"] == C.mid(1),
          str(lines))
    check("... a copy with no MESSAGE-ID is logged under the hash of its text, and is in no acknowledgement line",
          lines[1]["mid"].startswith("sha256:") and [x["mid"] for x in w.read("gzcoord-acks.jsonl")] == [C.mid(1)]
          and sorted(w.acks) == ["r1", "r2", "r3"], f"{lines}\n{w.read('gzcoord-acks.jsonl')}\n{w.acks}")
    w.close()
    # a record delivered again to a later process (an acknowledgement the relay never took) is another copy received
    w = C.World([[C.relay_rec(1)]])
    w.ack_down = True
    w.drain()
    w.pages = [[C.relay_rec(1)]]
    w.drain()
    check("the same relay record delivered to a second process is a second arrival line, and its failed acknowledgement a line each",
          [x["mid"] for x in w.read("gzcoord-arrivals.jsonl")] == [C.mid(1)] * 2
          and [x["ok"] for x in w.read("gzcoord-acks.jsonl")] == [False, False], f"{w.read('gzcoord-arrivals.jsonl')}\n{w.read('gzcoord-acks.jsonl')}")
    w.close()
    # the carrier's own arrivals are the carrier's evidence: this inbox logs no arrival for them
    w = C.World([[]], carrier_records=[C.urec(4)])
    r = w.drain()
    check("a message only the carrier has is shown and leaves no line in the inbox's arrival or acknowledgement log",
          "subject-4" in r.stdout and w.read("gzcoord-arrivals.jsonl") == [] and w.read("gzcoord-acks.jsonl") == [],
          f"{r.stdout}{r.stderr}")
    w.close()

    # a retired type (HELLO, SPEC §8) addressed here is acknowledged and never shown; one addressed elsewhere is acknowledged and logs no arrival
    elsewhere = C.msg(3).replace("INFO", "HELLO", 1).replace(f"TO: {ME}", "TO: x/someone-else")
    w = C.World([[{"seq": 1, "id": "r1", "ts": "T", "sender": "x/y", "content": C.msg(1).replace("INFO", "HELLO", 1)}, C.relay_rec(2),
                  {"seq": 3, "id": "r3", "ts": "T", "sender": "x/y", "content": elsewhere}]])
    r = w.drain()
    check("a retired HELLO addressed here is acknowledged and not shown, beside a message that is",
          sorted(w.acks) == ["r1", "r2", "r3"] and "subject-1" not in r.stdout and "subject-2" in r.stdout, f"{r.stdout}{r.stderr}\n{w.acks}")
    arrived = {x["mid"] for x in w.read("gzcoord-arrivals.jsonl")}
    acked = {x["mid"] for x in w.read("gzcoord-acks.jsonl")}
    check("... and every acknowledgement line has an arrival line (inbox.py and ADR-064 rule 11: one per copy addressed here, retired types included)",
          acked <= arrived and C.mid(1) in arrived and C.mid(3) not in arrived,
          f"arrivals {sorted(arrived)}\nacks {sorted(acked)}")
    w.close()

    # ── shown once, whichever arrives first ──────────────────────────────────────────────────────────────────────────
    # the carrier's mismatch copy first, the relay's copy after
    w = C.World([[]], carrier_records=[C.urec(5, "mismatch", frm="x/forged")])
    r = w.drain()
    w.pages = [[C.relay_rec(5, frm="x/forged")]]
    r2 = w.drain()
    check("the carrier's copy first (a FROM mismatch, shown as such), then the relay's: shown once, the relay's acknowledged",
          r.stdout.count("subject-5") == 1 and "FROM mismatch" in r.stdout and "subject-5" not in r2.stdout and w.acks == ["r5"],
          f"{r.stdout}{r.stderr}\n{r2.stdout}\n{w.acks}")
    w.close()
    # a different message that reuses a shown MESSAGE-ID is another message
    w = C.World([[C.relay_rec(6)]])
    w.drain()
    other = C.relay_rec(6)
    other["id"], other["seq"] = "r6b", 7
    other["content"] = other["content"].replace("subject-6", "subject-6-other")
    w.pages = [[other]]
    r = w.drain()
    check("a different text under a shown MESSAGE-ID is shown (the ledger tells them apart by the text's hash)",
          "subject-6-other" in r.stdout and w.acks[-1] == "r6b", f"{r.stdout}{r.stderr}")
    w.close()

    # ── --replay and --history read the relay's record and nothing else ───────────────────────────────────────────────
    w = C.World([[C.relay_rec(1)]], carrier_records=[C.urec(2)])
    w.drain()
    w.history = [C.relay_rec(1)]
    before = (w.ledger_lines(), w.read("gzcoord-arrivals.jsonl"), w.read("gzcoord-acks.jsonl"), list(w.acks))

    def inbox(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([P.INBOX_CMD, *args], env=w.env, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    rp, rj, hi = inbox("--replay", "1"), inbox("--replay", C.mid(1), "--json"), inbox("--history")
    check("--replay and --history show a record the ledger already marked shown, and write no ledger, arrival or acknowledgement line and acknowledge nothing",
          rp.returncode == 0 and "subject-1" in rp.stdout and json.loads(rj.stdout)["addressed"] is True and C.mid(1) in hi.stdout
          and before == (w.ledger_lines(), w.read("gzcoord-arrivals.jsonl"), w.read("gzcoord-acks.jsonl"), list(w.acks)),
          f"{rp.stdout}{rp.stderr}\n{rj.stdout}\n{hi.stdout}{hi.stderr}\n{before}")
    rc = inbox("--replay", C.mid(2))
    check("a message only the carrier brought is not in the relay's record: --replay of its MESSAGE-ID is exit 1, and --history does not list it",
          rc.returncode == 1 and "no message" in rc.stderr and C.mid(2) not in hi.stdout, f"{rc.returncode}\n{rc.stdout}{rc.stderr}\n{hi.stdout}")
    w.close()
    big = C.urec(3)
    big["content"] += "filler line\n" * 3000
    w = C.World([[]], carrier_records=[big])
    r = w.watch()
    check("a carrier-only delivery over the notification cap is cut with the carrier's notice (the journal holds it), never a --replay line",
          r.returncode == 0 and "fabric-history --thread " + C.mid(3) + " --full" in r.stdout and "--replay" not in r.stdout
          and r.stdout.count("filler line") < 3000, f"{r.returncode}\n{r.stdout[-600:]}{r.stderr}")
    w.close()

    # ── the relay down: what the watch says, and when ────────────────────────────────────────────────────────────────
    w = C.World([])
    w.relay_down = True
    r = w.watch()
    gave_up = [x for x in r.stdout.splitlines() if "unreachable" in x]
    check("--until-delivery, relay down past its bound: exit 5, one give-up line on stdout and no relay-down line before it",
          r.returncode == 5 and len(gave_up) == 1 and len(r.stdout.splitlines()) == 1, f"{r.returncode}\n{r.stdout}{r.stderr}")
    w.close()
    # --follow tells the session when the relay drops and when it returns (SEMANTICS.md, "When the relay is down")
    w = C.World([[]])
    w.relay_down = True
    pr = subprocess.Popen([P.INBOX_CMD, "--follow"], env=w.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          stdin=subprocess.DEVNULL)
    try:
        time.sleep(3)
        w.relay_down = False
        w.pages = []
        time.sleep(34)             # the retry is 30 s
    finally:
        pr.terminate()
        out, err = pr.communicate(timeout=30)
    watch_lines = [x for x in out.splitlines() if x.startswith("gzcoord watch:")]
    check("--follow: one line when the relay drops and one when it answers again, on stdout, in that order",
          len(watch_lines) == 2 and "unreachable" in watch_lines[0] and "back" in watch_lines[1], f"{out}{err}")
    w.close()
    # --until-delivery rides out a drop it recovers from without a word
    w = C.World([[]])
    w.relay_down = True
    env = {**w.env, "GZCOORD_UNTIL_DELIVERY_DOWN_S": "60"}
    pr = subprocess.Popen([P.INBOX_CMD, "--until-delivery", "--deadline", "40"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, stdin=subprocess.DEVNULL)
    try:
        time.sleep(3)
        w.relay_down = False
        out, err = pr.communicate(timeout=60)
    finally:
        if pr.poll() is None:
            pr.kill()
    check("--until-delivery: a relay that drops and returns inside its bound is not told to the session (SEMANTICS.md 'When the relay is down'): "
          "no unreachable line and no back line, the watch ending at its deadline with the quiet line and nothing on stderr",
          pr.returncode == 0 and out.startswith("gzcoord inbox: quiet for ") and len(out.splitlines()) == 1
          and not any("unreachable" in x or "back" in x for x in out.splitlines()) and "unreachable" not in err,
          f"{pr.returncode}\n{out}{err}")
    w.close()

    # ── send: what is posted, what is recorded, what a relay error leaves ───────────────────────────────────────────
    def sent(relay_url: str, text: str, base: str, **env: str) -> "P.Ran":
        f = os.path.join(base, "m.txt")
        with open(f, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return P.run_cmd(P.SEND_CMD, [f], P.send_env(relay_url, base, AGENT_FABRIC_STATE_DIR=os.path.join(base, "state"), **env))

    def sent_lines(base: str) -> list[dict]:
        try:
            with open(os.path.join(base, "state", "agents", P.LOGIN, "gzcoord-sent.jsonl"), encoding="utf-8") as fh:
                return [json.loads(x) for x in fh if x.strip()]
        except FileNotFoundError:
            return []

    relay = P.Relay()
    base = P.scratch("transport-send-")
    r = sent(relay.url, P.VALID, base)
    lines = sent_lines(base)
    check("send: the confirmed post is recorded as one line (id, sha256 of the text, the relay's seq, at) beside the account's journal",
          r.code == 0 and len(lines) == 1 and sorted(lines[0]) == ["at", "id", "seq", "sha256"] and lines[0]["id"] == P.VALID_ID
          and lines[0]["seq"] == 42 and lines[0]["sha256"] == hashlib.sha256(P.VALID.encode("utf-8")).hexdigest()
          and lines[0]["at"].endswith("Z"), f"{r.code} {r.err}\n{lines}")
    again = sent(relay.url, P.VALID, base)
    check("... the same message sent again passes, is posted again and recorded again (one line per confirmed post)",
          again.code == 0 and len(relay.posts) == 2 and len(sent_lines(base)) == 2, f"{again.err}\n{sent_lines(base)}")
    relay.close()
    for label, status in (("a 5xx", 503), ("a 4xx", 400)):
        relay = P.Relay(status=status)
        base = P.scratch("transport-send-")
        r = sent(relay.url, P.VALID, base)
        check(f"send: {label} from the relay is exit 3 with nothing on stdout and no line in the sent ledger",
              r.code == 3 and r.out == "" and sent_lines(base) == [] and len(relay.hits) >= 1, f"{r.code}\n{r.out}{r.err}\n{sent_lines(base)}")
        relay.close()
    # A post whose answer was lost is not in the sent ledger (send.py's docstring: an edited resend is not caught THERE). The journal
    # keeps the message before it leaves, and catches it; with the journal off nothing does.
    for journal_off in (False, True):
        relay = P.Relay(status=503)
        base = P.scratch("transport-send-")
        extra = {"GZCOORD_JOURNAL": "off"} if journal_off else {}
        sent(relay.url, P.VALID, base, **extra)
        relay.close()
        relay = P.Relay()
        edited = sent(relay.url, P.VALID.replace("hello", "hello, edited"), base, **extra)
        if journal_off:
            check("send, journal off: after a lost answer an edited resend under the same id goes out and is recorded (the documented limit)",
                  edited.code == 0 and len(relay.posts) == 1 and [x["id"] for x in sent_lines(base)] == [P.VALID_ID],
                  f"{edited.err}\n{sent_lines(base)}")
            third = sent(relay.url, P.VALID, base, **extra)
            check("... and the original text under that id is then the one refused, by the sent ledger",
                  third.code == 2 and "already went out with a different message" in third.err and len(relay.posts) == 1,
                  f"{third.code} {third.err}")
        else:
            check("send, journal on: the same edited resend is refused by the journal before it leaves: exit 2, nothing posted, nothing recorded",
                  edited.code == 2 and "already in this journal with another body" in edited.err and relay.posts == []
                  and sent_lines(base) == [], f"{edited.code} {edited.err}\n{sent_lines(base)}")
        relay.close()

    for d in P.SCRATCH:
        shutil.rmtree(d, ignore_errors=True)
    print(f"\ntest_gzcoord_message_transport: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
