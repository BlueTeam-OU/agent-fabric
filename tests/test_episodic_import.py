#!/usr/bin/env python3
"""episodic.py gzcoord-import (tools/fabric/episodic_import.py) against a fake
relay in this process, in scratch state: each decision rule of ADR-041 rule
9 with its positive control, the ledger cross-check, idempotence over a
live-captured row and a second run, the meta marker, the report without
content or token, a consumer never acknowledged, a control channel and
another agent's journal refused."""
from __future__ import annotations

import datetime
import json
import os
import pwd
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(HERE, "tools", "fabric", "episodic.py")
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
TOKEN = "fixture-relay-token-not-a-secret"
LOGIN = pwd.getpwuid(os.getuid()).pw_name
ME = f"{socket.gethostname().split('.')[0]}/{LOGIN}"
OTHER = "develop-qzapp/someone-else"
# Born 2026-09-20T00:00:00Z: the UUIDv7's first 48 bits are its milliseconds.
BIRTH_MS = int(datetime.datetime(2026, 9, 20, tzinfo=datetime.UTC).timestamp() * 1000)
AGENT = f"{BIRTH_MS:012x}"[:8] + "-" + f"{BIRTH_MS:012x}"[8:] + "-7abc-8def-0123456789ab"
AGENT_B = "01a0f7ea-15b0-7ed9-a176-6eb006592db1"
STRIP = ("AGENT_FABRIC_", "GITHUB_", "CLAUDE", "GZCOORD_", "GIT_", "XDG_")


def msg(mid: str | None, body: str, *, frm: str = OTHER, to: str | None = None, role: str | None = None,
        broadcast: bool = False, mtype: str = "INFO") -> str:
    head = f"[GZCOORD/1] {mtype}\nFROM: {frm}\nROLE: x\n"
    head += f"TO: {to}\n" if to else ""
    head += f"TO-ROLE: {role}\n" if role else ""
    head += "BROADCAST: true\n" if broadcast else ""
    head += f"MESSAGE-ID: {mid}\n" if mid else ""
    return head + f"SUBJECT: s\n\nINFO:\n{body}\n"


# The channel, oldest first. Each body carries a word that must never
# reach the report (BODY-<n>).
DAY = "2026-09-{:02d} 10:00:00.123456"
RECORDS = [
    ("to-me", msg("to-me-1", "BODY-1", to=ME), 22),
    ("to-other", msg("to-other-1", "BODY-2", to=OTHER), 22),
    ("to-other-but-role", msg("to-other-2", "BODY-3", to=OTHER, role="backend-dev"), 22),
    ("role-held", msg("role-held-1", "BODY-4", role="backend-dev"), 22),
    ("role-left", msg("role-left-1", "BODY-5", role="backend-dev"), 26),
    ("role-later", msg("role-later-1", "BODY-6", role="architect-cto"), 22),
    ("role-deactivated", msg("role-deact-1", "BODY-7", role="architect-cto"), 29),
    ("role-before-birth", msg("role-prev-1", "BODY-8", role="web-dev"), 15),
    ("broadcast-before", msg("bc-before-1", "BODY-9", broadcast=True), 19),
    ("broadcast-after", msg("bc-after-1", "BODY-10", broadcast=True), 21),
    ("sent-in-ledger", msg("sent-1", "BODY-11", frm=ME, to=OTHER), 22),
    ("sent-not-in-ledger", msg("sent-2", "BODY-12", frm=ME, to=OTHER), 23),
    ("sent-other-hash", msg("sent-3", "BODY-13", frm=ME, to=OTHER), 23),
    ("sent-other-seq", msg("sent-4", "BODY-14", frm=ME, broadcast=True), 23),
    ("sent-live-pending", msg("sent-5", "BODY-15", frm=ME, to=OTHER), 24),
    ("no-id", msg(None, "BODY-16", to=ME), 24),
    ("bom", "﻿" + msg("bom-1", "BODY-17", to=ME), 24),
    ("live-dup", msg("live-1", "BODY-18", to=ME), 25),
    ("hello", msg("hello-1", "BODY-19", to=ME, mtype="HELLO"), 25),
    ("not-gzcoord", "plain text BODY-20 for " + ME, 25),
    ("to-me-no-time", msg("to-me-2", "BODY-21", to=ME), None),
    ("role-no-time", msg("role-nt-1", "BODY-22", role="backend-dev"), None),
    ("broadcast-no-time", msg("bc-nt-1", "BODY-23", broadcast=True), None),
    ("unaddressed", msg("unaddr-1", "BODY-24"), 22),
]


