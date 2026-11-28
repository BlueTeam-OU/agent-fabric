#!/usr/bin/env python3
"""bin/gzcoord-send over the InterWeave carrier, the only transport since W15 (ADR-064 rules 6-8, CARRIER-CONTRACT.md §6),
through the real command in the protocol suite's minimal environment: the carrier's adapter socket is a stand-in answering the
contract's ops (P.Carrier). What is held: the carrier is asked the message's own id and text and its accept is the only exit 0
and the journal row's `interweave`; every other outcome is exit 3 with a line, the pending row failed only when the carrier
provably recorded nothing; the sent ledger holds the id of an accepted send and refuses the id again for another body, journal
on or off; a send the carrier did not accept leaves a line in the mirror log, `as` primary; with the journal off the carrier is
still the route and the bypass is said. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from gzcoord.carrier import server  # noqa: E402
import test_gzcoord_protocol as P  # noqa: E402 — its carrier stand-in, scratch and command environment

fails = 0
OK_REPLY = {"ok": True, "carried": 3, "queued": 3, "posted": 0}


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def rows(state: str, store: str) -> list[tuple]:
    code = ("import sqlite3,json,sys\nsys.path.insert(0, sys.argv[1]); import episodic\n"
            "c = sqlite3.connect(episodic.db_path())\n"
            "print(json.dumps(c.execute('SELECT direction, state, carrier, carrier_seq FROM episodes').fetchall()))")
    r = subprocess.run([sys.executable, "-c", code, P.TOOLS], capture_output=True, text=True, timeout=60,
                       env={**os.environ, "AGENT_FABRIC_STATE_DIR": state, "AGENT_FABRIC_SECRET_STORE": store})
    if "no such table" in r.stderr:
        return []      # a send with the journal off made no journal
    assert r.returncode == 0, r.stderr
    return [tuple(x) for x in json.loads(r.stdout)]


def send_in(reply: dict | None, **env: str):
    """gzcoord-send of the fixture message with a carrier answering `reply` (None: no carrier running); the journal rows and the
    carrier stand-in, closed, with the requests it saw, come back beside."""
    carrier = P.Carrier(send=reply) if reply is not None else None
    base = P.scratch("send-journal-")
    state, store = os.path.join(base, "state"), P.id_store()
    try:
        r = P.send_with(carrier, P.VALID, AGENT_FABRIC_STATE_DIR=state, AGENT_FABRIC_SECRET_STORE=store, **env)
    finally:
        if carrier is not None:
            carrier.close()
    return r, rows(state, store), carrier


def registry_with(operator: str | None) -> str:
    """A scratch hosts registry whose operator on the sender's host is `operator` (None: another login), so a case never
    reads whether whoever runs the suite is an operator in the checkout's registry."""
    path = os.path.join(P.scratch("reg-"), "registry.json")
    with open(path, "w") as fh:
        json.dump({"hosts": {P.ME["host"]: {"operator": operator or "someone-else"}}, "placement": {}}, fh)
    return path


def carrier_primary_cases() -> None:
    """The four outcomes of Adapter.post as gzcoord-send reports them (cutover W8): accepted is the only exit 0; every other is
    exit 3 with a line, and the pending row is failed only when the carrier provably recorded nothing."""
    r, db, carrier = send_in(OK_REPLY)
    check("accepted: exit 0, one stdout line with the id and no seq, the row the carrier's, the carrier asked the message's own id and text once",
          r.code == 0 and r.out == f"sent INFO {P.VALID_ID}\n" and db == [("outbound", "accepted", "interweave", None)]
          and [(q["op"], q["message_id"], q["text"]) for q in carrier.requests] == [("send", P.VALID_ID, P.VALID)],
          f"{r.code} {r.out!r} {r.err} {db} {carrier.requests}")

    r, db, _ = send_in({"ok": True, "carried": 0, "queued": 0, "posted": 0})
    check("not-carried: exit 3, nothing on stdout, said as not sent, the pending row failed, under the carrier's name",
          r.code == 3 and r.out == "" and "not sent" in r.err and db == [("outbound", "failed", "interweave", None)], f"{r.code} {r.err} {db}")

    r, db, _ = send_in(None, AGENT_FABRIC_HOSTS_REGISTRY=registry_with(None))
    check("absent, a sender who is no operator: exit 3, the line says what an agent can do, the row failed",
          r.code == 3 and "not sent" in r.err and "OBSERVATION" in r.err and "fabric-ctl" not in r.err
          and db == [("outbound", "failed", "interweave", None)], f"{r.code} {r.err} {db}")
    r, db, _ = send_in(None, AGENT_FABRIC_HOSTS_REGISTRY=registry_with(P.ME["agent"]))
    check("absent, a host operator: the line names the command that says why",
          r.code == 3 and "not sent" in r.err and f"fabric-ctl {P.ME['agent']} interweave" in r.err and "OBSERVATION" not in r.err
          and db == [("outbound", "failed", "interweave", None)], f"{r.code} {r.err} {db}")

    r, db, _ = send_in({"ok": False, "error": "disk", "carried": 3, "queued": 0})
    check("failed with nothing recorded: exit 3, not sent, the row failed",
          r.code == 3 and "not sent" in r.err and db == [("outbound", "failed", "interweave", None)], f"{r.code} {r.err} {db}")

    r, db, _ = send_in({"ok": False, "error": "disk", "carried": 3, "queued": 1})
    check("failed with some recipients recorded: exit 3, outcome unknown, the row stays pending",
          r.code == 3 and "outcome unknown" in r.err and "same id" in r.err and "keeps retrying it until it is receipted" in r.err
          and db == [("outbound", "pending", None, None)], f"{r.code} {r.err} {db}")


