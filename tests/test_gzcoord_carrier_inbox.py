#!/usr/bin/env python3
"""bin/gzcoord-inbox with the shown ledger and the InterWeave carrier beside the
relay (ADR-064 rules 9 and 11; CARRIER-CONTRACT.md §6), through the real command
in the protocol suite's minimal environment, a stub relay and a fake carrier on
its adapter socket. What is held end to end: a message the relay delivers and the
carrier also lists is shown once; one only the carrier has is shown, from the
roster's address; with no carrier at all the relay's copy is shown and the ledger
stops a second showing of the same record; a mismatch copy after the relay's is
shown again, flagged, once; the relay is acknowledged only after the ledger's
pending line; the arrival log has a line per relay copy addressed here, journal on
or off; a showing that died after its pending line is shown again, flagged "may
repeat". Plain script: prints ok/FAIL, exit 1 on any failure."""
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
import test_gzcoord_protocol as P  # noqa: E402 — its relay stub, scratch and command environment

fails = 0
ME = P.MY_ADDRESS


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def msg(n: int, frm: str = "x/y") -> str:
    return (f"[GZCOORD/1] INFO\nFROM: {frm}\nROLE: backend-dev\nPROJECT: fixture\nTO: {ME}\n"
            f"MESSAGE-ID: 01a09fc1-0000-7000-8000-00000000010{n}\nSUBJECT: subject-{n}\n\nNOTES:\nn\n")


def mid(n: int) -> str:
    return f"01a09fc1-0000-7000-8000-00000000010{n}"


def relay_rec(n: int, frm: str = "x/y") -> dict:
    return {"seq": n, "id": f"r{n}", "ts": "T", "sender": "x/y", "content": msg(n, frm)}


class World:
    def __init__(self, pages: list[list[dict]], carrier_records: list[dict] | None = None, journal: bool = True) -> None:
        self.acks: list[str] = []
        self.calls = 0
        self.pages = pages
        self.env = None
        self.ledger_at_ack: list[int] = []

        def answer(_h, method, path, body):
            if path.startswith("/api/ack"):
                self.acks.append(json.loads(body)["message_id"])
                self.ledger_at_ack.append(len(self.ledger_lines()))
                return 200, "{}"
            if path.startswith("/api/wait"):
                self.calls += 1
                page = self.pages[self.calls - 1] if self.calls <= len(self.pages) else []
                return 200, json.dumps({"messages": page})
            return 200, "{}"
        self.stub = P.Stub(answer)
        extra = {} if journal else {"GZCOORD_JOURNAL": "off"}
        self.env = P.cmd_env(CLAUDE_BRIDGE_URL=self.stub.url, CLAUDE_BRIDGE_AUTH_TOKEN="tok", GZCOORD_CHANNEL="fixture:chan",
                             AGENT_FABRIC_SECRET_STORE=P.id_store(), **extra)
        self.state = self.env["AGENT_FABRIC_STATE_DIR"]
        self.carrier = None
        if carrier_records is not None:
            self.carrier = server.Server(server.socket_path(self.env["XDG_RUNTIME_DIR"]),
                                         lambda req: {"ok": True, "records": carrier_records} if req["op"] == "unseen"
                                         else {"ok": False, "error": "unexpected"})

    def agent_dir(self) -> str:
        found = [os.path.join(dp) for dp, _, fs in os.walk(self.state) if "gzcoord-shown.jsonl" in fs or "gzcoord-arrivals.jsonl" in fs]
        return found[0] if found else ""

    def read(self, name: str) -> list[dict]:
        d = self.agent_dir()
        try:
            return [json.loads(x) for x in open(os.path.join(d, name)) if x.strip()]
        except (FileNotFoundError, OSError):
            return []

    def ledger_lines(self) -> list[dict]:
        return self.read("gzcoord-shown.jsonl") if self.agent_dir() else self._scan()

    def _scan(self) -> list[dict]:
        out = []
        for dp, _, fs in os.walk(self.state):
            if "gzcoord-shown.jsonl" in fs:
                out += [json.loads(x) for x in open(os.path.join(dp, "gzcoord-shown.jsonl")) if x.strip()]
        return out

    def drain(self) -> subprocess.CompletedProcess:
        self.calls = 0
        return subprocess.run([P.INBOX_CMD], env=self.env, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)

    def close(self) -> None:
        if self.carrier:
            self.carrier.close()
        self.stub.close()


def urec(n: int, verdict: str = "ok", frm: str = "x/y") -> dict:
    return {"content": msg(n, frm), "ts": "2026-10-24T12:00:00Z", "seq": None, "message_id": mid(n), "verdict": verdict,
            "sender": "x/y"}


