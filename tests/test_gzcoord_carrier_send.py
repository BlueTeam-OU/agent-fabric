#!/usr/bin/env python3
"""bin/gzcoord-send with the InterWeave carrier beside the relay (ADR-064
rules 6-8, CARRIER-CONTRACT.md §6), through the real command in the protocol
suite's minimal environment: the carrier's adapter socket is a fake answering
the contract's ops. What is held: every message goes to both; the journal row
is accepted when either accepts and keeps the FIRST accepter's provenance; a
relay that fails while the carrier takes the message leaves the row accepted
by InterWeave and the exit status the relay's; a carrier that is there and
does not answer, or refuses, changes neither the exit status nor the row;
with no carrier, and with the journal off, nothing is asked. Plain script:
prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from gzcoord.carrier import server  # noqa: E402
import test_gzcoord_protocol as P  # noqa: E402 — its relay stub, scratch and command environment

fails = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def rows(state: str, store: str) -> list[tuple]:
    code = ("import sqlite3,json,sys\nsys.path.insert(0, sys.argv[1]); import episodic\n"
            "c = sqlite3.connect(episodic.db_path())\n"
            "print(json.dumps(c.execute('SELECT direction, state, carrier, carrier_seq FROM episodes').fetchall()))")
    import subprocess
    r = subprocess.run([sys.executable, "-c", code, P.TOOLS], capture_output=True, text=True, timeout=60,
                       env={**os.environ, "AGENT_FABRIC_STATE_DIR": state, "AGENT_FABRIC_SECRET_STORE": store})
    if "no such table" in r.stderr:
        return []      # a send with the journal off made no journal
    assert r.returncode == 0, r.stderr
    return [tuple(x) for x in json.loads(r.stdout)]


class Fake:
    """A carrier's adapter socket under a runtime dir of its own."""

    def __init__(self, reply: dict) -> None:
        self.run = P.scratch("run-")
        self.requests: list[dict] = []
        self.reply = reply
        self.srv = server.Server(server.socket_path(self.run), self._handle)

    def _handle(self, req: dict) -> dict:
        self.requests.append(req)
        return self.reply

    def close(self) -> None:
        self.srv.close()


def send(relay_status: int, run: str, **env: str):
    relay = P.Relay(status=relay_status)
    base = P.scratch("send-journal-")
    state, store = os.path.join(base, "state"), P.id_store()
    try:
        r = P.send_with(relay.url, P.VALID, AGENT_FABRIC_STATE_DIR=state, AGENT_FABRIC_SECRET_STORE=store,
                        XDG_RUNTIME_DIR=run, **env)
    finally:
        relay.close()
    return r, rows(state, store)


def send_in(mode_name: str, relay_status: int, run: str, **env: str):
    """gzcoord-send of the fixture message on an account in `mode_name`; the relay stub's posts are returned beside."""
    from gzcoord.transport import mode
    relay = P.Relay(status=relay_status)
    base = P.scratch("send-mode-")
    state, store = os.path.join(base, "state"), P.id_store()
    agent = os.path.join(state, "agents", P.LOGIN)
    os.makedirs(agent)
    mode.write(mode_name, "h1/op", agent)
    try:
        r = P.send_with(relay.url, P.VALID, AGENT_FABRIC_STATE_DIR=state, AGENT_FABRIC_SECRET_STORE=store, XDG_RUNTIME_DIR=run, **env)
        posts = len(relay.posts)
    finally:
        relay.close()
    return r, rows(state, store), posts


