#!/usr/bin/env python3
"""NOT part of the suite (the name is not test_*): ADR-064 rule 13's live
check, run by TWO accounts of one host, each in its own session, in phases.
It runs what the fleet runs: the INSTALLED transport-daemon (~/.local/bin,
checked against the program digests of runtime/interweave/release.json), the
account's own gzcoord profile and PeerId, the roster rows admitted in
runtime/interweave/roster.json, and `bin/gzcoord-carrier run` from this
checkout, which must be level with main (the roster and the keys that judge it
are main's). Only the port check uses a scratch directory of its own, with a
throwaway profile. The messages are real INFO messages between the two logins,
journaled and logged by the carrier like any other; their subject says what
they are.

The accounts agree on one number, J92_RUN (milliseconds since the epoch, e.g.
`date +%s%3N`), which makes the MESSAGE-IDs of the run: a rerun uses a new one,
or the daemon's duplicate window would swallow it. What the accounts share is
a directory J92_SHARE (default /var/tmp/j92-live-share, mode 1777, files
readable by all): each account's results.

    check      every account   the installed programs are the pinned ones; the
                               roster counts both rows
    serve      every account   renders the profile's config.yaml from the
                               roster (refuses to replace a different one),
                               starts the installed daemon and the carrier
    exchange   every account   sends the other a small message and one past the
                               48 KiB ceiling; waits for both receipts and for
                               the other's two messages, by their ids; prints
                               what it measured
    portcheck  every account   the other account's port is first shown to be
                               held (a TCP connect); then a SECOND daemon of
                               this account, with a throwaway profile, is
                               configured to listen on it: it must be refused;
                               and on a free port, which must start (control)
    stop       every account   ends its processes, removes the config it wrote
                               and its scratch
"""
from __future__ import annotations

import hashlib
import json
import os
import pwd
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

SHARE = os.environ.get("J92_SHARE", "/var/tmp/j92-live-share")
LOGIN = pwd.getpwuid(os.getuid()).pw_name
HOME = os.path.expanduser("~")
WORK = os.environ.get("J92_WORK", os.path.join(HOME, "j92-live"))
BIN = os.path.join(HOME, ".local", "bin")
HOST = socket.gethostname().split(".")[0]
CMD = os.path.join(ROOT, "bin", "gzcoord-carrier")
RELEASE = os.path.join(ROOT, "runtime", "interweave", "release.json")
ROSTER = os.path.join(ROOT, "runtime", "interweave", "roster.json")
FREE_PORT_OFFSET = 90  # own roster port + 90, in the roster's range: two accounts' controls never meet


def say(line: str) -> None:
    print(line, flush=True)


def die(why: str) -> int:
    say(f"j92-live: {why}")
    return 2


def xdg(name: str, default: str) -> str:
    v = os.environ.get(name, "")
    return v if os.path.isabs(v) else os.path.join(HOME, default)


def config_path() -> str:
    return os.path.join(xdg("XDG_CONFIG_HOME", ".config"), "interweave", "profiles", "gzcoord", "config.yaml")


def scratch_env(work: str) -> dict[str, str]:
    d = {k: os.path.join(work, k) for k in ("run", "cfg", "data", "state")}
    return {"PATH": os.environ["PATH"], "HOME": work, "XDG_RUNTIME_DIR": d["run"],
            "XDG_CONFIG_HOME": d["cfg"], "XDG_DATA_HOME": d["data"], "XDG_STATE_HOME": d["state"]}


def mkdirs(work: str) -> None:
    os.makedirs(work, mode=0o700, exist_ok=True)
    os.chmod(work, 0o700)
    for k in ("run", "cfg", "data", "state"):
        os.makedirs(os.path.join(work, k), mode=0o700, exist_ok=True)


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pinned_build() -> dict:
    pin = json.load(open(RELEASE, encoding="utf-8"))
    return pin["releases"][pin["current"]]["x86_64"]


def judged_roster():
    from gzcoord import paths
    from gzcoord.carrier import roster
    r = roster.load(ROSTER)
    good, refused = roster.valid_rows(r, roster.GitMainKeys(paths.operator_root()))
    return r, good, refused


