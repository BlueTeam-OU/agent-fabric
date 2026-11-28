#!/usr/bin/env python3
"""bin/gzcoord-inbox with the shown ledger over the InterWeave carrier (ADR-064 rules 9 and 11; CARRIER-CONTRACT.md §6), through
the real command in the protocol suite's minimal environment and a carrier stand-in on its adapter socket (P.Carrier). What is
held end to end: a record the carrier lists is shown once, from the roster's address, and the next drain shows nothing more of
it; a record whose FROM the carrier's verdict contradicts is shown flagged; a showing that died after its pending line is
shown again, flagged "may repeat"; receiving with the journal off is refused; the watch log has a start and an end per watch,
and the watch retries a carrier that does not answer. This module also
holds the World the other inbox suites build on. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import test_gzcoord_protocol as P  # noqa: E402 — its carrier stand-in, scratch and command environment


RETRY_S = "1"   # GZCOORD_RETRY_S: the watch's seconds between tries while the carrier does not answer, shortened so a case waits for the retry's event


class Follow:
    """A `gzcoord-inbox --follow` run, its streams drained as they come so a case can wait for what it expects
    (`wait_for`) instead of out a fixed time; `stop` ends it and returns everything it said."""

    def __init__(self, env: dict) -> None:
        self.proc = subprocess.Popen([P.INBOX_CMD, "--follow"], env={**env, "GZCOORD_RETRY_S": RETRY_S}, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL)
        self.out: list[str] = []
        self.err: list[str] = []
        self.readers = [threading.Thread(target=self._drain, args=(f, into), daemon=True)
                        for f, into in ((self.proc.stdout, self.out), (self.proc.stderr, self.err))]
        for t in self.readers:
            t.start()

    @staticmethod
    def _drain(stream, into: list) -> None:
        for line in stream:
            into.append(line)

    def wait_for(self, ready, timeout: float = 20) -> bool:
        """True once ready(out, err) holds; False at the timeout, which a case's own check then reports."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if ready("".join(self.out), "".join(self.err)):
                return True
            time.sleep(0.05)
        return False

    def stop(self) -> tuple[str, str]:
        self.proc.terminate()
        self.proc.wait(timeout=30)
        for t in self.readers:
            t.join(timeout=5)
        return "".join(self.out), "".join(self.err)


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


class World:
    """A scratch account whose inbox commands find a carrier stand-in (`carrier`, a P.Carrier) listing `carrier_records`;
    `records` is what it lists now, and a case changes it between runs."""

    def __init__(self, carrier_records: list[dict] | None = None, journal: bool = True, hold_s: float | None = 0.3) -> None:
        self.carrier = P.Carrier(records=carrier_records, hold_s=hold_s)
        self.env = P.inbox_env(self.carrier, **({} if journal else {"GZCOORD_JOURNAL": "off"}))
        self.state = self.env["AGENT_FABRIC_STATE_DIR"]

    @property
    def records(self) -> list[dict]:
        return self.carrier.records

    def agent_dir(self) -> str:
        found = [os.path.join(dp) for dp, _, fs in os.walk(self.state) if {"gzcoord-shown.jsonl", "gzcoord-arrivals.jsonl", "gzcoord-watch.jsonl"} & set(fs)]
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

    def watch(self, deadline: int = 8) -> subprocess.CompletedProcess:
        """The real watch (--until-delivery) with a short bound on how long a carrier that never answers is called down."""
        env = {**self.env, "GZCOORD_UNTIL_DELIVERY_DOWN_S": "3"}
        return subprocess.run([P.INBOX_CMD, "--until-delivery", "--deadline", str(deadline)], env=env, capture_output=True,
                              text=True, timeout=120, stdin=subprocess.DEVNULL)

    def drain(self) -> subprocess.CompletedProcess:
        return subprocess.run([P.INBOX_CMD], env=self.env, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)

    def close(self) -> None:
        self.carrier.close()


def urec(n: int, verdict: str = "ok", frm: str = "x/y") -> dict:
    return {"content": msg(n, frm), "ts": "2026-10-24T12:00:00Z", "seq": None, "message_id": mid(n), "verdict": verdict,
            "sender": "x/y"}