def carrier_primary_cases() -> None:
    """The four outcomes of Adapter.post as gzcoord-send reports them when the carrier is the transport of record (cutover W8):
    accepted is the only exit 0; every other is exit 3 with a line, and the pending row is failed only when the carrier
    provably recorded nothing."""
    f = Fake({"ok": True, "carried": 3, "queued": 3, "posted": 0})
    r, db, posts = send_in("carrier-only", 200, f.run)
    check("W8 accepted: exit 0, one stdout line with the id and no seq, the row the carrier's, the relay never posted",
          r.code == 0 and r.out == f"sent INFO {P.VALID_ID}\n" and db == [("outbound", "accepted", "interweave", None)] and posts == 0,
          f"{r.code} {r.out!r} {r.err} {db} {posts}")
    f.close()

    f = Fake({"ok": True, "carried": 0, "queued": 0, "posted": 0})
    r, db, posts = send_in("carrier-only", 200, f.run)
    check("W8 not-carried: exit 3, nothing on stdout, said as not sent, the pending row failed",
          r.code == 3 and r.out == "" and "not sent" in r.err and db == [("outbound", "failed", "claude-bridge", None)], f"{r.code} {r.err} {db}")
    f.close()

    r, db, posts = send_in("carrier-only", 200, P.scratch("run-"))
    check("W8 absent: exit 3, the line names the command that says why, the row failed, the relay never posted",
          r.code == 3 and "not sent" in r.err and "OBSERVATION" in r.err and "fabric-ctl" not in r.err
          and db == [("outbound", "failed", "claude-bridge", None)] and posts == 0, f"{r.code} {r.err} {db} {posts}")

    f = Fake({"ok": False, "error": "disk", "carried": 3, "queued": 0})
    r, db, posts = send_in("carrier-only", 200, f.run)
    check("W8 failed with nothing recorded: exit 3, not sent, the row failed",
          r.code == 3 and "not sent" in r.err and db == [("outbound", "failed", "claude-bridge", None)], f"{r.code} {r.err} {db}")
    f.close()

    f = Fake({"ok": False, "error": "disk", "carried": 3, "queued": 1})
    r, db, posts = send_in("carrier-only", 200, f.run)
    check("W8 failed with some recipients recorded: exit 3, outcome unknown, the row stays pending",
          r.code == 3 and "outcome unknown" in r.err and "same id" in r.err and "keeps retrying it until it is receipted" in r.err and db == [("outbound", "pending", None, None)],
          f"{r.code} {r.err} {db}")
    f.close()

    r, db, posts = send_in("carrier-record", 200, P.scratch("run-"))
    check("W8 carrier-record, no carrier, the relay taking it: still exit 3, and the relay's copy is said, not counted",
          r.code == 3 and "not sent" in r.err and "the relay took a copy of it as well" in r.err and posts == 1, f"{r.code} {r.err} {posts}")
    check("  and the row is the relay's accept, in the journal's name for the relay, the second transport's",
          db == [("outbound", "accepted", "claude-bridge", None)], str(db))