def phase_check() -> int:
    build = pinned_build()
    for prog, want in build["reports"].items():
        path = os.path.join(BIN, prog)
        # the digest first: a program that is not the pinned one is never started
        if not os.path.isfile(path):
            return die(f"{path} is missing: install the pinned release first")
        if sha256_of(path) != build["program_sha256"][prog]:
            return die(f"{path} is not the pinned program (digest differs)")
        run = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=30)
        if run.returncode or run.stdout.strip() != want:
            return die(f"{path} --version printed {run.stdout.strip()!r}, the pin says {want!r}")
        say(f"check: {prog} is the pinned program: {want}")
    r, good, refused = judged_roster()
    for x in refused:
        say(f"check: row of {x.login} refused: {x.reason}")
    if sorted(row["login"] for row in good) != sorted(row["login"] for row in r.rows) or len(good) != 2:
        return die(f"the roster must count exactly two rows, it counts {len(good)}")
    say("check: the roster counts " + ", ".join(f"{row['login']}:{row['port']}" for row in good))
    return 0


def pids_path() -> str:
    return os.path.join(WORK, "pids.json")


def spawn(argv: list[str], env: dict[str, str], log: str) -> int:
    with open(log, "ab") as out:
        p = subprocess.Popen(argv, env=env, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             start_new_session=True)
    pids = json.load(open(pids_path())) if os.path.exists(pids_path()) else []
    pids.append(p.pid)
    json.dump(pids, open(pids_path(), "w"))
    return p.pid


def until(cond, seconds: float = 60.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.1)
    return False


def phase_serve() -> int:
    from gzcoord.carrier import roster, server
    if phase_check():
        return 2
    r, good, _ = judged_roster()
    mine = next((row for row in good if row["login"] == LOGIN), None)
    if mine is None:
        return die("no valid roster row for this account")
    want = roster.render_config(r, good, mine["agent_id"])
    cfg = config_path()
    os.makedirs(WORK, mode=0o700, exist_ok=True)
    state_file = os.path.join(WORK, "state.json")
    try:
        state = json.load(open(state_file))
    except (OSError, ValueError):
        state = {"wrote_config": None}
    if os.path.exists(cfg):
        if open(cfg, encoding="utf-8").read() != want:
            return die(f"{cfg} exists and is not what the roster renders: not replacing it")
    else:
        roster.write_config(cfg, want)
        # the path and digest, not a flag: stop removes exactly this file, and only while it is still this content
        state["wrote_config"] = {"path": cfg, "sha256": hashlib.sha256(want.encode("utf-8")).hexdigest()}
    json.dump(state, open(state_file, "w"))
    rd = os.environ["XDG_RUNTIME_DIR"]
    spawn([os.path.join(BIN, "transport-daemon"), "--profile", "gzcoord"], dict(os.environ), os.path.join(WORK, "daemon.log"))
    if not until(lambda: os.path.exists(os.path.join(rd, "interweave", "gzcoord.sock")), 30):
        return die(f"the daemon did not come up; see {WORK}/daemon.log")
    spawn([CMD, "run"], dict(os.environ), os.path.join(WORK, "carrier.log"))
    if not until(lambda: os.path.exists(server.socket_path(rd)), 60):
        return die(f"the carrier did not come up; see {WORK}/carrier.log")
    say(f"serve: {LOGIN} daemon on 127.0.0.1:{mine['port']} and carrier up")
    return 0


def write_result(name: str, doc: object) -> None:
    """Results go to a directory both accounts write; another local user may have made it first, so it is used only if it is a
    real directory that is ours, or sticky and world-writable, and the file is created fresh, never through a link."""
    os.makedirs(SHARE, exist_ok=True)
    st = os.lstat(SHARE)
    if not stat.S_ISDIR(st.st_mode):
        raise SystemExit(f"j92-live: {SHARE} is not a directory")
    if st.st_uid == os.getuid():
        # makedirs' mode is cut by the umask; the other account must be able to write here
        os.chmod(SHARE, 0o1777)
    elif st.st_mode & 0o1777 != 0o1777:
        raise SystemExit(f"j92-live: {SHARE} belongs to another user and is not sticky and world-writable")
    path = os.path.join(SHARE, name)
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


