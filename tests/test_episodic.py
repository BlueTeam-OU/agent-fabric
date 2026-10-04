#!/usr/bin/env python3
"""tools/fabric/episodic.py in scratch state: the outbound lifecycle, inbound
idempotence and conflicts, the sender's own echo, all-or-nothing batches,
the owner check, private modes, and two writers at once."""
from __future__ import annotations

import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(HERE, "tools", "fabric", "episodic.py")
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))

AGENT_A = "01a0f782-7e06-7dee-811f-0a860ed93bf3"
AGENT_B = "01a0f7ea-15b0-7ed9-a176-6eb006592db1"
ME = f"{socket.gethostname().split('.')[0]}/{__import__('pwd').getpwuid(os.getuid()).pw_name}"


def msg(mid: str, body: str = "body", sender: str = "develop-qzapp/someone", reply: str | None = None) -> str:
    head = f"[GZCOORD/1] INFO\nFROM: {sender}\nROLE: x\nTO: {ME}\n" + (f"IN-REPLY-TO: {reply}\n" if reply else "")
    return head + f"MESSAGE-ID: {mid}\nSUBJECT: s\n\nINFO:\n{body}\n"


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    tmp = tempfile.mkdtemp(prefix="episodic-")
    try:
        state, store = os.path.join(tmp, "state"), os.path.join(tmp, "store")
        os.makedirs(store)
        with open(os.path.join(store, ".agent-id"), "w") as f:
            f.write(AGENT_A + "\n")
        os.environ.update(AGENT_FABRIC_STATE_DIR=state, AGENT_FABRIC_SECRET_STORE=store)
        import episodic as ep

        sys.path.insert(0, os.path.join(HERE, "runtime"))
        import identity
        import secret_store
        check("the state dir, the agent id and the address are their sources' own",
              ep.state_dir() == identity.agent_state_dir() and ep.own_agent_id() == secret_store.own_agent_id() == AGENT_A
              and ep.own_address() == f"{identity.current_host()}/{identity.current_agent()}")
        conn = ep.connect()
        path = ep.db_path()
        print("outbound: pending before the carrier, then its outcome")
        ep.out_pending(conn, msg("m-1", "first"), project="agent-fabric")
        rows = conn.execute("SELECT state, content FROM episodes WHERE message_id='m-1'").fetchall()
        check("pending row with the exact text", rows == [("pending", msg("m-1", "first"))], rows)
        ep.out_final(conn, "m-1", "accepted", 41)
        check("accepted with the carrier's seq, the same row",
              conn.execute("SELECT state, carrier_seq, count(*) FROM episodes WHERE message_id='m-1'").fetchone()
              == ("accepted", 41, 1))
        ep.out_pending(conn, msg("m-2"))
        ep.out_final(conn, "m-2", "failed")
        ep.out_pending(conn, msg("m-2"))
        check("a failed send retried is the same row, pending again",
              conn.execute("SELECT state, count(*) FROM episodes WHERE message_id='m-2'").fetchone() == ("pending", 1))
        check("an attempt over a row it made fresh, or over a failed one, owns its outcome",
              ep.out_attempt(conn, msg("m-4"))[1] is False and ep.out_final(conn, "m-4", "failed") is None
              and ep.out_attempt(conn, msg("m-4"))[1] is False)
        check("an attempt over a row still pending says the earlier outcome is unknown (review of #78)",
              ep.out_attempt(conn, msg("m-4"))[1] is True)
        ep.out_final(conn, "m-1", "failed")
        check("a retransmission that fails leaves the accepted copy accepted (review of #78)",
              conn.execute("SELECT state, carrier_seq FROM episodes WHERE message_id='m-1'").fetchone()
              == ("accepted", 41))
        try:
            ep.out_pending(conn, msg("m-1", "another body"))
            check("an outbound id reused with another body is refused", False)
        except ep.IntegrityError:
            check("an outbound id reused with another body is refused", True)
        try:
            ep.out_final(conn, "never-pending", "accepted")
            check("an outcome with no pending row is refused", False)
        except ep.JournalError:
            check("an outcome with no pending row is refused", True)

        print("inbound: idempotent, a conflicting body kept aside, the echo folded in")
        c = ep.inbound(conn, [{"content": msg("i-1", "hello", reply="m-1"), "seq": 50, "ts": "2026-10-01T10:00:00Z"}])
        check("an addressed message is written", c["written"] == 1)
        c = ep.inbound(conn, [{"content": msg("i-1", "hello", reply="m-1"), "seq": 50}])
        check("the same again is the same row", c["same"] == 1
              and conn.execute("SELECT count(*) FROM episodes WHERE message_id='i-1'").fetchone()[0] == 1)
        c = ep.inbound(conn, [{"content": msg("i-1", "changed"), "seq": 51}])
        kept = conn.execute("SELECT content FROM episodes WHERE message_id='i-1'").fetchone()[0]
        check("a reused id with another body: the first stands, the other kept in conflicts",
              c["conflict"] == 1 and "hello" in kept
              and conn.execute("SELECT count(*) FROM conflicts WHERE message_id='i-1'").fetchone()[0] == 1)
        check("a carrier's microseconds become the journal's seconds", conn.execute(
            "SELECT happened_at FROM episodes WHERE message_id='i-1'").fetchone()[0] == "2026-10-01T10:00:00Z")
        c = ep.inbound(conn, [{"content": msg("i-us", "x"), "seq": 52, "ts": "2026-10-01T17:19:04.630273Z"}])
        check("…the relay's form included", conn.execute(
            "SELECT happened_at FROM episodes WHERE message_id='i-us'").fetchone()[0] == "2026-10-01T17:19:04Z")
        check("…and the thread edge is recorded", conn.execute(
            "SELECT in_reply_to FROM episodes WHERE message_id='i-1'").fetchone()[0] == "m-1")
        ep.out_pending(conn, msg("b-1", "to all", sender=ME))
        c = ep.inbound(conn, [{"content": msg("b-1", "to all", sender=ME), "seq": 77}])
        check("its own message coming back is no second episode; it fills the carrier seq",
              c["echo"] == 1 and conn.execute("SELECT count(*), max(carrier_seq) FROM episodes WHERE message_id='b-1'")
              .fetchone() == (1, 77))
        c = ep.inbound(conn, [{"content": msg("i-2"), "seq": 60}, {"content": "not a message", "seq": 61}])
        check("a record the parser cannot read is kept, keyed by its hash, and holds no other (review of #78)",
              c["written"] == 2 and conn.execute("SELECT count(*) FROM episodes WHERE message_id='i-2' OR "
                                                 "message_id=?", ("sha256:" + ep._sha("not a message"),)).fetchone()[0] == 2)
        noid = f"[GZCOORD/1] INFO\nFROM: develop-qzapp/old\nROLE: x\nBROADCAST: true\nSUBJECT: s\n\nINFO:\nhi\n"
        ep.inbound(conn, [{"content": noid, "seq": 62}])
        check("…a broadcast with no MESSAGE-ID too", conn.execute(
            "SELECT sender FROM episodes WHERE message_id=?", ("sha256:" + ep._sha(noid),)).fetchone() == ("develop-qzapp/old",))
        forged = msg("m-3", "I am you", sender=ME)
        ep.out_pending(conn, msg("e-1", "posted, outcome lost", sender=ME))
        ep.out_pending(conn, msg("e-2", "posted, client saw an error", sender=ME))
        ep.out_final(conn, "e-2", "failed")
        c = ep.inbound(conn, [{"content": msg("e-1", "posted, outcome lost", sender=ME), "seq": 21},
                              {"content": msg("e-2", "posted, client saw an error", sender=ME), "seq": 22}])
        check("an echo of a pending or failed row: the carrier holds it, so accepted with its seq and carrier "
              "(review of #78)",
              c["echo"] == 2 and conn.execute("SELECT state, carrier_seq, carrier FROM episodes WHERE message_id IN "
                                             "('e-1','e-2') ORDER BY message_id").fetchall()
              == [("accepted", 21, ep.DEFAULT_CARRIER), ("accepted", 22, ep.DEFAULT_CARRIER)])
        unverified = msg("e-3", "the backfill could not vouch for this", sender=ME)
        conn.execute("INSERT INTO episodes (id, source, direction, state, happened_at, recorded_at, message_id, "
                     "type, sender, content, content_hash, metadata_json) VALUES ('u-3', ?, 'outbound', 'unverified', "
                     "?, ?, 'e-3', 'INFO', ?, ?, ?, '{}')",
                     (ep.SOURCE, ep.now(), ep.now(), ME, unverified, ep._sha(unverified)))
        c = ep.inbound(conn, [{"content": unverified, "seq": 23}])
        check("…but an echo of an unverified row leaves it unverified: the same copy is no more proof (review of #88)",
              c["echo"] == 1 and conn.execute("SELECT state, carrier_seq FROM episodes WHERE message_id='e-3'")
              .fetchone() == ("unverified", 23))
        ep.out_pending(conn, msg("m-3", "what I really sent", sender=ME))
        c = ep.inbound(conn, [{"content": forged, "seq": 63}, {"content": msg("m-4", "x", sender=ME), "seq": 64}])
        check("a message naming this account as FROM is no echo unless the journal holds that body; kept as received",
              c["claims_me"] == 2 and c["echo"] == 0 and conn.execute(
                  "SELECT direction, state, carrier_seq FROM episodes WHERE message_id='m-3' ORDER BY direction").fetchall()
              == [("inbound", "received", 63), ("outbound", "pending", None)])

        print("the header, read as gzmsg's parse() reads it")
        cases = {
            "bom": "\ufeff" + msg("bom-1"),
            "body lines after a missing blank": "[GZCOORD/1] INFO\nFROM: h/x\nMESSAGE-ID: real-id\nSUBJECT: s\nINFO:\n"
                                                 "FROM: h/me\nMESSAGE-ID: other-id\n",
            "a repeated key": "[GZCOORD/1] INFO\nFROM: h/a\nFROM: h/b\nMESSAGE-ID: r\n\nINFO:\nx\n",
            "lowercase and spaced keys": "[GZCOORD/1] INFO\nfrom: h/a\nX Y: z\nFROM:h/b\nMESSAGE-ID: q\n",
            "values JS trim() keeps or drops": "[GZCOORD/1] INFO\nFROM: h/a\x1f\nMESSAGE-ID: \u00a0t\ufeff\nSUBJECT: \x1cs\n",
            "crlf": "[GZCOORD/1] INFO\r\nFROM: h/a\r\nMESSAGE-ID: c\r\n\r\nINFO:\r\nx\r\n",
        }
        py = {k: list(ep.parse_header(v)) for k, v in cases.items()}
        # The validator is Python now (tools/fabric/gzcoord/gzmsg.py, ADR-040
        # §7), and its parse() is what the inbox delivers by: the journal's
        # header reading is held to it in this process.
        from gzcoord import gzmsg
        gz = {k: [m["type"], m["metadata"]] for k, m in ((k, gzmsg.parse(v)) for k, v in cases.items())}
        check("type and metadata equal gzmsg's parse() on every shape (review of #78)", gz == py, (gz, py))

        print("private, owned")
        modes = {s: stat.S_IMODE(os.stat(path + s).st_mode) for s in ("", "-wal", "-shm") if os.path.exists(path + s)}
        check("directory 0700, database and its WAL files 0600",
              stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode) == 0o700 and set(modes.values()) == {0o600}, modes)
        conn.close()
        try:
            ep.connect(agent_id=AGENT_B)
            check("another agent id is refused the journal (a reused login)", False)
        except ep.JournalError as e:
            check("another agent id is refused the journal (a reused login)", "belongs to agent" in str(e), e)
        os.environ["AGENT_FABRIC_SECRET_STORE"] = os.path.join(tmp, "no-store")
        try:
            ep.connect(os.path.join(tmp, "other.db"))
            check("no agent id: no journal", False)
        except ep.JournalError:
            check("no agent id: no journal", True)
        os.environ["AGENT_FABRIC_SECRET_STORE"] = store

        print("the CLI, and two writers at once")
        env = {**os.environ}
        r = subprocess.run([sys.executable, TOOL, "gzcoord-in"], input=json.dumps(
            {"content": msg("c-1", "secret-looking body"), "seq": 90}) + "\n", env=env, capture_output=True, text=True,
            timeout=60)
        check("gzcoord-in writes and prints no content", r.returncode == 0
              and "secret-looking" not in r.stdout + r.stderr, r.stderr)
        r = subprocess.run([sys.executable, TOOL, "gzcoord-out-pending"], input=msg("m-1", "reuse"), env=env,
                           capture_output=True, text=True, timeout=60)
        check("an outbound id reuse exits 3", r.returncode == 3, (r.returncode, r.stderr))
        r = subprocess.run([sys.executable, TOOL, "gzcoord-in"], input='["not", "an object"]\n', env=env,
                           capture_output=True, text=True, timeout=60)
        check("gzcoord-in given a line that is no record: exit 1, one line, no traceback",
              r.returncode == 1 and "Traceback" not in r.stderr and r.stderr.count("\n") == 1, r.stderr)
        procs = [subprocess.Popen([sys.executable, TOOL, "gzcoord-in"], stdin=subprocess.PIPE, env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        outs = []
        for n, p in enumerate(procs):
            lines = "".join(json.dumps({"content": msg(f"w{n}-{i}"), "seq": i}) + "\n" for i in range(50))
            outs.append(p.communicate(lines, timeout=120))
        conn = ep.connect()
        check("two writers at once: every row, no error",
              all(p.returncode == 0 for p in procs)
              and conn.execute("SELECT count(*) FROM episodes WHERE message_id LIKE 'w%'").fetchone()[0] == 100, outs)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