def sent_ledger_cases() -> None:
    """The sent ledger means "the relay has it" (backfill skips an id on it). With the carrier as the record the relay
    is a mirror: its failure leaves the id off the ledger so the next backfill posts it; relay-record is unchanged."""
    def ledger_ids(mode_name: str, relay_status: int, run: str, **env: str) -> tuple:
        from gzcoord.transport import mode
        relay = P.Relay(status=relay_status)
        base = P.scratch("send-ledger-")
        state, store = os.path.join(base, "state"), P.id_store()
        agent = os.path.join(state, "agents", P.LOGIN)
        os.makedirs(agent)
        mode.write(mode_name, "h1/op", agent)
        try:
            r = P.send_with(relay.url, P.VALID, AGENT_FABRIC_STATE_DIR=state, AGENT_FABRIC_SECRET_STORE=store, XDG_RUNTIME_DIR=run, **env)
        finally:
            relay.close()
        try:
            with open(os.path.join(agent, "gzcoord-sent.jsonl"), encoding="utf-8") as fh:
                ids = [json.loads(x)["id"] for x in fh if x.strip() and "id" in json.loads(x)]
        except FileNotFoundError:
            ids = []
        return r, ids

    f = Fake({"ok": True, "carried": 3, "queued": 3, "posted": 0})
    r, ids = ledger_ids("carrier-record", 503, f.run)
    check("carrier-record, the carrier taking it and the relay mirror failing: exit 0 and the id is NOT on the sent ledger",
          r.code == 0 and ids == [], f"{r.code} {r.err} {ids}")
    f.close()
    f = Fake({"ok": True, "carried": 3, "queued": 3, "posted": 0})
    r, ids = ledger_ids("carrier-record", 200, f.run)
    check("  positive control: the relay mirror accepting puts the id on the ledger",
          r.code == 0 and ids == [P.VALID_ID], f"{r.code} {r.err} {ids}")
    f.close()
    f = Fake({"ok": True, "carried": 3, "queued": 3, "posted": 0})
    r, ids = ledger_ids("relay-record", 200, f.run)
    check("relay-record is unchanged: the relay's accept is on the ledger", r.code == 0 and ids == [P.VALID_ID], f"{r.code} {r.err} {ids}")
    f.close()
    for label, mode_name, env in (("carrier-only", "carrier-only", {}),
                                  ("GZCOORD_TRANSPORT_MODE=carrier-only on a relay-record account", "relay-record",
                                   {"GZCOORD_TRANSPORT_MODE": "carrier-only"}),
                                  ("GZCOORD_TRANSPORT_MODE=carrier-only on a carrier-record account", "carrier-record",
                                   {"GZCOORD_TRANSPORT_MODE": "carrier-only"})):
        f = Fake({"ok": True, "carried": 3, "queued": 3, "posted": 0})
        r, ids = ledger_ids(mode_name, 503, f.run, **env)
        check(f"{label}: the carrier alone takes it (exit 0) and the id is NOT on the sent ledger, so it is not skipped as on the relay",
              r.code == 0 and ids == [], f"{r.code} {r.err} {ids}")
        f.close()
    # The ledger's other job: an id spent with one body is refused for another, whatever the relay did and with the
    # journal off, where the journal's own check does not run (review F1).
    for label, mode_name, env in (("carrier-record", "carrier-record", {}), ("carrier-only", "carrier-only", {}),
                                  ("relay-record", "relay-record", {})):
        from gzcoord.transport import mode
        f = Fake({"ok": True, "carried": 3, "queued": 3, "posted": 0})
        relay = P.Relay()
        base = P.scratch("send-reuse-")
        state, store = os.path.join(base, "state"), P.id_store()
        agent = os.path.join(state, "agents", P.LOGIN)
        os.makedirs(agent)
        mode.write(mode_name, "h1/op", agent)
        try:
            kw = dict(AGENT_FABRIC_STATE_DIR=state, AGENT_FABRIC_SECRET_STORE=store, XDG_RUNTIME_DIR=f.run, GZCOORD_JOURNAL="off")
            first = P.send_with(relay.url, P.VALID, **kw)
            second = P.send_with(relay.url, P.VALID.replace("hello", "hello, edited"), **kw)
            again = P.send_with(relay.url, P.VALID, **kw)
        finally:
            relay.close()
        check(f"{label}, journal off: the same id with another body is refused (exit 2); the same message again passes",
              first.code == 0 and second.code == 2 and "already went out" in second.err and again.code == 0,
              f"{first.code} {second.code} {second.err} {again.code}")
        f.close()
    f = Fake({"ok": False, "error": "down", "carried": 0, "queued": 0})
    r, ids = ledger_ids("relay-record", 200, f.run)
    check("relay-record, the carrier mirror failing: still on the ledger", r.code == 0 and ids == [P.VALID_ID], f"{r.code} {r.err} {ids}")
    f.close()


def journal_off_cases() -> None:
    """D7 (cutover plan, owner 2026-11-15): a GZCOORD_JOURNAL=off send goes through the mode's own primary, says so, and
    leaves no journal row; relay-record's route is the relay alone as before."""
    bypass = "GZCOORD_JOURNAL=off"
    for m in ("carrier-record", "carrier-only"):
        f = Fake({"ok": True, "carried": 3, "queued": 3, "posted": 0})
        r, db, posts = send_in(m, 200, f.run, GZCOORD_JOURNAL="off")
        check(f"D7 {m}: the carrier takes the send (exit 0, its id line), the relay is not posted, the bypass line is said, no journal row",
              r.code == 0 and r.out == f"sent INFO {P.VALID_ID}\n" and posts == 0 and bypass in r.err and db == []
              and [q["op"] for q in f.requests] == ["send"], f"{r.code} {r.out!r} {r.err} {db} {posts} {f.requests}")
        f.close()
        r, db, posts = send_in(m, 200, P.scratch("run-"), GZCOORD_JOURNAL="off")
        check(f"D7 {m}: no carrier running is the carrier's failure (exit 3), never a fall back to the relay",
              r.code == 3 and "not sent" in r.err and "OBSERVATION" in r.err and posts == 0 and bypass in r.err, f"{r.code} {r.err} {posts}")
    f = Fake({"ok": True, "carried": 3, "queued": 3, "posted": 0})
    r, db, posts = send_in("relay-record", 200, f.run, GZCOORD_JOURNAL="off")
    check("D7 relay-record unchanged: the relay alone takes it, the carrier is not asked, the bypass line is said",
          r.code == 0 and posts == 1 and f.requests == [] and bypass in r.err and r.out.startswith("sent seq "), f"{r.code} {r.err} {posts}")
    f.close()


