#!/usr/bin/env python3
"""bin/gzcoord-carrier, the real command (ADR-064 rules 2, 5, 7, 8, 9, 11):
`run` as a process in a minimal environment against a fake daemon's data
socket, a scratch fabric whose origin/main holds the committed keys, and a
roster signed with real OpenPGP keys. What is held: render-config writes the
profile for this agent from the valid rows and nothing else and refuses
without a valid row; `run` leases the endpoint as an automated client, takes a
send through the adapter socket, ends the delivery on the peer's receipt,
journals an arrival into the real journal, writes the arrival log before it,
sends the receipt, and ends cleanly on SIGTERM leaving no socket; it refuses
to run with the journal off, with no runtime dir, and beside a live carrier.
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import pwd
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from gzcoord.carrier import server  # noqa: E402
from interweave_fake import FakeDaemon  # noqa: E402
import test_gzcoord_carrier_roster as RT  # noqa: E402 — its real-key helpers
import test_gzcoord_protocol as P  # noqa: E402 — its minimal command environment and agent id store

CMD = os.path.join(ROOT, "bin", "gzcoord-carrier")
fails = 0
LOGIN = pwd.getpwuid(os.getuid()).pw_name
HOST = socket.gethostname().split(".")[0]


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def until(cond, seconds: float = 20.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def git(repo: str, *args: str) -> None:
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, timeout=60,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"})


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gzc-") as d:
        root = RT.Agent(d, "root", "00000000-0000-7000-8000-000000000001", "user")
        me = RT.Agent(d, "me", P.AGENT_ID, LOGIN)
        peer = RT.Agent(d, "peer", "00000000-0000-7000-8000-00000000000b", "othr")
        try:
            # the scratch fabric: committed keys on a ref named origin/main
            fab = os.path.join(d, "fabric")
            os.makedirs(os.path.join(fab, "identities", "keys"))
            lineage = {a.agent_id: {"login": a.login, "fingerprint": a.primary,
                                    "parent": None if a is root else root.agent_id} for a in (root, me, peer)}
            with open(os.path.join(fab, "identities", "keys", "lineage.json"), "w") as fh:
                json.dump(lineage, fh)
            for a in (root, me, peer):
                with open(os.path.join(fab, "identities", "keys", f"{a.agent_id}.asc"), "wb") as fh:
                    fh.write(a.pub)
            git(fab, "init", "-q", "-b", "main")
            git(fab, "add", "-A")
            git(fab, "commit", "-q", "-m", "keys")
            git(fab, "update-ref", "refs/remotes/origin/main", "HEAD")
            rows = [RT.row(me, root, "me", 47101), RT.row(peer, root, "peer", 47102)]
            ros = os.path.join(d, "roster.json")
            with open(ros, "w") as fh:
                json.dump({"version": 1, "profile": "gzcoord", "endpoint": "gzcoord", "port_range": [47100, 47199],
                           "rows": rows}, fh)

            env = P.cmd_env(AGENT_FABRIC_OPERATOR=fab, GZCOORD_CARRIER_ROSTER=ros, AGENT_FABRIC_PYTHON=sys.executable,
                            AGENT_FABRIC_SECRET_STORE=P.id_store())
            run_dir = env["XDG_RUNTIME_DIR"] = P.scratch("gzr")      # 0700 from mkdtemp; removed with the rest

            def cmd(*args: str, **over) -> subprocess.CompletedProcess:
                return subprocess.run([CMD, *args], env={**env, **over}, capture_output=True, text=True,
                                      timeout=120, stdin=subprocess.DEVNULL)

            r = cmd("render-config")
            check("render-config prints this agent's profile: the peer allowlisted, itself not",
                  r.returncode == 0 and RT.peer_id("peer") in r.stdout and RT.peer_id("me") not in
                  r.stdout.split("allowed_peers")[1].split("\n")[0] and "/ip4/127.0.0.1/tcp/47101" in r.stdout, r.stderr + r.stdout)
            target = os.path.join(d, "cfg", "config.yaml")
            r2 = cmd("render-config", "--write", target)
            check("  and --write puts it in place owner-only",
                  r2.returncode == 0 and open(target).read() == r.stdout and oct(os.stat(target).st_mode & 0o777) == "0o600")

            bad = list(rows)
            bad[0] = dict(rows[0], port=47150)    # edited after the countersignature
            badros = os.path.join(d, "bad.json")
            with open(badros, "w") as fh:
                json.dump({"version": 1, "profile": "gzcoord", "endpoint": "gzcoord", "port_range": [47100, 47199],
                           "rows": bad}, fh)
            r3 = cmd("render-config", GZCOORD_CARRIER_ROSTER=badros)
            check("with this agent's own row failing its signature nothing is rendered (exit 2, reason on stderr)",
                  r3.returncode == 2 and r3.stdout == "" and "counts for nothing" in r3.stderr, r3.stderr)

            check("the journal off: run refuses (exit 2)", cmd("run", GZCOORD_JOURNAL="off").returncode == 2)
            env2 = {k: v for k, v in env.items() if k != "XDG_RUNTIME_DIR"}
            r4 = subprocess.run([CMD, "run"], env=env2, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
            check("no runtime directory: run refuses (exit 2)", r4.returncode == 2 and "XDG_RUNTIME_DIR" in r4.stderr, r4.stderr)
            check("usage: no command is exit 1", cmd().returncode == 1 and cmd("bogus").returncode == 1)
            check("status with no carrier is exit 3", cmd("status").returncode == 3)

            # -- the carrier itself ---------------------------------------
            ddir = os.path.join(run_dir, "interweave")
            os.makedirs(ddir, mode=0o700)
            daemon = FakeDaemon(ddir, peer=RT.peer_id("me"), name="gzcoord.sock")
            peer_d = FakeDaemon(os.path.join(d), peer=RT.peer_id("peer"), name="peer.sock")
            daemon.routes = {RT.peer_id("peer"): peer_d}
            peer_d.routes = {RT.peer_id("me"): daemon}
            proc = subprocess.Popen([CMD, "run"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    stdin=subprocess.DEVNULL)
            try:
                check("run holds the lease as an automated client and opens the adapter socket (0600)",
                      until(lambda: daemon.hellos) and daemon.hellos[0]["client"]["kind"] == "automated-client"
                      and daemon.hellos[0]["endpoint"] == {"id": "gzcoord"}
                      and until(lambda: os.path.exists(server.socket_path(run_dir)))
                      and oct(os.stat(server.socket_path(run_dir)).st_mode & 0o777) == "0o600", "")
                check("it never asks for an admin capability", "admin" not in json.dumps(daemon.hellos[0]))
                check("status answers over the adapter socket", until(lambda: cmd("status").returncode == 0)
                      and json.loads(cmd("status").stdout)["connected"] is True)
                r5 = cmd("run")
                check("a second carrier beside a live one is refused (exit 2) and the first is unharmed",
                      r5.returncode == 2 and json.loads(cmd("status").stdout)["ok"], r5.stderr)

                mid = "01a16dd0-0000-7000-8000-000000000001"
                text = (f"[GZCOORD/1] INFO\nFROM: {HOST}/{LOGIN}\nROLE: r\nTO: {HOST}/othr\nMESSAGE-ID: {mid}\n"
                        f"SUBJECT: s\n\nCONTEXT:\nhello\n")
                ans = server.call(server.socket_path(run_dir), {"op": "send", "message_id": mid, "text": text})
                check("a send through the adapter socket is queued and posted to the peer's PeerId",
                      ans["ok"] and ans["carried"] == 1 and until(lambda: len(daemon.sends) == 1)
                      and daemon.sends[0]["peer"] == RT.peer_id("peer"), str(ans))
                # What the peer's carrier would answer: its receipt arrives at OUR daemon from the peer's PeerId.
                daemon.push(RT.peer_id("peer"), "a" * 32, "application/vnd.agentfabric.gzcoord-receipt.v1", mid.encode())
                out = lambda: json.loads(cmd("status").stdout)["outstanding"]  # noqa: E731
                check("the peer's receipt ends the delivery", until(lambda: out() == []))

                inmid = "01a16dd0-0000-7000-8000-000000000002"
                incoming = (f"[GZCOORD/1] INFO\nFROM: {HOST}/othr\nROLE: r\nTO: {HOST}/{LOGIN}\nMESSAGE-ID: {inmid}\n"
                            f"SUBJECT: s\n\nCONTEXT:\nfrom the peer\n")
                daemon.push(RT.peer_id("peer"), "b" * 32, "application/vnd.agentfabric.gzcoord.v1", incoming.encode())
                state = os.path.join(env["AGENT_FABRIC_STATE_DIR"])
                arr = os.path.join(state, "agents", LOGIN, "gzcoord-arrivals.jsonl")
                check("an arrival from the peer is logged with the roster verdict, then journaled, then receipted",
                      until(lambda: os.path.exists(arr)) and json.loads(open(arr).readline())["verdict"] == "ok"
                      and json.loads(open(arr).readline())["carrier"] == "interweave"
                      and until(lambda: any(s["payload"]["media_type"].endswith("gzcoord-receipt.v1") for s in daemon.sends)),
                      str(daemon.sends))
                dbs = [os.path.join(dp, f) for dp, _, fs in os.walk(state) for f in fs if f == "episodic.db"]
                rows_ = []
                for db in dbs:
                    c = sqlite3.connect(db)
                    rows_ += c.execute("SELECT direction, carrier, message_id FROM episodes").fetchall()
                    c.close()
                check("the journal row is inbound, with InterWeave as its carrier", ("inbound", "interweave", inmid) in rows_,
                      str(rows_))
                unseen = server.call(server.socket_path(run_dir), {"op": "unseen"})["records"]
                check("the inbox's adapter is offered it, as from the roster's address",
                      [(x["mid"], x["sender"]) for x in unseen] == [(inmid, f"{HOST}/othr")], str(unseen))

                proc.send_signal(signal.SIGTERM)
                rc = proc.wait(timeout=30)
                check("SIGTERM ends it cleanly (exit 0) and removes the adapter socket",
                      rc == 0 and not os.path.exists(server.socket_path(run_dir)), proc.stderr.read())
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
                daemon.close()
                peer_d.close()
        finally:
            for ag in (root, me, peer):
                RT.drop_key(ag.home)
    for d in P.SCRATCH:      # the protocol suite's scratch is removed by ITS main, which this does not run
        shutil.rmtree(d, ignore_errors=True)
    print(f"\ntest_gzcoord_carrier_process: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
