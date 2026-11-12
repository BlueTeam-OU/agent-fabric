#!/usr/bin/env python3
"""NOT part of the suite (the name is not test_*): the live read-back of ADR-029 rule 18's control carrier,
run by TWO accounts of one host, each in its own session, in phases. It runs what the fleet will run: the
installed InterWeave programs, each account's own gzcoord profile and PeerId, the roster, and this checkout's
agentd.py / ctl.py / control_link.py (which must be the branch under test, level with the roster's main).

What it does NOT touch: the fleet's relay and its `fabric:control` channel. Both accounts' agentd instances here
are scratch processes (not the units) with FABRIC_CONTROL_CARRIER=dual by environment, a fixture hosts registry
that names the account running `ask` as the operator, and a PRIVATE relay (the tests' FakeRelay in a process of
its own) that `ask` stops in the middle of a run. The fleet's real agentd units keep running as they were.

Each account names the other in J141_PEER. The accounts share a directory J141_SHARE (default
/var/tmp/j141-live-share, mode 1777): the fixture registry and the private relay's URL.

    check    every account   the installed programs are the pinned ones; the roster counts both rows
    render   every account   `interweave-start` as the account itself (carrier_start): renders the profile's
                             config from the roster (now with the fabric-control endpoint) and restarts the
                             account's daemon and carrier units if it changed; then the daemon must list
                             fabric-control
    relay    operator        starts the private relay and writes the fixture registry
    serve    every account   starts this account's scratch agentd (dual); the operator's holds the 0600 socket
    ask      operator        fabric-ctl ping of the peer, two runs: (1) both carriers up; (2) the private relay
                             restarted so that it accepts the request and dies at once, before anyone can answer
                             it: the answer must still come, by the second carrier alone. Prints each run's rows
                             and the arrival log lines
    stop     every account   ends its scratch processes
"""
from __future__ import annotations

import hashlib
import http.server
import json
import os
import pwd
import signal
import socket
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

SHARE = os.environ.get("J141_SHARE", "/var/tmp/j141-live-share")
LOGIN = pwd.getpwuid(os.getuid()).pw_name
HOME = os.path.expanduser("~")
WORK = os.environ.get("J141_WORK", os.path.join(HOME, "j141-live"))
PEER = os.environ.get("J141_PEER", "")
BIN = os.path.join(HOME, ".local", "bin")
HOST = socket.gethostname().split(".")[0]
RELEASE = os.path.join(ROOT, "runtime", "interweave", "release.json")
CHANNEL = "j141:control"


def say(line: str) -> None:
    print(line, flush=True)


def die(why: str) -> int:
    say(f"j141-live: {why}")
    return 2


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pids_path() -> str:
    return os.path.join(WORK, "pids.json")


def spawn(argv: list[str], env: dict[str, str], log: str) -> int:
    os.makedirs(WORK, mode=0o700, exist_ok=True)
    with open(log, "ab") as out:
        p = subprocess.Popen(argv, env=env, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    pids = json.load(open(pids_path())) if os.path.exists(pids_path()) else []
    pids.append(p.pid)
    json.dump(pids, open(pids_path(), "w"))
    return p.pid


def scratch_env() -> dict[str, str]:
    """What the scratch agentd and fabric-ctl need to be this account on the private relay as dual: the minimum,
    never the session's credentials."""
    env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "XDG_RUNTIME_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME") if k in os.environ}
    env.update({"FABRIC_CONTROL_CARRIER": "dual", "FABRIC_CONTROL_CHANNEL": CHANNEL,
                "AGENT_FABRIC_HOSTS_REGISTRY": os.path.join(SHARE, "registry.json"),
                "CLAUDE_BRIDGE_URL": open(os.path.join(SHARE, "relay.url")).read().strip()})
    return env


def pair_refusal() -> str | None:
    if not PEER or PEER == LOGIN:
        return "J141_PEER must name the other account's login"
    return None