def mirror_log_cases() -> None:
    """ADR-064 rule 11, the sender's durable line: a mirror send the carrier did not accept leaves {mid, t, outcome, reason} in
    gzcoord-mirror.jsonl beside gzcoord-sent.jsonl, one outcome each; an accepted send leaves none (the positive control).
    The parity report reads it (test_gzcoord_carrier_parity.py); the mutation that drops the write fails each case here."""
    def logged(run: str, relay_status: int = 200, seed: bytes = b"", **env: str) -> tuple:
        relay = P.Relay(status=relay_status)
        base = P.scratch("send-mirrorlog-")
        state, store = os.path.join(base, "state"), P.id_store()
        agent = os.path.join(state, "agents", P.LOGIN)
        os.makedirs(agent)
        if seed:
            with open(os.path.join(agent, "gzcoord-mirror.jsonl"), "wb") as fh:
                fh.write(seed)
        try:
            r = P.send_with(relay.url, P.VALID, AGENT_FABRIC_STATE_DIR=state, AGENT_FABRIC_SECRET_STORE=store, XDG_RUNTIME_DIR=run, **env)
        finally:
            relay.close()
        try:
            with open(os.path.join(agent, "gzcoord-mirror.jsonl"), encoding="utf-8", errors="replace") as fh:
                lines = [json.loads(x) for x in fh if x.strip().startswith('{')]
        except FileNotFoundError:
            lines = None
        return r, lines

    def one(name: str, r, lines, outcome: str, reason_has: str) -> None:
        line = (lines or [{}])[0]
        check(f"{name}: exit 0 and one line {{mid, t, outcome {outcome}, reason}}",
              r.code == 0 and lines is not None and len(lines) == 1 and set(line) == {"mid", "t", "outcome", "reason"}
              and line["mid"] == P.VALID_ID and line["outcome"] == outcome and reason_has in line["reason"]
              and len(line["t"]) == 20 and line["t"].endswith("Z"), f"{r.code} {r.err} {lines}")

    r, lines = logged(P.scratch("run-"))
    one("mirror log, no carrier running (absent)", r, lines, "absent", "no InterWeave carrier")
    f = Fake({"ok": True, "carried": 0, "queued": 0, "posted": 0})
    r, lines = logged(f.run)
    one("mirror log, no roster member carries it (not-carried)", r, lines, "not-carried", "no roster member")
    f.close()
    f = Fake({"ok": False, "error": "no roster"})
    r, lines = logged(f.run)
    one("mirror log, the carrier refuses (failed)", r, lines, "failed", "refused (no roster)")
    f.close()
    f = Fake({"ok": True, "carried": 3, "queued": 1, "posted": 0})
    r, lines = logged(f.run)
    one("mirror log, not every recipient recorded (failed)", r, lines, "failed", "not every recipient")
    f.close()
    dead = P.scratch("run-")      # a socket path with nothing listening: the carrier is there and does not answer
    os.makedirs(os.path.dirname(server.socket_path(dead)))
    open(server.socket_path(dead), "w").close()
    r, lines = logged(dead)
    one("mirror log, a carrier that does not answer (no-answer)", r, lines, "no-answer", "did not answer")
    f = Fake({"ok": True, "carried": 3, "queued": 3, "posted": 0})
    r, lines = logged(f.run)
    check("  positive control: a carrier that accepts leaves no line", r.code == 0 and lines is None, f"{r.code} {r.err} {lines}")
    f.close()
    f = Fake({"ok": False, "error": "no roster"})
    r, lines = logged(f.run, seed=b"\xff\xfe not utf-8\n" * 30000)
    check("  a log with bytes that are not UTF-8, over its bound: the send ends 0 with its stdout line, says nothing of the log, the new line is there and the log is trimmed",
          r.code == 0 and r.out.startswith("sent seq 42 INFO ") and "mirror refusal log" not in r.err
          and lines is not None and lines[-1]["mid"] == P.VALID_ID and len(lines) < 100, f"{r.code} {r.out!r} {r.err} {lines and len(lines)}")
    f.close()
    f = Fake({"ok": False, "error": "no roster"})
    r, lines = logged(f.run, 500)
    check("  the log never changes the status: the relay failing too is still exit 3, and the line is there",
          r.code == 3 and lines is not None and lines[0]["outcome"] == "failed", f"{r.code} {r.err} {lines}")
    f.close()
    f = Fake({"ok": False, "error": "no roster"})
    r, lines = logged(f.run, GZCOORD_JOURNAL="off")
    check("  with the journal off no mirror is asked and nothing is logged", r.code == 0 and f.requests == [] and lines is None, f"{r.code} {lines}")
    f.close()


