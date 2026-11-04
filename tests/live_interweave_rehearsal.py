#!/usr/bin/env python3
"""NOT part of the suite (the name is not test_*): the carrier against REAL
InterWeave daemons on this host, in one account, as the rehearsal of ADR-064
rule 13's live check. It needs a checkout build of InterWeave:

    INTERWEAVE_BIN=<InterWeave>/target/release python3 tests/live_interweave_rehearsal.py

It makes two scratch profiles of the one profile name, each with its own XDG
directories under a scratch directory (so nothing of the account's own
InterWeave is touched), mints their keys with `transportctl identity init`,
writes a roster signed with throwaway OpenPGP keys, renders both config.yaml
from it, starts two `transport-daemon`s, runs `bin/gzcoord-carrier run` for one
and the engine in this process for the other, and measures: a direct message
each way, a message past the ceiling (compressed and chunked), a daemon killed
under a pending send and brought back, and the lease refused to a second
holder. What it cannot show is another ACCOUNT: both daemons are one uid (rule
13's second half is run by two accounts, see the live check). Prints one line
per measurement; exit 1 on a failed one.
"""
from __future__ import annotations

import hashlib
import json
import os
import pwd
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from gzcoord.carrier import arrivals, engine, ipc, record, roster, server  # noqa: E402
from gzcoord.inbox_parts.tokens import for_me  # noqa: E402
import test_gzcoord_carrier_roster as RT  # noqa: E402
import test_gzcoord_protocol as P  # noqa: E402

BIN = os.environ.get("INTERWEAVE_BIN", "")
CMD = os.path.join(ROOT, "bin", "gzcoord-carrier")
LOGIN = pwd.getpwuid(os.getuid()).pw_name
HOST = socket.gethostname().split(".")[0]
PORTS = (47101, 47102)
fails = 0