def sent_ledger_cases() -> None:
    """The sent ledger holds the id of a send the carrier accepted, and refuses the id again for another body whatever else
    happened and with the journal off, where the journal's own check does not run (review F1)."""
    def ledger_ids(reply: dict | None, **env: str) -> tuple:
        carrier = P.Carrier(send=reply) if reply is not None else None
        base = P.scratch("send-ledger-")
        state, store = os.path.join(base, "state"), P.id_store()
        try:
            r = P.send_with(carrier, P.VALID, AGENT_FABRIC_STATE_DIR=state, AGENT_FABRIC_SECRET_STORE=store, **env)
        finally:
            if carrier is not None:
                carrier.close()
        try:
            with open(os.path.join(state, "agents", P.LOGIN, "gzcoord-sent.jsonl"), encoding="utf-8") as fh:
                ids = [json.loads(x)["id"] for x in fh if x.strip() and "id" in json.loads(x)]
        except FileNotFoundError:
            ids = []
        return r, ids

    r, ids = ledger_ids(OK_REPLY)
    check("the carrier taking it: exit 0 and the id is on the sent ledger", r.code == 0 and ids == [P.VALID_ID], f"{r.code} {r.err} {ids}")
    r, ids = ledger_ids({"ok": False, "error": "no roster"})
    check("the carrier refusing it: exit 3 and the id is NOT on the sent ledger", r.code == 3 and ids == [], f"{r.code} {r.err} {ids}")
    r, ids = ledger_ids(None)
    check("no carrier: exit 3 and the id is NOT on the sent ledger", r.code == 3 and ids == [], f"{r.code} {r.err} {ids}")
    carrier = P.Carrier(send=OK_REPLY)
    base = P.scratch("send-reuse-")
    state, store = os.path.join(base, "state"), P.id_store()
    try:
        kw = dict(AGENT_FABRIC_STATE_DIR=state, AGENT_FABRIC_SECRET_STORE=store, GZCOORD_JOURNAL="off")
        first = P.send_with(carrier, P.VALID, **kw)
        second = P.send_with(carrier, P.VALID.replace("hello", "hello, edited"), **kw)
        again = P.send_with(carrier, P.VALID, **kw)
    finally:
        carrier.close()
    check("journal off: the same id with another body is refused (exit 2); the same message again passes",
          first.code == 0 and second.code == 2 and "already went out" in second.err and again.code == 0,
          f"{first.code} {second.code} {second.err} {again.code}")


def journal_off_cases() -> None:
    """D7 (cutover plan, owner 2026-11-15): a GZCOORD_JOURNAL=off send goes through the carrier, says so, and leaves no journal row."""
    bypass = "GZCOORD_JOURNAL=off"
    r, db, carrier = send_in(OK_REPLY, GZCOORD_JOURNAL="off")
    check("D7: the carrier takes the send (exit 0, its id line), the bypass line is said, no journal row",
          r.code == 0 and r.out == f"sent INFO {P.VALID_ID}\n" and bypass in r.err and db == []
          and [q["op"] for q in carrier.requests] == ["send"], f"{r.code} {r.out!r} {r.err} {db} {carrier.requests}")
    r, db, _ = send_in(None, GZCOORD_JOURNAL="off", AGENT_FABRIC_HOSTS_REGISTRY=registry_with(None))
    check("D7: no carrier running is the carrier's failure (exit 3)",
          r.code == 3 and "not sent" in r.err and "OBSERVATION" in r.err and bypass in r.err, f"{r.code} {r.err}")