def phase_check() -> int:
    if (why := pair_refusal()):
        return die(why)
    pin = json.load(open(RELEASE, encoding="utf-8"))
    build = pin["releases"][pin["current"]]["x86_64"]
    for prog, want in build["reports"].items():
        path = os.path.join(BIN, prog)
        if not os.path.isfile(path) or sha256_of(path) != build["program_sha256"][prog]:
            return die(f"{path} is missing or is not the pinned program")
        run = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=30)
        if run.returncode or run.stdout.strip() != want:
            return die(f"{path} --version printed {run.stdout.strip()!r}, the pin says {want!r}")
        say(f"check: {prog} is the pinned program: {want}")
    human = subprocess.run([os.path.join(BIN, "interweave-human"), "--version"], capture_output=True, text=True, timeout=30)
    say(f"check: interweave-human prints {human.stdout.strip()!r} (its digest is not in release.json: not checked)")
    from gzcoord.carrier import main as carrier_main
    _, good = carrier_main.verified_roster()
    logins = {row["login"] for row in good}
    if not {LOGIN, PEER} <= logins:
        return die(f"the roster must count both {LOGIN} and {PEER}; it counts {len(logins)} rows")
    say(f"check: the roster counts {len(logins)} rows, both of ours among them")
    return 0


def phase_render() -> int:
    if phase_check():
        return 2
    from control import carrier_install
    reply = carrier_install.carrier_start({"args": {}}, root=ROOT)
    say("render: interweave-start as this account: " + json.dumps({k: reply.get(k) for k in ("status", "reason", "rerendered", "units") if k in reply}))
    if reply.get("status") not in ("started", "running", "restarted"):
        return die(f"the units did not come up as asked: {reply}")
    run = subprocess.run([os.path.join(BIN, "transportctl"), "--profile", "gzcoord", "endpoints", "list"], capture_output=True, text=True, timeout=30)
    say("render: endpoints of the profile:\n" + "\n".join("    " + ln for ln in run.stdout.splitlines()))
    if "fabric-control" not in run.stdout:
        return die("the daemon does not list fabric-control")
    return 0


class Relay(http.server.BaseHTTPRequestHandler):
    """The private relay: /api/send, /api/messages, /api/wait on one channel, in memory."""
    rows: list[dict] = []
    lock = threading.Lock()

    def log_message(self, *_a):
        pass

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    die_after_request = False

    def do_POST(self):
        j = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)))
        with self.lock:
            n = len(self.rows) + 1
            self.rows.append({"seq": n, "id": f"id-{n}", "sender": j["sender"], "content": j["content"]})
        self._json({"seq": n, "id": f"id-{n}", "deduplicated": False})
        if self.die_after_request and '"kind":"request"' in j["content"]:
            # the relay accepted the request and is gone before anyone answers it: "stopped mid-run"
            threading.Thread(target=lambda: os._exit(0), daemon=True).start()

    def do_GET(self):
        import urllib.parse
        u = urllib.parse.urlsplit(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        deadline = time.monotonic() + (float(q.get("timeout_seconds") or 0) if u.path == "/api/wait" else 0)
        while True:
            with self.lock:
                ids = [r["id"] for r in self.rows]
                since = q.get("since_id")
                rows = self.rows[-int(q.get("limit") or 50):] if not since else (self.rows[ids.index(since) + 1:] if since in ids else None)
            if rows is None:
                return self._json({"messages": [], "warning": "since_id_not_found"})
            if rows or time.monotonic() >= deadline:
                return self._json({"messages": rows[:50]})
            time.sleep(0.05)


def phase_relay_server() -> int:
    """The private relay, as its own process: `live_control_dual.py relay-server <port> [die-after-request]`."""
    Relay.die_after_request = len(sys.argv) > 3 and sys.argv[3] == "die-after-request"
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[2])), Relay)
    srv.daemon_threads = True
    srv.serve_forever()
    return 0


def phase_relay() -> int:
    os.makedirs(SHARE, exist_ok=True)
    os.chmod(SHARE, 0o1777)
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    os.makedirs(WORK, mode=0o700, exist_ok=True)
    pid = spawn([sys.executable, os.path.abspath(__file__), "relay-server", str(port)], {"PATH": os.environ["PATH"]}, os.path.join(WORK, "relay.log"))
    with open(os.path.join(WORK, "relay.pid"), "w") as fh:
        fh.write(str(pid))
    with open(os.path.join(WORK, "relay.port"), "w") as fh:
        fh.write(str(port))
    reg = {"hosts": {HOST: {"operator": LOGIN}}, "placement": {PEER: HOST}}
    for name, text in (("registry.json", json.dumps(reg)), ("relay.url", f"http://127.0.0.1:{port}")):
        with open(os.path.join(SHARE, name), "w") as fh:
            fh.write(text)
        os.chmod(os.path.join(SHARE, name), 0o644)
    say(f"relay: private relay on 127.0.0.1:{port} (pid {pid}); operator {HOST}/{LOGIN}, placed {PEER}")
    return 0