def mid_of(sender: str, tag: str, t0: int) -> str:
    h = f"{t0 + (0 if tag == 'small' else 1):012x}"
    return f"{h[:8]}-{h[8:]}-7000-8000-{hashlib.sha256((sender + tag).encode()).hexdigest()[:12]}"


def phase_exchange() -> int:
    import episodic
    from gzcoord.carrier import CARRIER_NAME, record, server
    try:
        t0 = int(os.environ["J92_RUN"])
    except (KeyError, ValueError):
        return die("J92_RUN must be the run's number in milliseconds, the same for both accounts")
    sock = server.socket_path(os.environ["XDG_RUNTIME_DIR"])
    doc = json.load(open(ROSTER, encoding="utf-8"))
    other = next(row["login"] for row in doc["rows"] if row["login"] != LOGIN)
    out: dict[str, object] = {"login": LOGIN, "other": other, "run": t0, "sent": {}}
    arr = os.path.join(episodic.state_dir(), "gzcoord-arrivals.jsonl")
    outbox = os.path.join(episodic.state_dir(), CARRIER_NAME)

    def seen() -> list[dict]:
        try:
            return [json.loads(line) for line in open(arr)]
        except FileNotFoundError:
            return []

    def delivery_state(mid: str) -> str | None:
        return next((d["state"] for d in record.read_deliveries(outbox) if d["mid"] == mid), None)
    # The outbox outlives a run: a number used before would let its receipts stand for this run's. Only our own ids are
    # checked: the other account may legitimately have sent first, so its ids in our arrival log prove nothing; it
    # refuses a number it used itself, and its result file says it sent and was receipted in this run.
    own = {mid_of(LOGIN, tag, t0) for tag in ("small", "big")}
    theirs = {mid_of(other, tag, t0) for tag in ("small", "big")}
    used = own & {d["mid"] for d in record.read_deliveries(outbox)}
    if used:
        return die(f"J92_RUN {t0} was used before (message ids {sorted(used)} are already recorded): take a new number")
    big = "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(3200))
    for tag, body in (("small", "hello across accounts"), ("big", big)):
        mid = mid_of(LOGIN, tag, t0)
        text = (f"[GZCOORD/1] INFO\nFROM: {HOST}/{LOGIN}\nROLE: python-dev\nPROJECT: agent-fabric\nTO: {HOST}/{other}\nMESSAGE-ID: {mid}\n"
                f"SUBJECT: j92 rule 13 live check {tag}\n\nCONTEXT:\n{body}\n")
        t = time.monotonic()
        ans = server.call(sock, {"op": "send", "message_id": mid, "text": text}, timeout=30)
        if not (ans.get("ok") and ans.get("carried") == 1 and ans.get("queued") == 1):
            return die(f"the carrier did not queue {tag} for {other}: {ans}")
        # "done" is the recipient's receipt; an abandoned delivery is another state
        done = until(lambda: delivery_state(mid) == "done", 180)
        out["sent"][tag] = {"mid": mid, "bytes": len(text), "queued": ans, "receipted": done,
                            "seconds": round(time.monotonic() - t, 2)}
        say(f"exchange: sent {tag} ({len(text)} bytes) to {other}: receipted={done} in {out['sent'][tag]['seconds']} s")
    expect = theirs

    def arrived() -> set[str]:
        return {x["mid"] for x in seen() if x["carrier"] == CARRIER_NAME and x["verdict"] == "ok"}
    got = until(lambda: expect <= arrived(), 180)
    out["arrived"] = [{k: x[k] for k in ("mid", "carrier", "verdict")} for x in seen() if x["mid"] in expect]
    say(f"exchange: {other}'s messages arrived here: {got} {out['arrived']}")
    write_result(f"{LOGIN}.result.json", out)
    ok = got and all(v["receipted"] for v in out["sent"].values())
    say("exchange: " + ("OK" if ok else "FAILED"))
    return 0 if ok else 1


