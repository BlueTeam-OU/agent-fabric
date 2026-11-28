#!/usr/bin/env python3
"""Message delivery over the InterWeave carrier, characterised through the real commands (j215, W2-B0 of the
one-owner-per-mechanism plan, agent-fabric ADR-067; the carrier is the only transport since W15): the points
tests/test_gzcoord_carrier_inbox.py, test_gzcoord_port.py, test_gzcoord_bypass.py and test_gzcoord_protocol.py do not already
pin. Through bin/gzcoord-inbox and bin/gzcoord-send against a carrier stand-in on its adapter socket (P.Carrier), in the
protocol suite's minimal environment; no network.

Each check says what it pins and which line, when planted with a mutation, turns it red. A check that records a disagreement
with ADR-064, SEMANTICS.md or the inbox's own docstring is marked EXPECTED_FAILURE: it asserts what the text says, fails today,
and the harness reports "expected failure" for it; it turns into an unexpected pass the day the code agrees, which fails the
suite so the mark is removed. Plain script: ok/FAIL, exit 1."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import test_gzcoord_carrier_inbox as C  # noqa: E402 — its World (carrier stand-in), message builders, checks' env
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


def snapshot(w: "C.World") -> dict:
    """The account's journal rows, job list and ledger as they are now."""
    d = w.agent_dir()
    rows: list = []
    try:
        db = sqlite3.connect(os.path.join(d, "episodic.db"), timeout=5)
        try:
            rows = db.execute("SELECT direction, message_id FROM episodes").fetchall()
        finally:
            db.close()
    except sqlite3.Error:
        pass
    try:
        with open(os.path.join(d, "jobs.json"), encoding="utf-8") as fh:
            jobs = json.load(fh)
    except (OSError, ValueError):
        jobs = {}
    return {"journal": rows, "jobs": jobs, "ledger": [(bool(x.get("pending")), x["mid"]) for x in w.ledger_lines()]}


