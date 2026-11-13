#!/usr/bin/env python3
"""NOT part of the suite (the name is not test_*): the read-back of tools/fabric/gzcoord/backfill.py on this host, run by
one account against a PRIVATE relay in this process (the fleet's relay is never touched, never stopped).

What is real: this checkout's agentd.py `Ticker` and `backfill_tick` (the function the daemon's timer calls), backfill.py, the
journal's own verbs (episodic.py) writing the rows a `gzcoord-send` leaves behind when only the second carrier took a
message (state accepted, carrier interweave), and the relay's HTTP wire through RelayTransport. What is stood in for: the
relay (a stub with /status, /api/messages and /api/send, started and stopped here), the carrier's delivery (the rows are
written, not sent through the carrier to another account) and the daemon around the timer (no scratch agentd process).

Scratch state only: AGENT_FABRIC_STATE_DIR and the relay URL and channel are the environment of this process.

    python3 tests/live_backfill.py
"""
from __future__ import annotations

import datetime
import http.server
import json
import os
import socket
import sys
import shutil
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))

ME = ""   # this account's own address, set in main(): the journal is this account's, in a scratch state directory
CHANNEL = "backfill-readback:gzcoord"


def say(line: str) -> None:
    print(line, flush=True)


class Relay:
    """A relay the check owns: its record, and an up/down switch that closes and reopens the listening socket."""

    def __init__(self) -> None:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        self.port = s.getsockname()[1]
        s.close()
        self.record: list[dict] = []
        self.server: http.server.ThreadingHTTPServer | None = None

    def post(self, content: str) -> None:
        self.record.append({"id": f"r{len(self.record) + 1}", "seq": len(self.record) + 1, "sender": ME, "content": content,
                            "ts_full": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")})

    def start(self) -> None:
        relay = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def _send(self, obj, code=200):
                body = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path.startswith("/status"):
                    return self._send({"ok": True})
                if self.path.startswith("/api/messages"):
                    return self._send({"messages": relay.record[-500:]})
                self._send({}, 404)

            def do_POST(self):
                if self.path.startswith("/api/send"):
                    n = int(self.headers.get("Content-Length") or 0)
                    req = json.loads(self.rfile.read(n))
                    assert req["channel"] == CHANNEL and req["sender"] == ME, req
                    relay.post(req["content"])
                    return self._send({"seq": len(relay.record)})
                self._send({}, 404)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", self.port), H)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None


def text(mid: str) -> str:
    return f"[GZCOORD/1] INFO\nFROM: {ME}\nROLE: x\nTO: h/peer\nMESSAGE-ID: {mid}\nSUBJECT: s\n\nINFO:\nbody {mid}\n"


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="backfill-live-")
    relay = Relay()
    os.environ.update(AGENT_FABRIC_STATE_DIR=tmp, CLAUDE_BRIDGE_URL=f"http://127.0.0.1:{relay.port}", GZCOORD_CHANNEL=CHANNEL)
    import episodic
    from control import agentd

    global ME
    ME = episodic.own_address()
    state = episodic.state_dir()
    conn = episodic.connect(episodic.db_path(), episodic.own_agent_id())
    now = datetime.datetime.now(datetime.timezone.utc)

    def journal(mid: str, age_s: int) -> None:
        episodic.out_pending(conn, text(mid), "agent-fabric")
        conn.execute("UPDATE episodes SET happened_at=? WHERE message_id=?",
                     ((now - datetime.timedelta(seconds=age_s)).strftime("%Y-%m-%dT%H:%M:%SZ"), mid))
        episodic.out_final(conn, mid, "accepted", None, "interweave")

    # relay down: A and B reach the carrier only; C is older than the bound; B is then put on the record by a hand resend
    journal("A-carrier-only", 600)
    journal("B-hand-resent", 540)
    journal("C-over-age", 13 * 3600)
    relay.start()
    relay.post(text("B-hand-resent"))
    relay.stop()
    say("relay DOWN; journal: A (carrier only, 10 min old), B (carrier only; a hand resend put it on the record), "
        "C (13 h old)")

    out: list[str] = []
    real_stderr = agentd._stderr
    agentd._stderr = out.append
    ticker = agentd.Ticker("gzcoord backfill", lambda: agentd.backfill_tick(lambda: "scratch-token"), 1.0, log=out.append).start()
    try:
        time.sleep(2.5)
        say(f"relay down, 2 ticks: relay record has {len(relay.record)} message(s); log lines: {len(backfill_lines(state))}")
        for line in out:
            say("  agentd: " + line)
        t_up = time.monotonic()
        relay.start()
        say("relay UP")
        deadline = t_up + 15
        while time.monotonic() < deadline and not any(r["content"].startswith("[GZCOORD/1] INFO") and "A-carrier-only" in r["content"]
                                                       for r in relay.record):
            time.sleep(0.2)
        say(f"A on the relay {time.monotonic() - t_up:.1f} s after the relay returned")
        time.sleep(2.5)   # further ticks must post nothing more
    finally:
        ticker.stop()
        agentd._stderr = real_stderr
        relay.stop()

    ids = [json.loads(json.dumps(r))["content"].split("MESSAGE-ID: ")[1].split("\n")[0] for r in relay.record]
    say(f"relay record: {ids}")
    for line in backfill_lines(state):
        say("  log: " + line.strip())
    ok = (ids == ["B-hand-resent", "A-carrier-only"]
          and relay.record[1]["content"] == text("A-carrier-only")
          and sorted(json.loads(x)["outcome"] for x in backfill_lines(state)) == ["over-age", "posted", "present"])
    conn.close()
    shutil.rmtree(tmp)   # the scratch state is this run's alone
    say("PASS" if ok else "FAIL")
    return 0 if ok else 1


def backfill_lines(state: str) -> list[str]:
    try:
        with open(os.path.join(state, "gzcoord-backfill.jsonl")) as f:
            return f.readlines()
    except FileNotFoundError:
        return []


if __name__ == "__main__":
    sys.exit(main())