def main() -> int:
    mirror_log_cases()
    carrier_primary_cases()
    sent_ledger_cases()
    journal_off_cases()
    ok_reply = {"ok": True, "carried": 3, "queued": 3, "posted": 0}

    f = Fake(ok_reply)
    r, db = send(200, f.run)
    check("both carriers get the message; the carrier is asked the message's own id and text",
          r.code == 0 and len(f.requests) == 1 and f.requests[0]["op"] == "send"
          and f.requests[0]["message_id"] == P.VALID_ID and f.requests[0]["text"] == P.VALID, f"{r.code} {r.err} {f.requests}")
    check("the row is accepted once, with the RELAY's provenance and sequence: the first accepter's",
          db == [("outbound", "accepted", "claude-bridge", 42)], str(db))
    check("the exit status and the one stdout line are the relay's, as before",
          r.out.startswith("sent seq 42 INFO ") and r.out.count("\n") == 1)
    f.close()

    f = Fake(ok_reply)
    r, db = send(500, f.run)
    check("a relay that fails while the carrier queues the message: the row is accepted by InterWeave",
          db == [("outbound", "accepted", "interweave", None)], str(db))
    check("  and the exit status is still the relay's refusal, never 0", r.code == 3, f"{r.code} {r.err}")
    f.close()

    f = Fake({"ok": True, "carried": 0, "queued": 0, "posted": 0})
    r, db = send(200, f.run)
    check("a message the roster carries nowhere is the relay's alone: the row is the relay's",
          r.code == 0 and db == [("outbound", "accepted", "claude-bridge", 42)])
    f.close()

    f = Fake({"ok": False, "error": "no roster"})
    r, db = send(200, f.run)
    check("a carrier that refuses is said on stderr and changes neither the status nor the row",
          r.code == 0 and "InterWeave carrier refused (no roster)" in r.err and db == [("outbound", "accepted", "claude-bridge", 42)])
    f.close()
    f2 = Fake({"ok": False, "error": "no roster"})
    r, db = send(500, f2.run)
    check("  and with the relay down too, nothing marks the row accepted",
          r.code == 3 and db == [("outbound", "pending", None, None)], f"{r.code} {db}")
    f2.close()

    r, db = send(200, P.scratch("run-"))
    check("with no carrier nothing is asked and nothing is said",
          r.code == 0 and "InterWeave" not in r.err and db == [("outbound", "accepted", "claude-bridge", 42)])

    f = Fake(ok_reply)
    r, db = send(200, f.run, GZCOORD_JOURNAL="off")
    check("with the journal off the route is the relay alone: the carrier is not asked (rule 8)",
          r.code == 0 and f.requests == [])
    f.close()

    for d in P.SCRATCH:      # the protocol suite's scratch is removed by ITS main, which this does not run
        shutil.rmtree(d, ignore_errors=True)
    print(f"\ntest_gzcoord_carrier_send: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