def main() -> int:
    # ── a record the carrier lists waits for the journal, the intake write and the showing ───────────────────────────
    w = C.World([P.record(request(1))])
    r = w.drain()
    snap = snapshot(w)
    check("a delivered REQUEST is shown once, with the queued job and both ledger lines (the carrier journals it, not the inbox)",
          r.returncode == 0 and r.stdout.count("do-1") >= 1 and snap["journal"] == []
          and C.mid(1) in json.dumps(snap["jobs"])                                         # intake: the REQUEST is on the job list (inbox.with_queued)
          and snap["ledger"] == [(True, C.mid(1)), (False, C.mid(1))],                     # pending and final: the page was shown (show_page)
          f"{r.stdout}{r.stderr}\n{snap}")
    check("... and what the session saw was printed whole, the queued line below the message",
          "do it" in r.stdout and "queued as j1: do-1" in r.stdout and r.stdout.index("ACCEPTANCE") < r.stdout.index("queued as j1"),
          r.stdout)
    w.close()

    # ── a record not shown is not settled ────────────────────────────────────────────────────────────────────────────
    # shown to a session that is gone: the write fails after the pending line
    w = C.World([C.urec(2)])
    rd, wr = os.pipe()
    os.close(rd)                   # nobody reads stdout: the showing's write fails
    env = {**w.env, "GZCOORD_UNTIL_DELIVERY_DOWN_S": "3"}
    try:
        r = subprocess.run([P.INBOX_CMD, "--until-delivery", "--deadline", "8"], env=env, stdout=wr, stderr=subprocess.PIPE, text=True,
                           timeout=120, stdin=subprocess.DEVNULL)
    finally:
        os.close(wr)
    check("a showing whose write fails leaves only the pending line",
          [(bool(x.get("pending")), x["mid"]) for x in w.ledger_lines()] == [(True, C.mid(2))],
          f"{r.returncode}\n{r.stderr}\n{w.ledger_lines()}")
    r2 = w.drain()
    check("... the carrier lists it again and the next showing says it may repeat",
          "subject-2" in r2.stdout and "may repeat" in r2.stdout, f"{r2.stdout}{r2.stderr}")
    w.close()

    # the carrier's own arrivals are the carrier's evidence: this inbox logs no arrival for them
    w = C.World([C.urec(4)])
    r = w.drain()
    check("a record the carrier lists is shown and leaves no line in the inbox's arrival log",
          "subject-4" in r.stdout and w.read("gzcoord-arrivals.jsonl") == [], f"{r.stdout}{r.stderr}")
    w.close()

    # a retired type (HELLO, SPEC §8) is never shown, whichever record it came in
    w = C.World([P.record(C.msg(1).replace("INFO", "HELLO", 1)), C.urec(2)])
    r = w.drain()
    check("a retired HELLO the carrier lists is not shown, beside a message that is",
          "subject-1" not in r.stdout and "subject-2" in r.stdout, f"{r.stdout}{r.stderr}")
    w.close()

    # ── shown once ───────────────────────────────────────────────────────────────────────────────────────────────────
    # a different message that reuses a shown MESSAGE-ID is another message
    w = C.World([C.urec(6)])
    w.drain()
    other = C.urec(6)
    other["content"] = other["content"].replace("subject-6", "subject-6-other")
    w.records[:] = [other]
    r = w.drain()
    check("a different text under a shown MESSAGE-ID is shown (the ledger tells them apart by the text's hash)",
          "subject-6-other" in r.stdout, f"{r.stdout}{r.stderr}")
    w.close()

    # ── --replay and --history read the journal, and write nothing ───────────────────────────────────────────────────
    w = C.World([C.urec(2)])
    P.seed_journal(w.env, (C.msg(2), None))      # what the carrier journaled on arrival: --replay and --history read nothing else
    w.drain()
    before = (w.ledger_lines(), w.read("gzcoord-arrivals.jsonl"), list(w.carrier.ops()))

    def inbox(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([P.INBOX_CMD, *args], env=w.env, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    rp, rj, hi = inbox("--replay", C.mid(2)), inbox("--replay", C.mid(2), "--json"), inbox("--history")
    check("--replay and --history show a record the ledger already marked shown, and write no ledger or arrival line and ask the carrier nothing",
          rp.returncode == 0 and "subject-2" in rp.stdout and json.loads(rj.stdout)["addressed"] is True and C.mid(2) in hi.stdout
          and before == (w.ledger_lines(), w.read("gzcoord-arrivals.jsonl"), list(w.carrier.ops())),
          f"{rp.stdout}{rp.stderr}\n{rj.stdout}\n{hi.stdout}{hi.stderr}\n{before}")
    rc = inbox("--replay", C.mid(3))
    check("a message not in the journal: --replay of its MESSAGE-ID is exit 1, and --history does not list it",
          rc.returncode == 1 and "no message" in rc.stderr and C.mid(3) not in hi.stdout, f"{rc.returncode}\n{rc.stdout}{rc.stderr}\n{hi.stdout}")
    w.close()
    big = C.urec(3)
    big["content"] += "filler line\n" * 3000
    w = C.World([big])
    r = w.watch()
    check("a delivery over the notification cap is cut with the carrier's notice (the journal holds it), never a --replay line",
          r.returncode == 0 and "fabric-history --thread " + C.mid(3) + " --full" in r.stdout and "--replay" not in r.stdout
          and r.stdout.count("filler line") < 3000, f"{r.returncode}\n{r.stdout[-600:]}{r.stderr}")
    w.close()

    # ── the carrier not answering: what the watch says, and when ─────────────────────────────────────────────────────
    # the seam shortens the retry for the cases in this suite; the production value is still 30 s
    r = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, sys.argv[1]); from gzcoord import inbox; print(inbox.RETRY_S)",
                        os.path.join(C.ROOT, "tools", "fabric")], env={"PATH": os.environ["PATH"]}, capture_output=True, text=True, timeout=60)
    check("the retry between tries while the carrier does not answer is 30 s unless a test shortens it", r.stdout.strip() == "30.0", f"{r.stdout}{r.stderr}")
    # --until-delivery rides out a drop it recovers from without a word
    env = P.inbox_env()
    env.update({"GZCOORD_UNTIL_DELIVERY_DOWN_S": "60", "GZCOORD_RETRY_S": C.RETRY_S})
    pr = subprocess.Popen([P.INBOX_CMD, "--until-delivery", "--deadline", "8"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, stdin=subprocess.DEVNULL)
    carrier = None
    try:
        # no carrier for the first tries (without them the drop was never exercised), then one; it is asked after it came up
        # (a watch that slept to its deadline instead would never ask)
        time.sleep(2)
        carrier = P.Carrier(run=env["XDG_RUNTIME_DIR"], hold_s=0.2)
        t0 = time.monotonic()
        while "wait" not in carrier.ops() and time.monotonic() - t0 < 5:
            time.sleep(0.05)
        asked = "wait" in carrier.ops()
        out, err = pr.communicate(timeout=60)
    finally:
        if pr.poll() is None:
            pr.kill()
        if carrier is not None:
            carrier.close()
    check("--until-delivery: a carrier that is down and answers again inside its bound is not told to the session: no down line and no "
          "back line, the watch ending at its deadline with the quiet line and nothing on stderr",
          pr.returncode == 0 and out.startswith("gzcoord inbox: quiet for ") and len(out.splitlines()) == 1
          and not any("not answering" in x or "answers again" in x for x in out.splitlines()) and err.strip() == "" and asked,
          f"{pr.returncode}\nasked={asked}\n{out}{err}")

    # ── send: what is posted, what is recorded, what a refusal leaves ────────────────────────────────────────────────
    def sent(carrier: "P.Carrier | None", text: str, base: str, **env: str) -> "P.Ran":
        f = os.path.join(base, "m.txt")
        with open(f, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return P.run_cmd(P.SEND_CMD, [f], P.send_env(carrier, base, AGENT_FABRIC_STATE_DIR=os.path.join(base, "state"), **env))

    def sent_lines(base: str) -> list[dict]:
        try:
            with open(os.path.join(base, "state", "agents", P.LOGIN, "gzcoord-sent.jsonl"), encoding="utf-8") as fh:
                return [json.loads(x) for x in fh if x.strip()]
        except FileNotFoundError:
            return []

    carrier = P.Carrier()
    base = P.scratch("transport-send-")
    r = sent(carrier, P.VALID, base)
    lines = sent_lines(base)
    check("send: the confirmed post is recorded as one line (id, sha256 of the text, no seq, at) beside the account's journal",
          r.code == 0 and len(lines) == 1 and sorted(lines[0]) == ["at", "id", "seq", "sha256"] and lines[0]["id"] == P.VALID_ID
          and lines[0]["seq"] is None and lines[0]["sha256"] == hashlib.sha256(P.VALID.encode("utf-8")).hexdigest()
          and lines[0]["at"].endswith("Z"), f"{r.code} {r.err}\n{lines}")
    again = sent(carrier, P.VALID, base)
    check("... the same message sent again passes, is posted again and recorded again (one line per confirmed post)",
          again.code == 0 and len(carrier.posts) == 2 and len(sent_lines(base)) == 2, f"{again.err}\n{sent_lines(base)}")
    carrier.close()
    for label, refuse in (("the carrier refusing every recipient", P.Carrier(send={"ok": False, "error": "no", "carried": 1, "queued": 0})),
                          ("no carrier running", None)):
        base = P.scratch("transport-send-")
        r = sent(refuse, P.VALID, base)
        check(f"send: {label} is exit 3 with nothing on stdout and no line in the sent ledger",
              r.code == 3 and r.out == "" and sent_lines(base) == [], f"{r.code}\n{r.out}{r.err}\n{sent_lines(base)}")
        if refuse is not None:
            refuse.close()
    # A post whose answer was lost is not in the sent ledger (send.py's docstring: an edited resend is not caught THERE). The journal
    # keeps the message before it leaves, and catches it; with the journal off nothing does.
    for journal_off in (False, True):
        lost = P.Carrier(send={"ok": False, "error": "the answer was lost"})    # no queued count: recipients may be recorded
        base = P.scratch("transport-send-")
        extra = {"GZCOORD_JOURNAL": "off"} if journal_off else {}
        sent(lost, P.VALID, base, **extra)
        lost.close()
        carrier = P.Carrier()
        edited = sent(carrier, P.VALID.replace("hello", "hello, edited"), base, **extra)
        if journal_off:
            check("send, journal off: after a lost answer an edited resend under the same id goes out and is recorded (the documented limit)",
                  edited.code == 0 and len(carrier.posts) == 1 and [x["id"] for x in sent_lines(base)] == [P.VALID_ID],
                  f"{edited.err}\n{sent_lines(base)}")
            third = sent(carrier, P.VALID, base, **extra)
            check("... and the original text under that id is then the one refused, by the sent ledger",
                  third.code == 2 and "already went out with a different message" in third.err and len(carrier.posts) == 1,
                  f"{third.code} {third.err}")
        else:
            check("send, journal on: the same edited resend is refused by the journal before it leaves: exit 2, nothing posted, nothing recorded",
                  edited.code == 2 and "already in this journal with another body" in edited.err and carrier.posts == []
                  and sent_lines(base) == [], f"{edited.code} {edited.err}\n{sent_lines(base)}")
        carrier.close()

    for d in P.SCRATCH:
        shutil.rmtree(d, ignore_errors=True)
    print(f"\ntest_gzcoord_message_transport: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