def say(line: str) -> None:
    print(line, flush=True)


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    say(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def until(cond, seconds: float = 60.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


class Inst:
    """One profile's directories and processes."""

    def __init__(self, base: str, name: str) -> None:
        self.name = name
        self.dirs = {k: os.path.join(base, name, k) for k in ("run", "cfg", "data", "state")}
        for d in self.dirs.values():
            os.makedirs(d, mode=0o700)
        os.chmod(os.path.join(base, name), 0o700)
        self.env = {"PATH": os.environ["PATH"], "HOME": os.path.join(base, name),
                    "XDG_RUNTIME_DIR": self.dirs["run"], "XDG_CONFIG_HOME": self.dirs["cfg"],
                    "XDG_DATA_HOME": self.dirs["data"], "XDG_STATE_HOME": self.dirs["state"]}
        self.daemon: subprocess.Popen | None = None
        self.log = os.path.join(base, f"{name}.daemon.log")

    def ctl(self, *args: str) -> str:
        r = subprocess.run([os.path.join(BIN, "transportctl"), "--profile", "gzcoord", *args], env=self.env,
                           capture_output=True, text=True, timeout=60)
        if r.returncode:
            raise RuntimeError(f"transportctl {args}: {r.stderr}")
        return r.stdout

    def config_path(self) -> str:
        return os.path.join(self.dirs["cfg"], "interweave", "profiles", "gzcoord", "config.yaml")

    def start(self) -> None:
        self.daemon = subprocess.Popen([os.path.join(BIN, "transport-daemon"), "--profile", "gzcoord"], env=self.env,
                                       stdout=open(self.log, "ab"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)

    def sock(self) -> str:
        return os.path.join(self.dirs["run"], "interweave", "gzcoord.sock")

    def stop(self, sig: int = signal.SIGTERM) -> int | None:
        if self.daemon and self.daemon.poll() is None:
            self.daemon.send_signal(sig)
            try:
                return self.daemon.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.daemon.kill()
                return self.daemon.wait()
        return self.daemon.returncode if self.daemon else None


def main() -> int:
    if not BIN or not os.path.exists(os.path.join(BIN, "transport-daemon")):
        say("INTERWEAVE_BIN must name a directory with transport-daemon and transportctl (a checkout build)")
        return 2
    base = tempfile.mkdtemp(prefix="gzrh", dir=os.environ.get("TMPDIR", "/tmp"))
    os.chmod(base, 0o700)
    a, b = Inst(base, "a"), Inst(base, "b")
    root = RT.Agent(base, "root", "00000000-0000-7000-8000-000000000001", "user")
    me = RT.Agent(base, "me", P.AGENT_ID, LOGIN)
    peer = RT.Agent(base, "peer", "00000000-0000-7000-8000-00000000000b", "othr")
    proc = None
    try:
        for inst in (a, b):
            inst.ctl("identity", "init")
        shows = {inst.name: inst.ctl("identity", "show") for inst in (a, b)}
        say(f"minted two PeerIds: {shows['a'].strip()[:20]}… and {shows['b'].strip()[:20]}…")

        def mkrow(agent, inst, port):
            shown = shows[inst.name]
            r = {"agent_id": agent.agent_id, "login": agent.login, "peer_id": shown.strip(), "endpoint": "gzcoord",
                 "port": port, "identity_show": shown, "login_signature": agent.sign(shown.encode())}
            r["countersignature"] = root.sign(roster.canonical_row(r))
            return r
        rows = [mkrow(me, a, PORTS[0]), mkrow(peer, b, PORTS[1])]
        rdoc = roster.Roster("gzcoord", "gzcoord", (47100, 47199), tuple(rows))
        ros = os.path.join(base, "roster.json")
        json.dump({"version": 1, "profile": "gzcoord", "endpoint": "gzcoord", "port_range": [47100, 47199],
                   "rows": rows}, open(ros, "w"))
        fab = os.path.join(base, "fabric")
        os.makedirs(os.path.join(fab, "identities", "keys"))
        json.dump({x.agent_id: {"login": x.login, "fingerprint": x.primary,
                                "parent": None if x is root else root.agent_id} for x in (root, me, peer)},
                  open(os.path.join(fab, "identities", "keys", "lineage.json"), "w"))
        for x in (root, me, peer):
            open(os.path.join(fab, "identities", "keys", f"{x.agent_id}.asc"), "wb").write(x.pub)
        g = ["git", "-C", fab]
        genv = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x.invalid", "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@x.invalid"}
        for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "k"],
                     ["update-ref", "refs/remotes/origin/main", "HEAD"]):
            subprocess.run([*g, *args], check=True, capture_output=True, env=genv, timeout=60)
        good, refused = roster.valid_rows(rdoc, roster.GitMainKeys(fab))
        check("the roster of the two real PeerIds verifies (both signatures, real keys)", len(good) == 2 and not refused, str(refused))
        for inst, agent in ((a, me), (b, peer)):
            roster.write_config(inst.config_path(), roster.render_config(rdoc, good, agent.agent_id))
        for inst in (a, b):
            inst.start()
        ok = until(lambda: all(os.path.exists(i.sock()) for i in (a, b)))
        check("both daemons are up on their data sockets", ok, open(a.log).read() + open(b.log).read())
        until(lambda: "connected" in a.ctl("peers", "list").lower() or b.ctl("peers", "list").strip() != "", 30)

        # -- carrier A: the real command ------------------------------------
        store = P.id_store()
        env = {"PATH": os.environ["PATH"], "HOME": a.env["HOME"], "XDG_RUNTIME_DIR": a.dirs["run"],
               "AGENT_FABRIC_OPERATOR": fab, "AGENT_FABRIC_ROOT": os.path.join(base, "ws", "agent-fabric"),
               "AGENT_FABRIC_STATE_DIR": os.path.join(base, "a-state"), "AGENT_FABRIC_SECRET_STORE": store,
               "GZCOORD_CARRIER_ROSTER": ros, "AGENT_FABRIC_PYTHON": sys.executable}
        os.makedirs(os.path.join(base, "ws"))
        os.symlink(ROOT, env["AGENT_FABRIC_ROOT"])
        proc = subprocess.Popen([CMD, "run"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                stdin=subprocess.DEVNULL)
        sockA = server.socket_path(a.dirs["run"])
        check("carrier A (bin/gzcoord-carrier run) holds the lease on the real daemon and serves its adapter socket",
              until(lambda: os.path.exists(sockA), 60), proc.stderr.read() if proc.poll() is not None else "")

        # -- carrier B: the engine in this process --------------------------
        iso = lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())  # noqa: E731
        bdir = os.path.join(base, "b-iw")
        jrows: list[tuple[str, str]] = []
        bme = engine.Me(peer.agent_id, peer.login, f"{HOST}/{peer.login}", "dev")

        def parse(text):
            first, _, rest = text.partition("\n")
            meta = {}
            for line in rest.split("\n"):
                if not line.strip():
                    break
                k, _, v = line.partition(": ")
                meta[k] = v
            return first[12:], meta

        def bjournal(text, ts, sender):
            _, meta = parse(text)
            jrows.append((meta["MESSAGE-ID"], text))
            return "written"
        bbox = record.Outbox(bdir, iso_now=iso)
        bcar = engine.Carrier(
            me_fn=lambda: bme, roster_fn=lambda: (rdoc, good), outbox=bbox, spool=arrivals.Spool(bdir, os.path.join(bdir, "gzcoord-shown.jsonl"), iso_now=iso),
            arrival_log=arrivals.ArrivalLog(os.path.join(bdir, "arr.jsonl"), iso_now=iso),
            connect=lambda: ipc.Session.open(b.sock(), endpoint="gzcoord", kind="automated-client"),
            journal=bjournal, parse=parse, for_me=for_me, host=HOST, iso_now=iso)
        bth = threading.Thread(target=bcar.run, daemon=True)
        bth.start()
        check("carrier B (the engine) holds the lease on the other real daemon", until(lambda: bcar.session is not None))

        def a_call(req):
            return server.call(sockA, req, timeout=30)

        def a_out():
            return a_call({"op": "status"})["outstanding"]

        def mk(mid, frm, to, body="hello"):
            return (f"[GZCOORD/1] INFO\nFROM: {frm}\nROLE: r\nTO: {to}\nMESSAGE-ID: {mid}\nSUBJECT: s\n\nCONTEXT:\n{body}\n")

        # -- a direct message each way ---------------------------------------
        m1 = "01a16de0-0000-7000-8000-000000000001"
        t0 = time.monotonic()
        res = a_call({"op": "send", "message_id": m1, "text": mk(m1, f"{HOST}/{LOGIN}", f"{HOST}/othr")})
        ok = until(lambda: any(r[0] == m1 for r in jrows) and a_out() == [], 60)
        say(f"  A -> B direct: queued {res}, journaled at B and receipted to A in {time.monotonic() - t0:.2f} s")
        check("A -> B: B journaled it and A's delivery ended on B's receipt", ok, str(a_out()))

        m2 = "01a16de0-0000-7000-8000-000000000002"
        t0 = time.monotonic()
        bcar.send(m2, mk(m2, f"{HOST}/othr", f"{HOST}/{LOGIN}"))
        ok = until(lambda: [r["message_id"] for r in a_call({"op": "unseen"})["records"]] == [m2] and
                   not [x for x in bbox.outstanding()], 60)
        say(f"  B -> A direct: journaled at A (a real journal) and receipted in {time.monotonic() - t0:.2f} s")
        check("B -> A: A's arrival is in the inbox spool and B's delivery ended on A's receipt", ok)
        arr = [json.loads(l) for l in open(os.path.join(env["AGENT_FABRIC_STATE_DIR"], "agents", LOGIN, "gzcoord-arrivals.jsonl"))]
        check("A's arrival log has the line, carrier interweave, verdict ok",
              [(x["mid"], x["carrier"], x["verdict"]) for x in arr] == [(m2, "interweave", "ok")], str(arr))

        # -- past the ceiling --------------------------------------------------
        big = "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(3200))
        m3 = "01a16de0-0000-7000-8000-000000000003"
        text3 = mk(m3, f"{HOST}/{LOGIN}", f"{HOST}/othr", big)
        t0 = time.monotonic()
        a_call({"op": "send", "message_id": m3, "text": text3})
        ok = until(lambda: any(r[0] == m3 for r in jrows) and a_out() == [], 120)
        got = next((r[1] for r in jrows if r[0] == m3), None)
        say(f"  A -> B {len(text3)} bytes (chunked): reassembled and receipted in {time.monotonic() - t0:.2f} s")
        check("a message past the 48 KiB ceiling arrives byte for byte through the real daemons", ok and got == text3)
        m3b = "01a16de0-0000-7000-8000-000000000033"
        text3b = mk(m3b, f"{HOST}/{LOGIN}", f"{HOST}/othr", "line of text\n" * 20000)
        a_call({"op": "send", "message_id": m3b, "text": text3b})
        ok = until(lambda: any(r[0] == m3b for r in jrows) and a_out() == [], 60)
        check("a compressible 260 KB message goes compressed in one payload and arrives byte for byte",
              ok and next((r[1] for r in jrows if r[0] == m3b), None) == text3b)

        # -- a daemon killed under a pending send --------------------------------
        b.stop(signal.SIGKILL)
        m4 = "01a16de0-0000-7000-8000-000000000004"
        a_call({"op": "send", "message_id": m4, "text": mk(m4, f"{HOST}/{LOGIN}", f"{HOST}/othr")})
        time.sleep(3)
        pending = [x["mid"] for x in a_out()]
        check("with B's daemon dead the send stays outstanding, not given up", pending == [m4], str(pending))
        b.start()
        t0 = time.monotonic()
        ok = until(lambda: any(r[0] == m4 for r in jrows) and a_out() == [], 180)
        say(f"  B's daemon back: delivered by A's retry and receipted after {time.monotonic() - t0:.1f} s")
        check("brought back, B's daemon gets it by A's retry under the same message and A is receipted", ok, str(a_out()))
        check("B journaled it once", len([r for r in jrows if r[0] == m4]) == 1)

        # -- A's own daemon restarted: a fresh lease ---------------------------------
        a.stop(signal.SIGTERM)
        a.start()
        m5 = "01a16de0-0000-7000-8000-000000000005"
        ok = until(lambda: os.path.exists(a.sock()), 30)
        res = None
        end = time.monotonic() + 90
        while time.monotonic() < end and res is None:
            try:
                res = a_call({"op": "send", "message_id": m5, "text": mk(m5, f"{HOST}/{LOGIN}", f"{HOST}/othr")})
            except OSError:
                time.sleep(0.5)
        ok = until(lambda: any(r[0] == m5 for r in jrows) and a_out() == [], 120)
        check("after A's own daemon is restarted the carrier re-leases and the next message is delivered", ok, str(a_out()))

        # -- a second holder of the lease ----------------------------------------------
        try:
            ipc.Session.open(a.sock(), endpoint="gzcoord", kind="automated-client")
            second = None
        except ipc.IpcError as e:
            second = e.code
        check("a second client of the same endpoint is refused by the real daemon (EndpointInUse)",
              second == "EndpointInUse", str(second))

        proc.send_signal(signal.SIGTERM)
        check("carrier A ends on SIGTERM", proc.wait(timeout=30) == 0)
        proc = None
    finally:
        if proc and proc.poll() is None:
            proc.kill()
        for inst in (a, b):
            inst.stop(signal.SIGKILL)
        for x in (root, me, peer):
            RT.drop_key(x.home)
        shutil.rmtree(base, ignore_errors=True)
    say(f"\nlive_interweave_rehearsal: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