class Relay(BaseHTTPRequestHandler):
    messages: list[dict] = []
    calls: list[tuple] = []
    cap = 4
    fail_after: int | None = None

    def log_message(self, *a) -> None:
        pass

    def _send(self, code: int, obj: object) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        Relay.calls.append(("GET", u.path, q, self.headers.get("Authorization")))
        gets = len([c for c in Relay.calls if c[0] == "GET"])
        if Relay.fail_after is not None and gets > Relay.fail_after:
            return self._send(500, {"error": "down"})
        if u.path != "/api/messages" or q.get("full") != "1":
            return self._send(400, {"error": "a listing without full=1 carries a preview"})
        # A consumer never seen starts at seq 1 (no cursor is kept for a
        # listing); since_id pages forward from a record the relay holds.
        start = 0
        if "since_id" in q:
            start = next(i for i, m in enumerate(Relay.messages) if m["id"] == q["since_id"]) + 1
        elif "consumer_id" not in q:
            start = max(0, len(Relay.messages) - Relay.cap)
        self._send(200, {"messages": Relay.messages[start:start + min(Relay.cap, int(q.get("limit", 50)))]})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        Relay.calls.append(("POST", self.path, body, self.headers.get("Authorization")))
        self._send(200, {"ok": True})


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:900]}"))
        fails += not good

    Relay.messages = []
    for i, (name, content, day) in enumerate(RECORDS, start=1):
        rec = {"id": f"relay-{i}", "seq": 100 + i, "sender": ME if f"FROM: {ME}\n" in content else OTHER,
               "content": content}
        if day is not None:
            rec["timestamp"] = DAY.format(day)
        Relay.messages.append(rec)
    seq_of = {name: 100 + i for i, (name, _, _) in enumerate(RECORDS, start=1)}
    text_of = {name: content for name, content, _ in RECORDS}

    server = HTTPServer(("127.0.0.1", 0), Relay)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    tmp = tempfile.mkdtemp(prefix="episodic-import-")
    try:
        home, state_root, store = (os.path.join(tmp, d) for d in ("home", "state", "store"))
        os.makedirs(store)
        with open(os.path.join(store, ".agent-id"), "w") as f:
            f.write(AGENT + "\n")
        env = {k: v for k, v in os.environ.items() if not k.startswith(STRIP)}
        env.update(HOME=home, AGENT_FABRIC_STATE_DIR=state_root, AGENT_FABRIC_SECRET_STORE=store, CLAUDE_BRIDGE_URL=url)
        os.environ.update(AGENT_FABRIC_STATE_DIR=state_root, AGENT_FABRIC_SECRET_STORE=store)
        import episodic as ep
        import episodic_import as ei
        state = ep.state_dir()
        report_path = os.path.join(state, "episodic-import.json")

        src = open(os.path.join(HERE, "communication", "gzcoord", "scripts", "gzmsg.mjs"), encoding="utf-8").read()
        retired = re.search(r"export const RETIRED_TYPES = \[([^\]]*)\]", src)
        check("RETIRED_TYPES is gzmsg.mjs's own",
              retired and tuple(re.findall(r"'([A-Z-]+)'", retired.group(1))) == ei.RETIRED_TYPES, retired)
        check("the fixture's agent id is a UUIDv7 born 2026-09-20",
              ep.AGENT_ID_RE.match(AGENT) and ei.birth(AGENT) == datetime.datetime(2026, 9, 20, tzinfo=datetime.UTC), AGENT)

        def run(*a: str, e: dict | None = None) -> subprocess.CompletedProcess:
            Relay.calls.clear()
            return subprocess.run([sys.executable, TOOL, "gzcoord-import", *a], env=e or env, capture_output=True,
                                  text=True, timeout=120)

        r = run("agent-fabric")
        check("no token: exit 1, said, nothing asked of the relay",
              r.returncode == 1 and "fabric-secrets sync first" in r.stderr and not Relay.calls, (r.returncode, r.stderr))
        os.makedirs(os.path.join(home, ".config", "agent-fabric"))
        with open(os.path.join(home, ".config", "agent-fabric", "secrets.env"), "w") as f:
            f.write(f"export OTHER=x\nexport CLAUDE_BRIDGE_AUTH_TOKEN='{TOKEN}'\n")

        os.makedirs(state, exist_ok=True)
        # The agent's role history, written out of order: valid_from decides.
        # web-dev before its birth is the login's previous agent's.
        hist = [("2026-09-25T00:00:00Z", "architect-cto", "backend-dev"),
                ("2026-09-10T00:00:00Z", "web-dev", None),
                ("2026-09-21T00:00:00Z", "backend-dev", None),
                ("2026-09-28T00:00:00Z", None, "architect-cto")]
        with open(os.path.join(state, "role-history.jsonl"), "w") as f:
            for at, role, prev in hist:
                f.write(json.dumps({"agent": LOGIN, "host": "h", "previous_role": prev, "project": "agent-fabric",
                                    "reason": "x", "role": role, "valid_from": at, "working_copy": "/w"}) + "\n")
            f.write("not json\n")
        sha = lambda name: __import__("hashlib").sha256(text_of[name].encode()).hexdigest()  # noqa: E731
        with open(os.path.join(state, "gzcoord-sent.jsonl"), "w") as f:
            for entry in ({"id": "sent-1", "sha256": sha("sent-in-ledger"), "seq": seq_of["sent-in-ledger"]},
                          {"id": "sent-3", "sha256": "0" * 64, "seq": seq_of["sent-other-hash"]},
                          {"id": "sent-4", "sha256": sha("sent-other-seq"), "seq": 7},
                          {"id": "sent-5", "sha256": sha("sent-live-pending"), "seq": seq_of["sent-live-pending"]}):
                f.write(json.dumps({**entry, "at": "2026-09-22T10:00:00Z"}) + "\n")

        # What live capture already kept: an inbound row, and a send whose
        # outcome was never written.
        conn = ep.connect()
        ep.inbound(conn, [{"content": text_of["live-dup"], "seq": seq_of["live-dup"], "ts": DAY.format(25)}])
        ep.out_pending(conn, text_of["sent-live-pending"])
        conn.close()

        print("a relay that fails part way")
        Relay.fail_after = 2
        r = run("agent-fabric")
        Relay.fail_after = None
        rep = json.load(open(report_path))
        conn = ep.connect()
        check("exit 1, the status said, the token not", r.returncode == 1 and "500" in r.stderr and TOKEN not in r.stderr,
              (r.returncode, r.stderr))
        check("…no marker: the import is not complete", ei.imported(conn) is None and rep["complete"] is False, rep)
        conn.close()

        print("the import")
        r = run("agent-fabric")
        out = r.stdout + r.stderr
        check("exit 0", r.returncode == 0, out)
        gets = [c for c in Relay.calls if c[0] == "GET"]
        check("the whole channel, in pages: since_id moves forward from a fresh consumer",
              len(gets) == -(-len(RECORDS) // Relay.cap) + 1 and "since_id" not in gets[0][2]
              and all("since_id" in g[2] for g in gets[1:]), [g[2] for g in gets])
        consumers = {g[2].get("consumer_id") for g in gets}
        check("one consumer id for the run, not the account's own address", len(consumers) == 1
              and None not in consumers and ME not in consumers and ME in next(iter(consumers)), consumers)
        check("nothing acknowledged: no POST at all (positive control: the GETs were made)",
              gets and not [c for c in Relay.calls if c[0] == "POST"], Relay.calls)
        check("the bearer is the account's token", all(c[3] == f"Bearer {TOKEN}" for c in Relay.calls), Relay.calls)

        conn = ep.connect()
        conn.row_factory = sqlite3.Row
        rows = {(r["direction"], r["message_id"]): r for r in conn.execute("SELECT * FROM episodes")}
        inbound = {m for d, m in rows if d == "inbound"}
        outbound = {m for d, m in rows if d == "outbound"}
        nohash = "sha256:" + sha("no-id")
        check("inbound is exactly: TO me, TO-ROLE held then, a broadcast after birth, no id (by hash), BOM, the live row, "
              "TO me without a time",
              inbound == {"to-me-1", "role-held-1", "bc-after-1", nohash, "bom-1", "live-1", "to-me-2"}, sorted(inbound))
        check("outbound is exactly the agent's own five", outbound == {f"sent-{i}" for i in range(1, 6)}, sorted(outbound))
        check("TO someone else is never stored, even with a TO-ROLE I hold (TO decides alone); nor one addressed to nobody",
              not {"to-other-1", "to-other-2", "unaddr-1"} & (inbound | outbound))
        check("TO-ROLE of a role left, held only later, deactivated, or held before birth: not stored",
              not {"role-left-1", "role-later-1", "role-deact-1", "role-prev-1", "role-nt-1", "bc-nt-1"} & inbound)
        check("a broadcast before birth is not stored (positive control: the one after is)",
              "bc-before-1" not in inbound and "bc-after-1" in inbound)
        check("HELLO and a non-GZCOORD record are not stored",
              "hello-1" not in inbound and not [m for m in inbound if "BODY-20" in rows[("inbound", m)]["content"]])
        r1 = rows[("outbound", "sent-1")]
        check("an outbound row is accepted, at the carrier's seq and time, with the exact text",
              r1["state"] == "accepted" and r1["carrier_seq"] == seq_of["sent-in-ledger"]
              and r1["happened_at"] == "2026-09-22T10:00:00Z" and r1["content"] == text_of["sent-in-ledger"], dict(r1))
        r5 = rows[("outbound", "sent-5")]
        check("a live send left pending is the same row, now accepted with its seq",
              r5["state"] == "accepted" and r5["carrier_seq"] == seq_of["sent-live-pending"], dict(r5))
        rb = rows[("inbound", "bom-1")]
        check("the BOM record keeps its exact text, read through the BOM",
              rb["content"] == text_of["bom"] and rb["sender"] == OTHER and rb["carrier_seq"] == seq_of["bom"], dict(rb))
        rr = rows[("inbound", "role-held-1")]
        check("an inbound row carries the carrier's seq and time", rr["carrier_seq"] == seq_of["role-held"]
              and rr["happened_at"] == "2026-09-22T10:00:00Z" and rr["state"] == "received", dict(rr))
        check("the live-captured row was not duplicated",
              conn.execute("SELECT COUNT(*) FROM episodes WHERE message_id='live-1'").fetchone()[0] == 1)

        rep = json.load(open(report_path))
        c = rep["counts"]
        want = {"outbound": 4, "outbound_promoted": 1, "outbound_same": 0, "outbound_conflict": 0,
                "to_me": 5, "to_role": 1, "broadcast": 1, "to_role_unresolved": 5, "broadcast_before_birth": 1,
                "others": 3, "retired": 1, "not_gzcoord": 1, "no_time": 1,
                # the failed run kept to-me-1 and role-held-1 before the relay
                # stopped; live capture kept live-1
                "inbound_written": 4, "inbound_same": 3,
                "inbound_conflict": 0}
        check("the counts per decision", c == want, {k: (c.get(k), v) for k, v in want.items() if c.get(k) != v})
        un = {u["message_id"]: u["why"] for u in rep["to_role_unresolved"]}
        check("the unresolved TO-ROLE ids, each with why", un == {
            "role-left-1": "role not held then", "role-later-1": "role not held then",
            "role-deact-1": "role not held then", "role-prev-1": "before birth", "role-nt-1": "no time"}, un)
        led = {k: [e["message_id"] for e in v] for k, v in rep["ledger"].items()}
        check("ledger: one missing, one with another hash, one at another seq; each still stored",
              led == {"not_in_ledger": ["sent-2"], "hash_differs": ["sent-3"], "seq_differs": ["sent-4"]}
              and {"sent-2", "sent-3", "sent-4"} <= outbound, led)
        check("the report: the last seq, complete", rep["complete"] is True
              and rep["channels"]["gzapp:gzcoord"]["last_seq"] == 100 + len(RECORDS), rep["channels"])
        raw = open(report_path).read()
        check("no message content in the report (positive control: its ids are there)",
              not re.search(r"BODY-\d", raw) and "SUBJECT" not in raw and "role-left-1" in raw, raw[:300])
        check("the report is private", os.stat(report_path).st_mode & 0o777 == 0o600, oct(os.stat(report_path).st_mode))
        check("the token is in neither stdout, stderr nor the report (positive control: it reached the relay)",
              TOKEN not in r.stdout + r.stderr + raw and any(TOKEN in (c[3] or "") for c in Relay.calls))
        mark = conn.execute("SELECT gzcoord_imported_at, gzcoord_import_seqs FROM meta").fetchone()
        check("the meta marker: when, and the last seq per channel",
              mark[0] and json.loads(mark[1]) == {"gzapp:gzcoord": 100 + len(RECORDS)}, tuple(mark))
        before = sorted((r["id"], r["direction"], r["message_id"], r["content_hash"], r["state"], r["carrier_seq"])
                        for r in conn.execute("SELECT * FROM episodes"))
        conn.close()

        print("again")
        r = run("agent-fabric")
        conn = ep.connect()
        after = sorted((r[0], r[1], r[2], r[3], r[4], r[5]) for r in conn.execute(
            "SELECT id, direction, message_id, content_hash, state, carrier_seq FROM episodes"))
        c2 = json.load(open(report_path))["counts"]
        check("a second run is the same rows", r.returncode == 0 and after == before, (r.stderr, len(before), len(after)))
        check("…counted as already kept", c2["outbound"] == 0 and c2["outbound_same"] == 5 and c2["inbound_written"] == 0
              and c2["inbound_same"] == 7 and not conn.execute("SELECT COUNT(*) FROM conflicts").fetchone()[0], c2)
        conn.close()
        r = run("--if-needed", "agent-fabric")
        check("--if-needed after a complete import asks nothing of the relay (positive control: a run without it does)",
              r.returncode == 0 and "already imported" in r.stdout and not Relay.calls, (r.stdout, Relay.calls))

        print("a body that differs under a kept id")
        Relay.messages.append({"id": "relay-x1", "seq": 900, "timestamp": DAY.format(27),
                               "content": msg("to-me-1", "BODY-X", to=ME)})
        Relay.messages.append({"id": "relay-x2", "seq": 901, "timestamp": DAY.format(27),
                               "content": msg("sent-1", "BODY-Y", frm=ME, to=OTHER)})
        r = run("agent-fabric")
        conn = ep.connect()
        c3 = json.load(open(report_path))["counts"]
        kept = conn.execute("SELECT content FROM episodes WHERE message_id IN ('to-me-1', 'sent-1') ORDER BY message_id").fetchall()
        check("the first copy stands, the other is in conflicts, both directions",
              r.returncode == 0 and c3["inbound_conflict"] == 1 and c3["outbound_conflict"] == 1
              and [k[0] for k in kept] == [text_of["sent-in-ledger"], text_of["to-me"]]
              and conn.execute("SELECT COUNT(*) FROM conflicts").fetchone()[0] == 2, (c3, r.stderr))
        conn.close()
        del Relay.messages[-2:]

        print("refusals")
        r = run("agent-fabric", e={**env, "GZCOORD_CHANNEL": "fabric:control"})
        check("a control channel is refused before any request", r.returncode == 2 and "control" in r.stderr
              and not Relay.calls, (r.returncode, r.stderr))
        r = run("agent-fabric", e={**env, "GZCOORD_CHANNEL": "gzapp:gzcoord"})
        check("…positive control: the same override to an application channel runs", r.returncode == 0 and Relay.calls)
        other = os.path.join(tmp, "other-store")
        os.makedirs(other)
        with open(os.path.join(other, ".agent-id"), "w") as f:
            f.write(AGENT_B + "\n")
        r = run("agent-fabric", e={**env, "AGENT_FABRIC_SECRET_STORE": other})
        check("another agent's journal is refused, before the relay is asked",
              r.returncode == 1 and "belongs to agent" in r.stderr and not Relay.calls, r.stderr)
        r = run("no-such-project")
        check("a project with no integration is said; nothing asked", r.returncode == 0
              and "no GZCoord integration" in r.stdout and not Relay.calls, (r.returncode, r.stdout))
        r = run("--bogus")
        check("usage: an unknown flag is refused", r.returncode == 2 and not Relay.calls, r.returncode)
    finally:
        server.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