def phase_serve() -> int:
    if (why := pair_refusal()):
        return die(why)
    if not os.path.exists(os.path.join(SHARE, "relay.url")):
        return die("no relay.url in the share: the operator runs `relay` first")
    pid = spawn([sys.executable, os.path.join(ROOT, "tools", "fabric", "control", "agentd.py")], scratch_env(), os.path.join(WORK, "agentd.log"))
    say(f"serve: scratch agentd (dual) pid {pid}, log {os.path.join(WORK, 'agentd.log')}")
    time.sleep(3)
    say("serve: " + open(os.path.join(WORK, "agentd.log"), errors="replace").read().strip().splitlines()[-1])
    return 0


def ctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fabric", "control", "ctl.py"), *args], env=scratch_env(),
                          capture_output=True, text=True, timeout=120)


def arrivals() -> list[dict]:
    from control.upgrade import state_dir
    try:
        return [json.loads(l) for l in open(os.path.join(state_dir(), "control-arrivals.jsonl"))]
    except OSError:
        return []


def show(label: str, p: subprocess.CompletedProcess, since: int) -> None:
    say(f"\n== {label}: exit {p.returncode}")
    for line in p.stdout.splitlines():
        say("  out: " + line[:400])
    for line in p.stderr.splitlines():
        say("  err: " + line[:400])
    for a in arrivals()[since:]:
        say("  arrival: " + json.dumps(a))


def restart_relay(mode: str) -> None:
    """The private relay again on the SAME port (the scratch agentds were started with its URL), with its rows gone."""
    old = int(open(os.path.join(WORK, "relay.pid")).read())
    try:
        os.kill(old, signal.SIGKILL)
    except OSError:
        pass
    time.sleep(0.5)
    port = open(os.path.join(WORK, "relay.port")).read().strip()
    pid = spawn([sys.executable, os.path.abspath(__file__), "relay-server", port, mode], {"PATH": os.environ["PATH"]}, os.path.join(WORK, "relay.log"))
    with open(os.path.join(WORK, "relay.pid"), "w") as fh:
        fh.write(str(pid))
    time.sleep(1)


def first_row(p: subprocess.CompletedProcess) -> dict:
    try:
        return json.loads(p.stdout.splitlines()[0])
    except (IndexError, ValueError):
        return {}


def phase_ask() -> int:
    if (why := pair_refusal()):
        return die(why)
    since = len(arrivals())
    p = ctl(PEER, "ping", "--json", "--timeout", "20")
    show("1: both carriers up", p, since)
    row = first_row(p)
    ok1 = p.returncode == 0 and row.get("carrier") == "interweave" and row.get("relay_copy") == "same"

    # (2) a relay that accepts the request and is gone before the answer
    restart_relay("die-after-request")
    since = len(arrivals())
    p = ctl(PEER, "ping", "--json", "--timeout", "20")
    show("2: the relay stopped mid-run (it died right after accepting the request)", p, since)
    row2 = first_row(p)
    ok2 = p.returncode == 0 and row2.get("status") == "ok" and row2.get("carrier") == "interweave" and row2.get("relay_copy") == "missing"

    say(f"\nverdict 1 (both carriers, one InterWeave copy counted, the relay's the same): {'PASS' if ok1 else 'FAIL'}")
    say(f"verdict 2 (relay stopped mid-run, fabric-ctl still got the answer): {'PASS' if ok2 else 'FAIL'}")
    return 0 if ok1 and ok2 else 1


def phase_stop() -> int:
    for pid in json.load(open(pids_path())) if os.path.exists(pids_path()) else []:
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            pass
    for name in ("pids.json", "relay.pid"):
        try:
            os.unlink(os.path.join(WORK, name))
        except OSError:
            pass
    say("stop: scratch processes ended; the units and the profile's config are left as `render` made them")
    return 0


PHASES = {"check": phase_check, "render": phase_render, "relay": phase_relay, "serve": phase_serve, "ask": phase_ask, "stop": phase_stop,
          "relay-server": phase_relay_server}


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in PHASES:
        sys.exit(die(f"usage: {sys.argv[0]} {'|'.join(PHASES)}"))
    sys.exit(PHASES[sys.argv[1]]())