def mirror_log_cases() -> None:
    """ADR-064 rule 11, the sender's durable line: a send the carrier did not accept leaves {mid, t, outcome, reason, as} in
    gzcoord-mirror.jsonl beside gzcoord-sent.jsonl, one outcome each, `as` primary (the carrier is the transport of record); an
    accepted send leaves none (the positive control). The parity report reads it (test_gzcoord_carrier_parity.py); the mutation
    that drops the write fails each case here."""
    def logged(reply: dict | None, run: str | None = None, seed: bytes = b"", **env: str) -> tuple:
        carrier = P.Carrier(send=reply) if reply is not None else None
        base = P.scratch("send-mirrorlog-")
        state, store = os.path.join(base, "state"), P.id_store()
        agent = os.path.join(state, "agents", P.LOGIN)
        os.makedirs(agent)
        if seed:
            with open(os.path.join(agent, "gzcoord-mirror.jsonl"), "wb") as fh:
                fh.write(seed)
        if run is not None:
            env["XDG_RUNTIME_DIR"] = run
        try:
            r = P.send_with(carrier, P.VALID, AGENT_FABRIC_STATE_DIR=state, AGENT_FABRIC_SECRET_STORE=store, **env)
        finally:
            if carrier is not None:
                carrier.close()
        try:
            with open(os.path.join(agent, "gzcoord-mirror.jsonl"), encoding="utf-8", errors="replace") as fh:
                lines = [json.loads(x) for x in fh if x.strip().startswith('{')]
        except FileNotFoundError:
            lines = None
        return r, lines

    def one(name: str, r, lines, outcome: str, reason_has: str) -> None:
        line = (lines or [{}])[0]
        check(f"{name}: exit 3 and one line {{mid, t, outcome {outcome}, reason, as primary}}",
              r.code == 3 and lines is not None and len(lines) == 1 and set(line) == {"mid", "t", "outcome", "reason", "as"}
              and line["as"] == "primary"
              and line["mid"] == P.VALID_ID and line["outcome"] == outcome and reason_has in line["reason"]
              and len(line["t"]) == 20 and line["t"].endswith("Z"), f"{r.code} {r.err} {lines}")

    r, lines = logged(None)
    one("no carrier running (absent)", r, lines, "absent", "no InterWeave carrier")
    r, lines = logged({"ok": False, "error": "disk", "carried": 3, "queued": 0})
    one("the carrier recorded nothing (failed)", r, lines, "failed", "disk")
    r, lines = logged({"ok": False, "error": "disk", "carried": 3, "queued": 1})
    one("the carrier answered and recorded some recipients (failed, never no-answer)", r, lines, "failed", "disk, 1 recipient(s) recorded")
    r, lines = logged({"ok": True, "carried": 3, "queued": 1, "posted": 0})
    one("not every recipient recorded (failed)", r, lines, "failed", "not every recipient")
    r, lines = logged({"ok": True, "carried": 0, "queued": 0, "posted": 0})
    one("no roster member carries it (failed, never not-carried)", r, lines, "failed", "no roster member")
    r, lines = logged({"ok": False, "error": "no roster"})
    one("the carrier refuses (failed)", r, lines, "failed", "no roster")
    dead = P.scratch("run-")      # a socket path with nothing listening: the carrier is there and does not answer
    os.makedirs(os.path.dirname(server.socket_path(dead)))
    open(server.socket_path(dead), "w").close()
    r, lines = logged(None, run=dead)
    one("a carrier that does not answer (no-answer)", r, lines, "no-answer", "did not answer")
    r, lines = logged(OK_REPLY)
    check("  positive control: a carrier that accepts leaves no line", r.code == 0 and lines is None, f"{r.code} {r.err} {lines}")
    r, lines = logged({"ok": False, "error": "no roster"}, seed=b"\xff\xfe not utf-8\n" * 30000)
    check("  a log with bytes that are not UTF-8, over its bound: the send ends 3 with nothing on stdout, says nothing of the log, "
          "the new line is there and the log is trimmed",
          r.code == 3 and r.out == "" and "mirror refusal log" not in r.err
          and lines is not None and lines[-1]["mid"] == P.VALID_ID and len(lines) < 100, f"{r.code} {r.out!r} {r.err} {lines and len(lines)}")
    r, lines = logged(None, GZCOORD_JOURNAL="off")
    one("journal off (absent): the carrier is the route, so it is logged", r, lines, "absent", "no InterWeave carrier")


def main() -> int:
    mirror_log_cases()
    carrier_primary_cases()
    sent_ledger_cases()
    journal_off_cases()
    for d in P.SCRATCH:      # the protocol suite's scratch is removed by ITS main, which this does not run
        shutil.rmtree(d, ignore_errors=True)
    print(f"\ntest_gzcoord_carrier_send: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