def main() -> int:
    # a record the carrier lists is shown once
    w = World([urec(1)])
    r = w.drain()
    check("a record the carrier lists is shown once, titled from the roster's address",
          r.returncode == 0 and r.stdout.count("subject-1") == 1 and "x/y" in r.stdout, r.stdout + r.stderr)
    check("the ledger holds the pending line and the final line, under the carrier's name",
          [(bool(x.get("pending")), x["via"]) for x in w.ledger_lines()] == [(True, "interweave"), (False, "interweave")],
          str(w.ledger_lines()))
    r2 = w.drain()
    check("the next drain shows nothing more of it, the carrier still listing it", "subject-1" not in r2.stdout and r2.returncode == 0,
          r2.stdout + r2.stderr)
    w.close()

    # no carrier at all: said, not silent
    w = World([urec(2)])
    w.carrier.close()
    r = w.drain()
    check("with no carrier running the drain says so on stderr, exit 0, and shows nothing",
          r.returncode == 0 and "carrier is not running" in r.stderr and "subject-2" not in r.stdout, r.stdout + r.stderr)
    w.close()

    # journal off: receiving is refused, the carrier is not asked
    w = World([urec(5)], journal=False)
    r = w.drain()
    check("with the journal off the inbox refuses in one line, exit 7, and the carrier is not asked",
          r.returncode == 7 and "GZCOORD_JOURNAL=off" in r.stdout + r.stderr and w.carrier.ops() == [] and "subject-5" not in r.stdout,
          f"{r.returncode}\n{r.stdout}{r.stderr}\n{w.carrier.ops()}")
    w.close()

    # rule 9: the carrier's verdict contradicts the message's FROM
    w = World([urec(6, "mismatch", frm="x/forged")])
    r = w.drain()
    check("a record whose FROM the carrier's verdict contradicts is shown once, flagged, as from the roster's address",
          r.stdout.count("subject-6") == 1 and "FROM mismatch" in r.stdout, r.stdout + r.stderr)
    r = w.drain()
    check("... and it is not shown again", "subject-6" not in r.stdout, r.stdout)
    w.close()

    # an interrupted showing
    w = World([])
    w.drain()
    agent_dir = w.agent_dir()
    if not agent_dir:
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
        fh.write(json.dumps({"mid": mid(7), "via": "interweave", "t": "T", "pending": True}) + "\n")
    w.records.append(urec(7))
    r = w.drain()
    check("a message whose showing died after its pending line is shown again, flagged may-repeat",
          "subject-7" in r.stdout and "may repeat" in r.stdout, r.stdout + r.stderr)
    r = w.drain()
    check("... and then it is settled", "subject-7" not in r.stdout, r.stdout)
    w.close()

    # The watch: its log of starts and ends, and a record the carrier lists again.
    w = World([])
    r = w.watch(deadline=3)

    def lifecycle() -> list[tuple]:
        return [(x["event"], x.get("reason"), x.get("code")) for x in w.read("gzcoord-watch.jsonl")]
    check("a watch that ended at its deadline says quiet, exit 0, and logged its start and an end with reason quiet",
          r.returncode == 0 and lifecycle() == [("start", None, None), ("end", "quiet", 0)], f"{r.returncode}\n{lifecycle()}")
    w.records.append(urec(1))
    r = w.watch()
    check("a message that arrived meanwhile reaches the next watch, once, exit 0",
          r.returncode == 0 and r.stdout.count("subject-1") == 1, f"{r.returncode}\n{r.stdout}{r.stderr}")
    check("the restart is a second start, and its end says delivery",
          lifecycle()[2:] == [("start", None, None), ("end", "delivery", 0)], str(w.read("gzcoord-watch.jsonl")))
    r = w.watch(deadline=3)
    check("a restart of the watch does not show it again, the carrier still listing it: quiet",
          "subject-1" not in r.stdout and r.returncode == 0, f"{r.returncode}\n{r.stdout}{r.stderr}")
    check("the watch log keeps every start and end of the account; its lines are one pid per watch and a time each, no message text",
          [e for e in lifecycle() if e[0] == "end"] == [("end", "quiet", 0), ("end", "delivery", 0), ("end", "quiet", 0)]
          and len({x["pid"] for x in w.read("gzcoord-watch.jsonl")}) == 3
          and all(x["t"].endswith("Z") for x in w.read("gzcoord-watch.jsonl"))
          and "subject-1" not in json.dumps(w.read("gzcoord-watch.jsonl")), str(lifecycle()))
    w.close()

    # An unwritable watch log never ends or alters the watch; it is said once on stderr.
    w = World([])
    w.watch(deadline=2)
    log = os.path.join(w.agent_dir(), "gzcoord-watch.jsonl")      # before the removal: agent_dir() finds the account by its logs
    os.remove(log)
    os.mkdir(log)
    w.records.append(urec(8))
    r = w.watch()
    check("an unwritable watch log is said once on stderr and the watch still delivers, exit 0",
          r.returncode == 0 and "subject-8" in r.stdout and r.stderr.count("the watch log") == 1, f"{r.returncode}\n{r.stdout}{r.stderr}")
    w.close()

    # --follow: the carrier is not running (the watch is "down"), then it is and delivers: shown, and the watch says it is back.
    env = P.inbox_env()
    f = Follow(env)
    carrier = None
    try:
        waited = [f.wait_for(lambda out, err: "carrier is not answering" in out)]
        carrier = P.Carrier(records=[urec(5)], run=env["XDG_RUNTIME_DIR"])
        waited.append(f.wait_for(lambda out, err: "subject-5" in out))
        waited.append(f.wait_for(lambda out, err: "answers again" in out))
    finally:
        out, err = f.stop()
        if carrier is not None:
            carrier.close()
    check("--follow, the carrier not running, then running: the down line once, the record shown, the back line",
          all(waited) and out.count("subject-5") == 1 and out.count("carrier is not answering") == 1 and "answers again" in out,
          f"{waited}\n{out}{err}")

    for d in P.SCRATCH:
        shutil.rmtree(d, ignore_errors=True)
    print(f"\ntest_gzcoord_carrier_inbox: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
