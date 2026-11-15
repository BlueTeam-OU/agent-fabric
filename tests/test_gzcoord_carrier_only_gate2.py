#!/usr/bin/env python3
"""Gate 2 of docs/proposals/gzcoord-interweave-only-cutover.md, as far as a test can stand in for it: an account in
carrier-only with the relay UNREACHABLE (a port that was bound, read and closed) runs every GZCoord function once through its
real entry, each result checked. Cases: send, watch (--until-delivery), replay (--replay <id> --json), the grant check of
`fabric-pr arm --authorization` (github/arm.py verify_grant), `fabric-jobs add --request`, and a REQUEST's job intake.

The account under test is this Linux login with a REAL `gzcoord-carrier run` on a fake daemon's data socket; the other account
is the wire's far end (a second fake daemon, its PeerId in the signed roster, its messages pushed to the first). A second real
carrier needs a second Linux login, because the carrier names itself from `pwd` (gzmsg.whoami) with no override: that half of
"two accounts" is what the live check has and this stand-in has not.

A function that still needs the relay FAILS here, naming the function and the lines that reach for it. Nothing is patched or
skipped. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import pwd
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from gzcoord.carrier import server  # noqa: E402
from gzcoord.transport import mode  # noqa: E402
from interweave_fake import FakeDaemon  # noqa: E402
import test_gzcoord_carrier_roster as RT  # noqa: E402 — its real-key helpers
import test_gzcoord_protocol as P  # noqa: E402 — its agent id and scratch

BIN = os.path.join(ROOT, "bin")
LOGIN = pwd.getpwuid(os.getuid()).pw_name
HOST = socket.gethostname().split(".")[0]
ME = f"{HOST}/{LOGIN}"
PEER = f"{HOST}/othr"
HEAD = "0123456789abcdef0123456789abcdef01234567"
fails = 0


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


def closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def git(repo: str, *args: str) -> None:
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, timeout=60, stdin=subprocess.DEVNULL,
                   env={"PATH": os.environ["PATH"], "HOME": repo, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"})


def text(kind: str, n: int, frm: str, to: str, body: str = "NOTES:\nhello\n", extra: str = "") -> tuple[str, str]:
    mid = f"01a16dd0-0000-7000-8000-0000000001{n:02d}"
    return mid, (f"[GZCOORD/1] {kind}\nFROM: {frm}\nROLE: backend-dev\nPROJECT: fixture\nTO: {to}\n{extra}"
                 f"MESSAGE-ID: {mid}\nSUBJECT: subject-{n}\n\n{body}")


class World:
    """One account in carrier-only, its relay unreachable, and the peer's far end."""

    def __init__(self, base: str) -> None:
        self.base = base
        self.port = closed_port()
        self.relay_url = f"http://127.0.0.1:{self.port}"
        d = base
        root = RT.Agent(d, "root", "00000000-0000-7000-8000-000000000001", "user")
        me = RT.Agent(d, "me", P.AGENT_ID, LOGIN)
        peer = RT.Agent(d, "peer", "00000000-0000-7000-8000-00000000000b", "othr")
        self.agents = (root, me, peer)
        fab = os.path.join(d, "fabric")
        os.makedirs(os.path.join(fab, "identities", "keys"))
        lineage = {a.agent_id: {"login": a.login, "fingerprint": a.primary, "parent": None if a is root else root.agent_id}
                   for a in self.agents}
        with open(os.path.join(fab, "identities", "keys", "lineage.json"), "w") as fh:
            json.dump(lineage, fh)
        for a in self.agents:
            with open(os.path.join(fab, "identities", "keys", f"{a.agent_id}.asc"), "wb") as fh:
                fh.write(a.pub)
        for rel in ("identities/roles/catalog.json", "projects/gzapp/integration/gzcoord/config.json"):
            os.makedirs(os.path.dirname(os.path.join(fab, rel)), exist_ok=True)
            shutil.copy(os.path.join(P.FIXTURE_OPERATOR, rel), os.path.join(fab, rel))
        git(fab, "init", "-q", "-b", "main")
        git(fab, "add", "-A")
        git(fab, "commit", "-q", "-m", "keys")
        git(fab, "update-ref", "refs/remotes/origin/main", "HEAD")
        ros = os.path.join(d, "roster.json")
        with open(ros, "w") as fh:
            json.dump({"version": 1, "profile": "gzcoord", "endpoint": "gzcoord", "port_range": [47100, 47199],
                       "rows": [RT.row(me, root, "me", 47101), RT.row(peer, root, "peer", 47102)]}, fh)
        ws = os.path.join(d, "ws")
        os.makedirs(ws)
        os.symlink(ROOT, os.path.join(ws, "agent-fabric"))     # the workspace whose .gzcoord a hosting account would start the relay in
        self.run_dir = os.path.join(d, "r")
        os.makedirs(self.run_dir, mode=0o700)
        self.state = os.path.join(d, "state")
        self.agent_dir = os.path.join(self.state, "agents", LOGIN)
        os.makedirs(self.agent_dir)
        home = os.path.join(d, "home")
        os.makedirs(home)
        store = os.path.join(d, "store")
        os.makedirs(store)
        with open(os.path.join(store, ".agent-id"), "w") as fh:
            fh.write(P.AGENT_ID + "\n")
        tmp = os.path.join(d, "t")
        os.makedirs(tmp)
        reg = os.path.join(d, "hosts.json")      # the fleet's placement: both logins on this host, as the live fleet's registry says
        with open(reg, "w") as fh:
            json.dump({"version": 1, "hosts": {HOST: {"operator": "user"}}, "placement": {LOGIN: HOST, "othr": HOST}}, fh)
        # Everything a command sees is named here: no session credential, proxy or HOME of the runner reaches it.
        self.env = {"PATH": os.environ["PATH"], "HOME": home, "TMPDIR": tmp, "LANG": "C.UTF-8",
                    "AGENT_FABRIC_ROOT": os.path.join(ws, "agent-fabric"), "AGENT_FABRIC_OPERATOR": fab,
                    "AGENT_FABRIC_SECRET_STORE": store, "AGENT_FABRIC_STATE_DIR": self.state, "XDG_RUNTIME_DIR": self.run_dir,
                    "AGENT_FABRIC_HOSTS_REGISTRY": reg, "GZCOORD_CARRIER_ROSTER": ros, "AGENT_FABRIC_PYTHON": sys.executable,
                    # the relay is configured, as on an account whose relay was stopped, and nothing listens there
                    "CLAUDE_BRIDGE_URL": self.relay_url, "CLAUDE_BRIDGE_AUTH_TOKEN": "tok-fixture", "GZCOORD_CHANNEL": "fixture:chan"}
        # FABRIC_CONTROL_CARRIER is deliberately unset: control runs as the fleet's committed runtime/control/config.json says
        # ("dual"), and its agentd socket would be looked for under this XDG_RUNTIME_DIR, which is the case's own.
        mode.write("carrier-only", "h1/op", self.agent_dir)
        ddir = os.path.join(self.run_dir, "interweave")
        os.makedirs(ddir, mode=0o700)
        self.daemon = FakeDaemon(ddir, peer=RT.peer_id("me"), name="gzcoord.sock")
        self.peer_d = FakeDaemon(d, peer=RT.peer_id("peer"), name="peer.sock")
        self.daemon.routes = {RT.peer_id("peer"): self.peer_d}
        self.peer_d.routes = {RT.peer_id("me"): self.daemon}
        self.proc = subprocess.Popen([os.path.join(BIN, "gzcoord-carrier"), "run"], env=self.env, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL)
        self.pushes = 0

    def up(self) -> bool:
        return until(lambda: self.daemon.hellos and os.path.exists(server.socket_path(self.run_dir)))

    def push(self, body: str) -> None:
        """The peer's carrier delivering `body` to this account."""
        self.pushes += 1
        self.daemon.push(RT.peer_id("peer"), f"{self.pushes:032x}", "application/vnd.agentfabric.gzcoord.v1", body.encode())

    def run(self, argv: list[str], stdin: str | None = None, timeout: int = 120, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run(argv, env={**self.env, **env}, capture_output=True, text=True, timeout=timeout, cwd=self.base,
                              input=stdin, stdin=None if stdin is not None else subprocess.DEVNULL)

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        for pipe in (self.proc.stdout, self.proc.stderr):
            pipe.close()
        self.daemon.close()
        self.peer_d.close()
        for a in self.agents:
            RT.drop_key(a.home)


def source_line(path: str, needle: str) -> str:
    """path:line of the first line of `path` (under the checkout) holding `needle`, so a failure names where the code is NOW."""
    try:
        with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                if needle in line:
                    return f"{path}:{n}"
    except OSError:
        pass
    return f"{path}:?"


RELAYISH = re.compile(r"relay|refused|unreachable|bridge|127\.0\.0\.1", re.I)


def relay_report(function: str, r: subprocess.CompletedProcess, port: int, *sites: str) -> str:
    """What a failing case says: the function, the output lines that name the relay, and the source lines that reach for it."""
    said = [l for l in (r.stdout + r.stderr).splitlines() if RELAYISH.search(l) or str(port) in l]
    return (f"{function} fails with the relay unreachable (exit {r.returncode}); lines naming it: {said or '(none: see output)'}"
            f"\nreaching for it at: {', '.join(sites) or '(unknown)'}\nstdout: {r.stdout[-600:]!r}\nstderr: {r.stderr[-900:]!r}")


ARM_DRIVER = """
import json, sys
sys.path.insert(0, sys.argv[1])
from github import arm
ref, head, session = sys.argv[2:5]
try:
    login, mid = arm.verify_grant(ref, "7", "O/R", head, session, "", lambda why: arm.Refused(why), word="authorization", field="AUTHORIZES")
    print(json.dumps({"granted": [login, mid]}))
except arm.Refused as e:
    print(json.dumps({"refused": str(e)}))
except arm.Unanswered as e:
    print(json.dumps({"unanswered": str(e)}))
"""
INBOX = os.path.join(BIN, "gzcoord-inbox")


def arm_verify(w: World, ref: str, head: str = HEAD) -> tuple[subprocess.CompletedProcess, dict]:
    """github/arm.py verify_grant, the function `fabric-pr arm --authorization <ref>` calls, in a process of its own."""
    r = w.run([sys.executable, "-I", "-c", ARM_DRIVER, os.path.join(ROOT, "tools", "fabric"), ref, head, ME], timeout=150)
    try:
        return r, json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return r, {}


def jobs_list(w: World) -> list[dict]:
    try:
        with open(os.path.join(w.agent_dir, "jobs.json"), encoding="utf-8") as fh:
            return json.load(fh).get("jobs", [])
    except (OSError, ValueError):
        return []


def watch(w: World, push: str | None, deadline: int = 40) -> tuple[subprocess.CompletedProcess | None, str]:
    """The real watch, started first; `push` is delivered by the peer once it is waiting. (result, why not)"""
    p = subprocess.Popen([INBOX, "--until-delivery", "--deadline", str(deadline)], env=w.env,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL, cwd=w.base)
    try:
        time.sleep(3)      # a watch that is going to wait has started by now; one that gave up has not
        early = p.poll()
        if push is not None:
            w.push(push)
        out, err = p.communicate(timeout=deadline + 60)
    except subprocess.TimeoutExpired:
        p.kill()
        out, err = p.communicate()
        return subprocess.CompletedProcess(p.args, -9, out, err), "did not end within its deadline"
    r = subprocess.CompletedProcess(p.args, p.returncode, out, err)
    return r, (f"ended after under 3 s with exit {early}" if early is not None and push is not None else "")


def cases(w: World) -> None:
    # (1) send
    mid, body = text("INFO", 10, ME, PEER)
    path = os.path.join(w.base, "out.txt")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(body)
    r = w.run([os.path.join(BIN, "gzcoord-send"), path], timeout=120)
    check("send: exit 0 with one line `sent INFO <id>`, the peer's PeerId posted through the carrier, and nothing asked of the relay",
          r.returncode == 0 and r.stdout == f"sent INFO {mid}\n" and until(lambda: len(w.daemon.sends) >= 1)
          and w.daemon.sends[0]["peer"] == RT.peer_id("peer") and until(lambda: w.daemon.forwarded >= 1),
          relay_report("gzcoord-send", r, w.port,
                       source_line("tools/fabric/gzcoord/send.py", "pres = asked_presence("),
                       source_line("tools/fabric/control/presence.py", 'sent = c("/api/send"'),
                       source_line("tools/fabric/control/presence.py", "raise relay_error"))
          + f"\ndaemon sends: {len(w.daemon.sends)}")
    # Diagnostic beside the case above, which stays as it is: with the presence question waived (--force, the sender's own word
    # for it) is the carrier's half of a send sound? It does not stand in for the case above.
    r = w.run([os.path.join(BIN, "gzcoord-send"), path, "--force"], timeout=120)
    check("send --force (diagnostic): the post alone goes through the carrier to the peer and its receipt ends the delivery",
          r.returncode == 0 and f"sent INFO {mid}" in r.stdout and until(lambda: len(w.daemon.sends) >= 1)
          and w.daemon.sends[0]["peer"] == RT.peer_id("peer") and until(lambda: w.daemon.forwarded >= 1)
          and bool(server.call(server.socket_path(w.run_dir), {"op": "status"}).get("outstanding")),
          relay_report("gzcoord-send --force", r, w.port, source_line("tools/fabric/gzcoord/send.py", "if not tok")))
    w.daemon.push(RT.peer_id("peer"), "f" * 32, "application/vnd.agentfabric.gzcoord-receipt.v1", mid.encode())
    check("  and the peer's receipt ends the delivery",
          until(lambda: server.call(server.socket_path(w.run_dir), {"op": "status"}).get("outstanding") == []))

    # (2) watch
    quiet, why = watch(w, None, deadline=4)
    check("watch, control: with nothing sent a watch ends at its deadline, exit 0, showing no message",
          quiet is not None and quiet.returncode == 0 and "subject-" not in quiet.stdout,
          relay_report("gzcoord-inbox --until-delivery", quiet, w.port) if quiet else why)
    wmid, wbody = text("INFO", 11, PEER, ME)
    r, why = watch(w, wbody)
    check("watch: --until-delivery waits, and the message the peer's carrier brings ends it with exit 0, shown once with its subject",
          r is not None and not why and r.returncode == 0 and r.stdout.count("subject-11") == 1,
          relay_report("gzcoord-inbox --until-delivery", r, w.port) + f"\n{why}")

    # (3) replay
    r = w.run([INBOX, "--replay", wmid, "--json"])
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        doc = {}
    check("replay: the message read by its MESSAGE-ID from the journal, addressed here, carried by interweave from the verified peer",
          r.returncode == 0 and doc.get("addressed") is True and doc.get("carrier") == "interweave" and doc.get("sender_verified") is True
          and doc.get("sender") == PEER and (doc.get("metadata") or {}).get("MESSAGE-ID") == wmid,
          relay_report("gzcoord-inbox --replay <id> --json", r, w.port))
    r = w.run([INBOX, "--replay", "01a16dd0-0000-7000-8000-000000009999", "--json"])
    check("replay, negative: an id no journal holds is refused (non-zero, no addressed answer), not made up",
          r.returncode != 0 and '"addressed": true' not in r.stdout, f"{r.returncode} {r.stdout!r} {r.stderr!r}")

    # (4) the grant check of `fabric-pr arm --authorization`
    gmid, gbody = text("DECISION", 12, PEER, ME, "DECISION:\nproceed\n", f"AUTHORIZES: O/R#7@{HEAD[:12]}\n")
    w.push(gbody)
    until(lambda: w.run([INBOX, "--replay", gmid, "--json"]).returncode == 0)
    r, got = arm_verify(w, gmid)
    check("arm --authorization: verify_grant takes the grant from the journal row, its sender the carrier's verified one",
          got.get("granted") == ["othr", gmid], relay_report("fabric-pr arm --authorization (arm.verify_grant)", r, w.port))
    r, got = arm_verify(w, gmid, head="f" * 40)
    check("  negative: the same grant for another head is refused, naming the head",
          "refused" in got and "head" in got["refused"], f"{r.stdout!r} {r.stderr!r}")

    # (5) fabric-jobs add --request
    qmid, qbody = text("REQUEST", 13, PEER, ME, "REQUEST:\nplease\n")
    w.push(qbody)
    until(lambda: w.run([INBOX, "--replay", qmid, "--json"]).returncode == 0)
    r = w.run([os.path.join(BIN, "fabric-jobs"), "add", "--request", qmid, "--topic", "thing"], timeout=150)
    got = [j for j in jobs_list(w) if (j.get("source") or {}).get("message_id") == qmid]
    check("fabric-jobs add --request: exit 0 and one job whose source is that REQUEST, from the peer",
          r.returncode == 0 and len(got) == 1 and got[0]["source"].get("from") == PEER,
          relay_report("fabric-jobs add --request (jobsparts/records.py fetch_message)", r, w.port))

    # (6) a REQUEST's job intake by the watch. What the spool still holds unshown (the grant, the REQUEST above) would end the
    # watch at once with the wrong delivery, so it is drained first: the watch below waits for the message sent after it.
    w.run([INBOX])
    imid, ibody = text("REQUEST", 14, PEER, ME, "REQUEST:\nplease, too\n")
    r, why = watch(w, ibody)
    got = [j for j in jobs_list(w) if (j.get("source") or {}).get("message_id") == imid]
    check("intake: a REQUEST the watch delivers is queued as a job with that MESSAGE-ID as its source, once",
          r is not None and not why and r.returncode == 0 and len(got) == 1 and got[0].get("state") == "queued",
          relay_report("gzcoord-inbox intake (intake.py queue_received)", r, w.port) + f"\n{why}\njobs: {jobs_list(w)}")


def main() -> int:
    base = tempfile.mkdtemp(prefix="g2-")
    w = None
    try:
        w = World(base)
        check("the carrier is up on the fake daemon, the account is in carrier-only, and the relay's port is closed",
              w.up() and mode.read(w.agent_dir)["mode"] == "carrier-only"
              and subprocess.run(["bash", "-c", f"exec 3<>/dev/tcp/127.0.0.1/{w.port}"], capture_output=True).returncode != 0,
              w.proc.stderr.read() if w.proc.poll() is not None else "")
        cases(w)
    finally:
        if w:
            w.close()
        shutil.rmtree(base, ignore_errors=True)
        for d in P.SCRATCH:
            shutil.rmtree(d, ignore_errors=True)
    print(f"\ntest_gzcoord_carrier_only_gate2: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