def main() -> int:
    # relay copy + carrier copy of one message: shown once
    w = World([[relay_rec(1)]], carrier_records=[urec(1)])
    r = w.drain()
    check("a message the relay delivers and the carrier also lists is shown once, as the relay's",
          r.returncode == 0 and r.stdout.count("subject-1") == 1 and "relay seq 1" in r.stdout, r.stdout + r.stderr)
    check("the relay was acknowledged after the ledger's pending line", w.acks == ["r1"] and w.ledger_at_ack[0] >= 1
          and w.ledger_lines()[0].get("pending") is True, str(w.ledger_at_ack))
    check("the ledger holds the pending line and the final line", [bool(x.get("pending")) for x in w.ledger_lines()] == [True, False])
    check("the arrival log has the relay copy, unauthenticated",
          [(x["carrier"], x["verdict"]) for x in w.read("gzcoord-arrivals.jsonl")] == [("relay", "unauthenticated")])
    w.pages = [[]]
    r2 = w.drain()
    check("the next drain shows nothing more of it, the carrier still listing it", "subject-1" not in r2.stdout, r2.stdout)
    w.close()

    # only the carrier has it
    w = World([[]], carrier_records=[urec(2)])
    r = w.drain()
    check("a message only the carrier has is shown, titled from the roster's address, with no relay acknowledgement",
          "subject-2" in r.stdout and "x/y" in r.stdout and "relay seq" not in r.stdout and w.acks == [], r.stdout + r.stderr)
    w.close()

    # no carrier at all
    w = World([[relay_rec(3)]])
    r = w.drain()
    check("with no carrier the relay's copy is shown", "subject-3" in r.stdout and r.returncode == 0, r.stdout + r.stderr)
    w.pages = [[relay_rec(3)]]
    r = w.drain()
    check("... and the same record delivered again (an acknowledgement that failed) is not shown twice: the ledger knows it",
          "subject-3" not in r.stdout and w.acks[-1] == "r3", r.stdout)
    w.close()

    # journal off: the arrival log is still kept, the carrier is not asked
    w = World([[relay_rec(4)]], carrier_records=[urec(5)], journal=False)
    r = w.drain()
    check("with the journal off the carrier is not asked (its arrival is not shown) and the relay's copy is",
          "subject-4" in r.stdout and "subject-5" not in r.stdout, r.stdout + r.stderr)
    check("... and the arrival log still has the relay copy", len(w.read("gzcoord-arrivals.jsonl")) == 1)
    w.close()

    # rule 9: the relay's copy shown, the carrier's copy reveals a mismatch
    w = World([[relay_rec(6, frm="x/forged")]], carrier_records=[urec(6, "mismatch", frm="x/forged")])
    r = w.drain()
    check("the relay's copy and, on the same page, the carrier's copy that reveals the FROM mismatch: shown again, flagged",
          r.stdout.count("subject-6") == 2 and "FROM mismatch" in r.stdout and "relay copy of" in r.stdout, r.stdout)
    w.pages = [[]]
    r = w.drain()
    check("... and that second showing happens once", "subject-6" not in r.stdout, r.stdout)
    w.close()

    # an interrupted showing
    w = World([[]], carrier_records=[])
    os.makedirs(os.path.join(w.state, "agents"), exist_ok=True)
    w.drain()
    agent_dir = w.agent_dir() or None
    if agent_dir is None:
        # make the agent state directory the inbox uses, by asking it for it
        import episodic
        saved = os.environ.get("AGENT_FABRIC_STATE_DIR")
        os.environ["AGENT_FABRIC_STATE_DIR"] = w.state
        try:
            agent_dir = episodic.state_dir()
        finally:
            if saved is None:
                os.environ.pop("AGENT_FABRIC_STATE_DIR")
            else:
                os.environ["AGENT_FABRIC_STATE_DIR"] = saved
    os.makedirs(agent_dir, exist_ok=True)
    with open(os.path.join(agent_dir, "gzcoord-shown.jsonl"), "w") as fh:
        fh.write(json.dumps({"mid": mid(7), "via": "relay", "t": "T", "pending": True}) + "\n")
    w.pages = [[relay_rec(7)]]
    r = w.drain()
    check("a message whose showing died after its pending line is shown again, flagged may-repeat",
          "subject-7" in r.stdout and "may repeat" in r.stdout, r.stdout + r.stderr)
    w.pages = [[relay_rec(7)]]
    r = w.drain()
    check("... and then it is settled", "subject-7" not in r.stdout, r.stdout)
    w.close()

    for d in P.SCRATCH:
        shutil.rmtree(d, ignore_errors=True)
    print(f"\ntest_gzcoord_carrier_inbox: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