def phase_portcheck() -> int:
    from gzcoord.carrier import roster
    if phase_check():
        return 2
    doc = json.load(open(ROSTER, encoding="utf-8"))
    theirs = next(row["port"] for row in doc["rows"] if row["login"] != LOGIN)
    free = next(row["port"] for row in doc["rows"] if row["login"] == LOGIN) + FREE_PORT_OFFSET
    # The control that makes a refusal mean something: the port is held right now.
    try:
        socket.create_connection(("127.0.0.1", theirs), timeout=5).close()
    except OSError as e:
        return die(f"nothing answers on the other account's port {theirs} ({e}): their daemon must be up first")
    results = {}
    for label, port, expect_start in (("the other account's port", theirs, False), ("a free port (control)", free, True)):
        work = os.path.join(WORK, f"x{port}")
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(WORK, mode=0o700, exist_ok=True)
        mkdirs(work)
        env = scratch_env(work)
        init = subprocess.run([os.path.join(BIN, "transportctl"), "--profile", "gzcoord", "identity", "init"], env=env,
                              capture_output=True, text=True, timeout=60)
        if init.returncode:
            return die(f"transportctl identity init: {init.stderr.strip()}")
        roster.write_config(os.path.join(work, "cfg", "interweave", "profiles", "gzcoord", "config.yaml"), (
            "schema_version: 2\nprofile: { name: gzcoord }\ntrust:\n  policy: static-allowlist\n  allowed_peers: []\n"
            "endpoints:\n  default_direct_endpoint: gzcoord\n  entries:\n"
            "    - { id: gzcoord, enabled: true, advertise: false, allowed_client_kinds: [automated-client] }\n"
            "channels: { desired: [] }\ntransport: { listen: { addresses: [\"/ip4/127.0.0.1/tcp/%d\"] } }\n"
            "observability: { log_level: info }\n" % port))
        p = subprocess.Popen([os.path.join(BIN, "transport-daemon"), "--profile", "gzcoord"], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL)
        try:
            rc = p.wait(timeout=15)
            started = False
            tail = (p.stdout.read() or "").strip().splitlines()[-2:]
            if rc != 1 or not any("Address already in use" in line for line in tail):
                return die(f"the daemon exited {rc} with {tail}, which is not a refusal of the port")
        except subprocess.TimeoutExpired:
            started, rc, tail = True, None, []
            p.send_signal(signal.SIGTERM)
            p.wait(timeout=30)
        results[label] = {"port": port, "started": started, "exit": rc, "output_tail": tail}
        say(f"portcheck: {label} {port}: daemon {'STARTED and ran' if started else f'exited {rc}'} "
            f"{'' if started else tail}")
        shutil.rmtree(work, ignore_errors=True)
        if started != expect_start:
            say("portcheck: UNEXPECTED")
            return 1
    write_result(f"{LOGIN}.portcheck.json", results)
    say("portcheck: OK")
    return 0


def phase_stop() -> int:
    if os.path.exists(pids_path()):
        for pid in json.load(open(pids_path())):
            try:
                os.killpg(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        time.sleep(2)
    try:
        wrote = json.load(open(os.path.join(WORK, "state.json")))["wrote_config"]
    except (OSError, ValueError, KeyError):
        wrote = None
    removed = False
    if wrote:
        if os.path.isfile(wrote["path"]) and sha256_of(wrote["path"]) == wrote["sha256"]:
            os.unlink(wrote["path"])
            removed = True
        else:
            say(f"stop: {wrote['path']} is not what serve wrote: left in place")
    shutil.rmtree(WORK, ignore_errors=True)
    say(f"stop: {LOGIN} processes ended, {WORK} removed" + (", the config it wrote removed" if removed else ""))
    return 0


def main(argv: list[str]) -> int:
    phases = {"check": phase_check, "serve": phase_serve, "exchange": phase_exchange,
              "portcheck": phase_portcheck, "stop": phase_stop}
    if len(argv) != 1 or argv[0] not in phases:
        print(__doc__.split("\n\n")[0] + "\nusage: " + " | ".join(phases), file=sys.stderr)
        return 1
    return phases[argv[0]]()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
