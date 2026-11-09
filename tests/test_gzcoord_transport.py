#!/usr/bin/env python3
"""tools/fabric/gzcoord/transport/ (agent-fabric ADR-067): each transport's four verbs against the wire it speaks, the mux's
sending and its logs, and the shown-ledger decision of dedup.py. The behaviour of the inbox and the sender through the real
commands is pinned by test_gzcoord_message_transport.py, test_gzcoord_protocol.py and test_gzcoord_carrier_*.py, which run
unchanged on the moved code; this file covers what they reach only through a process: a verb's request, a failure's class.
A stub relay in this process, a fake adapter, scratch directories. Plain script: ok/FAIL, exit 1."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import subprocess
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import test_gzcoord_carrier_inbox as C  # noqa: E402 — its message builders and the identity they are addressed to
import test_gzcoord_protocol as P  # noqa: E402 — the real commands' minimal environment and stub relay
from gzcoord import transport  # noqa: E402
from gzcoord.carrier import CARRIER_NAME  # noqa: E402
from gzcoord.carrier import ledger as L  # noqa: E402
from gzcoord.inbox_parts import relay as R  # noqa: E402
from gzcoord.inbox_parts.tokens import TokenRefused  # noqa: E402
from gzcoord.transport import dedup, relay as relay_transport  # noqa: E402

fails = 0
ME = {"address": "h/beta", "slug": "dev"}
NOW = "2026-10-24T12:00:00Z"


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def text(mid: str, to: str = "h/beta") -> str:
    return f"[GZCOORD/1] INFO\nFROM: h/alpha\nROLE: r\nTO: {to}\nMESSAGE-ID: {mid}\nSUBJECT: s\n\nCONTEXT:\nbody of {mid}\n"


class Stub:
    """A relay: answers by (method, path) from `answers`, 401 for any token not in `accepts`; keeps every request."""

    def __init__(self, answers: dict, accepts: tuple[str, ...] = ("tok",)) -> None:
        self.seen: list[dict] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def _do(self) -> None:
                n = int(self.headers.get("content-length") or 0)
                body = self.rfile.read(n).decode() if n else ""
                outer.seen.append({"method": self.command, "path": self.path, "auth": self.headers.get("authorization"),
                                   "body": json.loads(body) if body else None})
                token = (self.headers.get("authorization") or "").removeprefix("Bearer ")
                status, doc = (401, {}) if token not in accepts and self.path != "/status" else answers.get(
                    (self.command, self.path.split("?")[0]), (404, {}))
                raw = json.dumps(doc).encode()
                self.send_response(status)
                self.send_header("content-length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            do_GET = do_POST = _do

            def log_message(self, *a: object) -> None:
                pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class FakeAdapter:
    def __init__(self, post: str = "accepted", unseen: list[dict] | None = None, present: bool = True) -> None:
        self._post, self._unseen, self._present, self.posted = post, unseen or [], present, []

    def post(self, mid: str, text: str) -> str:
        self.posted.append(mid)
        return self._post

    def unseen(self) -> list[dict]:
        return [dict(r) for r in self._unseen]

    def present(self) -> bool:
        return self._present


def main() -> int:
    scratch = tempfile.mkdtemp(prefix="transport-")
    try:
        # ── the relay as a Primary ───────────────────────────────────────────────────────────────────────────────
        stub = Stub({("POST", "/api/send"): (200, {"seq": 42, "deduplicated": True}),
                     ("GET", "/api/wait"): (200, {"messages": [{"id": "r1", "seq": 1, "content": text("m1")}], "cursor": 9}),
                     ("POST", "/api/ack"): (200, {}),
                     ("GET", "/api/messages"): (200, {"messages": []}), ("GET", "/status"): (200, {})})
        tp = transport.RelayTransport(stub.url, "chan", "h/beta", "tok")
        sent = tp.send("m1", "TEXT")
        req = stub.seen[-1]
        check("send posts {channel, sender, content} to /api/send with the bearer token and answers the relay's seq",
              req["method"] == "POST" and req["path"] == "/api/send" and req["auth"] == "Bearer tok"
              and req["body"] == {"channel": "chan", "sender": "h/beta", "content": "TEXT"}
              and (sent.name, sent.state, sent.seq, sent.deduplicated) == ("relay", "accepted", 42, True), f"{req}\n{sent}")
        got = tp.receive(3, threading.Event())
        req = stub.seen[-1]
        asked = urllib.parse.parse_qs(urllib.parse.urlsplit(req["path"]).query)
        check("receive asks /api/wait for this consumer, 50 at most, and answers the page's records",
              req["path"].startswith("/api/wait?")
              and asked == {"channel": ["chan"], "consumer_id": ["h/beta"], "timeout_seconds": ["3"], "limit": ["50"]}
              and [r["id"] for r in got] == ["r1"], f"{req}\n{got}")
        tp.ack("r1")
        check("ack posts the record id as message_id for this consumer",
              stub.seen[-1]["body"] == {"consumer_id": "h/beta", "channel": "chan", "message_id": "r1"}, f"{stub.seen[-1]}")
        tp.newest(500)
        tp.newest(7, timeout=5)
        check("newest asks /api/messages for the newest records whole, no consumer",
              stub.seen[-2]["path"] == "/api/messages?channel=chan&limit=500&full=1"
              and stub.seen[-1]["path"] == "/api/messages?channel=chan&limit=7&full=1", f"{stub.seen[-2:]}")
        check("health is the relay's /status probe: a stub that answers it is up, a port nobody listens on is not",
              transport.RelayTransport(stub.url, "c", "a", "t").health().ok
              and not transport.RelayTransport("http://127.0.0.1:1", "c", "a", "t").health().ok)
        stub.close()
        # a page that is not a dict, or has no list of messages, is nothing waiting — never an error
        for doc in ([], {"messages": None}, None):
            s2 = Stub({("GET", "/api/wait"): (200, doc)})
            check(f"receive of the relay's answer {doc!r} is an empty list",
                  transport.RelayTransport(s2.url, "c", "a", "tok").receive(0, threading.Event()) == [], "")
            s2.close()

        # ── a refused token: taken fresh once, and only a 401/403 of the relay ──────────────────────────────────
        stub = Stub({("POST", "/api/send"): (200, {"seq": 1})}, accepts=("new",))
        real = relay_transport.synced_token
        try:
            relay_transport.synced_token = lambda: "new"
            tp = transport.RelayTransport(stub.url, "chan", "h/beta", "old")
            sent = tp.send("m", "T")
            check("a 401 with a different synced token: the post is made again with it, once, and the new token is kept",
                  sent.seq == 1 and [x["auth"] for x in stub.seen] == ["Bearer old", "Bearer new"]
                  and tp.refresh(R.RelayError("x", 401)) is False, f"{stub.seen}")
            relay_transport.synced_token = lambda: "old"
            tp = transport.RelayTransport(stub.url, "chan", "h/beta", "old")
            try:
                tp.send("m", "T")
                raised = None
            except R.RelayError as e:
                raised = e
            check("a 401 whose synced token is the one just refused: the 401 stands, no second post",
                  raised is not None and raised.status == 401 and len(stub.seen) == 3, f"{raised} {stub.seen}")
            relay_transport.synced_token = lambda: (_ for _ in ()).throw(TokenRefused("line break"))
            try:
                tp.send("m", "T")
                raised = None
            except TokenRefused as e:
                raised = e
            check("a synced token with a line break is TokenRefused, not a retry", raised is not None, "")
            calls = []
            relay_transport.synced_token = lambda: calls.append(1) or "new"
            check("refresh of a 500, of a 404 and of an error that is not the relay's reads no token and is False",
                  not any(tp.refresh(e) for e in (R.RelayError("x", 500), R.RelayError("x", 404), OSError("x"), R.RelayError("x")))
                  and calls == [], f"{calls}")
        finally:
            relay_transport.synced_token = real
            stub.close()

        # ── what each failure proves ─────────────────────────────────────────────────────────────────────────────
        tp = transport.RelayTransport("http://x", "c", "a", "t")
        check("never_delivered: a 4xx, a connection that never reached the relay and a refused token are; a 5xx, a timeout "
              "or a reset (reached unknown) and an error with no class are not",
              [tp.never_delivered(e) for e in (R.RelayError("x", 400), R.RelayError("x", 499), R.RelayError("x", reached=False),
                                               TokenRefused("x"), R.RelayError("x", 500), R.RelayError("x", 503),
                                               R.RelayError("x", reached=None), R.RelayError("x", 399), OSError("x"))]
              == [True, True, True, True, False, False, False, False, False])
        check("explain: a 401 or 403 is exit 4, a refused token is exit 4, anything else is unreachable at exit 0",
              [tp.explain(e)["code"] for e in (R.RelayError("x", 401), R.RelayError("x", 403), TokenRefused("x"),
                                               R.RelayError("x", 500), R.RelayError("x", reached=False))] == [4, 4, 4, 0, 0])

        # ── the carrier as a mirror ──────────────────────────────────────────────────────────────────────────────
        for state in ("accepted", "not-carried", "absent", "failed"):
            fake = FakeAdapter(post=state)
            c = transport.CarrierTransport(fake)
            check(f"carrier send answers the adapter's {state!r} under the carrier's own name",
                  c.send("m", "T") == transport.Sent(CARRIER_NAME, state) and fake.posted == ["m"])
        fake = FakeAdapter(unseen=[{"message_id": "u1"}], present=False)
        c = transport.CarrierTransport(fake)
        check("carrier receive is what the adapter lists unseen, ack tells it nothing, health is whether it is running",
              c.receive(5, threading.Event()) == [{"message_id": "u1"}] and c.ack("x") is None
              and c.health() == transport.Health(CARRIER_NAME, False))

        # ── the mux ──────────────────────────────────────────────────────────────────────────────────────────────
        state_dir = os.path.join(scratch, "state")
        os.makedirs(state_dir)
        stub = Stub({("POST", "/api/ack"): (200, {}), ("GET", "/api/wait"): (200, {"messages": [
            {"id": "r1", "seq": 1, "content": text("mine")}, {"id": "r2", "seq": 2, "content": text("other", to="h/gamma")},
            {"id": "r3", "seq": 3, "content": "not gzcoord"}]})})
        cfg = {"relay_url": stub.url, "channel": "chan"}
        mux = transport.open_transport(cfg, token="tok", me=ME, state_dir=state_dir, iso_now=lambda: NOW)
        check("the factory makes the relay primary and the carrier a mirror; with the journal off there is no mirror and no iw",
              mux.primary.name == "relay" and [m.name for m in mux.mirrors] == [CARRIER_NAME] and mux.iw is mux
              and transport.open_transport(cfg, token="tok", me=ME, journal_off=True).iw is None)
        page = mux.fetch_page(1, threading.Event())
        mux.ack("r1")
        mux.ack("r2")
        acks = [json.loads(x) for x in open(os.path.join(state_dir, "gzcoord-acks.jsonl"))]
        check("fetch_page is the primary's records as a page; the acknowledgement log has a line for the record addressed here "
              "and none for another's or one that is not GZCOORD/1",
              [r["id"] for r in page["messages"]] == ["r1", "r2", "r3"]
              and [(a["mid"], a["ok"]) for a in acks] == [("mine", True)], f"{page}\n{acks}")
        stub.close()
        down = transport.open_transport({"relay_url": "http://127.0.0.1:1", "channel": "c"}, token="tok", me=ME,
                                        state_dir=state_dir, iso_now=lambda: NOW)
        down._of_record["rX"] = "mid-x"
        try:
            down.ack("rX")
            raised = False
        except R.RelayError:
            raised = True
        acks = [json.loads(x) for x in open(os.path.join(state_dir, "gzcoord-acks.jsonl"))]
        check("an acknowledgement the relay did not take is raised and logged as failed",
              raised and (acks[-1]["mid"], acks[-1]["ok"]) == ("mid-x", False), f"{acks}")
        good, bad = transport.CarrierTransport(FakeAdapter()), transport.CarrierTransport(FakeAdapter(post="failed"))
        m2 = transport.TransportMux(mux.primary, [bad, good], me=ME)
        check("send_mirrors asks every mirror, in order, and answers each one's state",
              [s.state for s in m2.send_mirrors("m", "T")] == ["failed", "accepted"])
        m3 = transport.TransportMux(mux.primary, [transport.CarrierTransport(FakeAdapter(unseen=[{"message_id": "a"}])),
                                                  transport.CarrierTransport(FakeAdapter(unseen=[{"message_id": "b"}]))], me=ME)
        check("unseen is every mirror's, flattened", [r["message_id"] for r in m3.unseen()] == ["a", "b"])

        # ── through the command: the record the primary keeps is read 500 whole, by --history, --replay and a delivery ──
        seen: list[str] = []

        def answer(_h: object, method: str, path: str, body: str) -> tuple[int, str]:
            seen.append(f"{method} {path}")
            if path.startswith("/api/wait"):
                return 200, json.dumps({"messages": [C.relay_rec(1)]})
            if path.startswith("/api/messages"):
                return 200, json.dumps({"messages": [C.relay_rec(1)]})
            return 200, "{}"
        cmd_stub = P.Stub(answer)
        env = P.cmd_env(CLAUDE_BRIDGE_URL=cmd_stub.url, CLAUDE_BRIDGE_AUTH_TOKEN="tok", GZCOORD_CHANNEL="fixture:chan",
                        AGENT_FABRIC_SECRET_STORE=P.id_store())
        try:
            for args in (["--history"], ["--replay", "1"], []):
                del seen[:]
                r = subprocess.run([P.INBOX_CMD, *args], env=env, capture_output=True, text=True, timeout=120,
                                   stdin=subprocess.DEVNULL)
                reads = [urllib.parse.parse_qs(x.split("?", 1)[1]) for x in seen if x.startswith("GET /api/messages?")]
                check(f"gzcoord-inbox {' '.join(args) or '(a delivery)'} reads the channel's newest 500 records whole, once",
                      r.returncode == 0 and reads == [{"channel": ["fixture:chan"], "limit": ["500"], "full": ["1"]}],
                      f"{r.returncode} {r.stdout}{r.stderr}\n{seen}")
        finally:
            cmd_stub.close()

        # ── through the sender: the journal row says which transport accepted it ─────────────────────────────────────
        hosts = P.PresenceRelay({})   # only its hosts registry: --force skips the presence ask
        for label, relay, who in (("the relay down", P.Relay(status=503), CARRIER_NAME), ("the relay up", P.Relay(), "claude-bridge")):
            try:
                r, state, store, seen = P.carrier_send(relay.url, P.addressed("TO: h/alpha"), extra=["--force"], **hosts.env)
                code = ("import sqlite3,json,sys\nsys.path.insert(0, sys.argv[1]); import episodic\n"
                        "c = sqlite3.connect(episodic.db_path())\n"
                        "print(json.dumps(c.execute('SELECT state, carrier FROM episodes').fetchall()))")
                q = subprocess.run([sys.executable, "-c", code, P.TOOLS], capture_output=True, text=True, timeout=60,
                                   env={**os.environ, "AGENT_FABRIC_STATE_DIR": state, "AGENT_FABRIC_SECRET_STORE": store})
                rows = json.loads(q.stdout) if q.returncode == 0 else q.stderr
                check(f"send, {label} and a carrier that takes it: the carrier is asked once and the row names {who} (the first to accept)",
                      len(seen) == 1 and isinstance(rows, list) and len(rows) == 1 and rows[0][0] == "accepted"
                      and rows[0][1] == who, f"{r.code} {r.err}\n{rows}")
            finally:
                relay.close()

        # ── through the sender: with the journal off no mirror is asked (ADR-064 rule 8) ────────────────────────────
        relay = P.Relay(status=503)
        try:
            r, state, store, seen = P.carrier_send(relay.url, P.addressed("TO: h/alpha"), extra=["--force"],
                                                   GZCOORD_JOURNAL="off", **hosts.env)
            check("send, journal off, relay down and a carrier running: the carrier is not asked", seen == [] and r.code == 3,
                  f"{r.code} {r.err}\n{seen}")
        finally:
            relay.close()

        # ── through the sender: a post the relay deduplicated is said, a fresh one is not ────────────────────────────
        dup = P.Stub(lambda _h, _m, _p, _b: (200, json.dumps({"seq": 42, "id": "relay-id", "deduplicated": True})))
        fresh = P.Relay()
        try:
            said_dup, said_fresh = P.send_with(dup.url, P.VALID), P.send_with(fresh.url, P.VALID)
            check("send: the line for a post the relay deduplicated differs from a fresh post's by the relay's word for it",
                  said_dup.code == 0 and said_fresh.code == 0 and said_dup.out.startswith(said_fresh.out.rstrip("\n"))
                  and len(said_dup.out) > len(said_fresh.out), f"{said_dup.out!r}\n{said_fresh.out!r}")
        finally:
            dup.close()
            fresh.close()

        # ── the shown ledger's decision ──────────────────────────────────────────────────────────────────────────
        lg = L.Ledger(os.path.join(scratch, "shown.jsonl"), iso_now=lambda: NOW)
        rec = {"id": "r1", "seq": 1, "content": text("D-1")}
        mirror = {"content": text("D-1"), "ts": NOW, "message_id": "D-1", "verdict": "ok", "sender": "h/alpha"}
        lock = lg.exclusive()
        c1 = {"rec": rec, "msg": {"metadata": {"MESSAGE-ID": "D-1"}}, "isMine": True}
        classified = [c1]
        dedup.admit(lock, classified, [c1], [mirror])
        lock.finish()
        check("a primary record is shown and a mirror's copy of the same text is not added",
              "quiet" not in c1 and len(classified) == 1, f"{classified}")
        lock = lg.exclusive()
        c2 = {"rec": dict(rec), "msg": {"metadata": {"MESSAGE-ID": "D-1"}}, "isMine": True}
        classified = [c2]
        dedup.admit(lock, classified, [c2], [mirror])
        lock.release()
        check("... shown again by either, it is quiet (journaled and acknowledged, not shown twice) and not added again",
              c2.get("quiet") is True and len(classified) == 1, f"{classified}")
        lock = lg.exclusive()
        classified = []
        dedup.admit(lock, classified, [], [{**mirror, "message_id": "D-2", "content": text("D-2")}])
        lock.finish()
        check("a mirror's record not shown before becomes a message of its own, tagged with the mirror's name",
              len(classified) == 1 and classified[0]["iw"]["mid"] == "D-2" and classified[0]["rec"]["seq"] == CARRIER_NAME,
              f"{classified}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    print(f"\ntest_gzcoord_transport: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
