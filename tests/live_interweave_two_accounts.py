#!/usr/bin/env python3
"""NOT part of the suite (the name is not test_*): ADR-064 rule 13's live
check, run by TWO accounts of one host, each in its own session, in phases.
Needs the PINNED InterWeave release (runtime/interweave/release.json), which
the `fetch` phase downloads, verifies and unpacks into the account's scratch
directory, and this repository at the commit being checked. INTERWEAVE_BIN
(a directory holding `transport-daemon` and `transportctl`) overrides where
the programs are taken from; the run's record says which it was. Everything an account creates lives in one scratch directory of its
own (J89_WORK, default ~/j89-live, mode 0700), with its own XDG directories, so
nothing of the account's own InterWeave or journal is touched; what the two
accounts share is a directory J89_SHARE (default /var/tmp/j89-live-share,
mode 1777, files readable by all): each account's PeerId, the roster, a
scratch fabric holding the throwaway keys that sign it, and the results.

    fetch      every account   downloads the pinned archive with its GitHub
                               token (GH_TOKEN, else `gh auth token`), refuses
                               any size or digest but the pin's, unpacks it
                               under <work>/iw and checks each program's
                               --version against the pin; runs nothing of it
    init       every account   mints its transport key; writes <share>/<login>.json
    roster     ONE account     reads both, signs a roster with THROWAWAY keys,
                               writes <share>/roster.json and <share>/fabric
    serve      every account   renders config.yaml from the roster, starts its
                               daemon and its carrier (bin/gzcoord-carrier run)
    exchange   every account   sends the other a small message and one past the
                               48 KiB ceiling; waits for both receipts and for
                               the other's two messages; prints what it measured
    portcheck  every account   starts a SECOND daemon of its own, configured to
                               listen on the port the other account's daemon
                               holds: it must be refused; and on a free port,
                               which must start (the control)
    stop       every account   ends its processes and removes its scratch

The roster is signed with throwaway keys because what this measures is the
carrier and the transport across two uids, not the signing, which the suite
tests with real keys; the real roster is signed by each login and the
coordinator at deployment (ADR-064 rule 2).
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
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

SHARE = os.environ.get("J89_SHARE", "/var/tmp/j89-live-share")
LOGIN = pwd.getpwuid(os.getuid()).pw_name
WORK = os.environ.get("J89_WORK", os.path.join(os.path.expanduser("~"), "j89-live"))
BIN = os.environ.get("INTERWEAVE_BIN") or os.path.join(WORK, "iw", "bin")
HOST = socket.gethostname().split(".")[0]
CMD = os.path.join(ROOT, "bin", "gzcoord-carrier")
PORT_RANGE = (47100, 47199)
PORT_BASE = 47101


def say(line: str) -> None:
    print(line, flush=True)


def die(why: str) -> int:
    say(f"j89-live: {why}")
    return 2


def dirs() -> dict[str, str]:
    return {k: os.path.join(WORK, k) for k in ("run", "cfg", "data", "state")}


def daemon_env(work: str = "") -> dict[str, str]:
    d = {k: os.path.join(work or WORK, k) for k in ("run", "cfg", "data", "state")}
    return {"PATH": os.environ["PATH"], "HOME": work or WORK, "XDG_RUNTIME_DIR": d["run"],
            "XDG_CONFIG_HOME": d["cfg"], "XDG_DATA_HOME": d["data"], "XDG_STATE_HOME": d["state"]}


def ctl(*args: str, work: str = "", profile: str = "gzcoord") -> str:
    r = subprocess.run([os.path.join(BIN, "transportctl"), "--profile", profile, *args], env=daemon_env(work),
                       capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError(f"transportctl {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def mkdirs(work: str) -> None:
    os.makedirs(work, mode=0o700, exist_ok=True)
    os.chmod(work, 0o700)
    for k in ("run", "cfg", "data", "state"):
        os.makedirs(os.path.join(work, k), mode=0o700, exist_ok=True)


def carrier_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AGENT_FABRIC_STATE", "XDG_"))}
    env.update(XDG_RUNTIME_DIR=dirs()["run"], AGENT_FABRIC_STATE_DIR=dirs()["state"],
               AGENT_FABRIC_OPERATOR=os.path.join(SHARE, "fabric"), GZCOORD_CARRIER_ROSTER=os.path.join(SHARE, "roster.json"),
               # the scratch fabric is another uid's: git refuses to read it without this
               GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="safe.directory", GIT_CONFIG_VALUE_0="*")
    return env


def github_token() -> str:
    tok = os.environ.get("GH_TOKEN", "")
    if tok:
        return tok
    r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=30)
    if r.returncode or not r.stdout.strip():
        raise RuntimeError("no GitHub token: set GH_TOKEN or log gh in")
    return r.stdout.strip()


def phase_fetch() -> int:
    from control import interweave
    pin = interweave.load_pin(ROOT)
    version, build = interweave.pinned_build(pin)
    mkdirs(WORK)
    dest = os.path.join(WORK, "iw")
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, mode=0o700)
    try:
        top = interweave.fetch_and_unpack(build, github_token(), dest)
    except (interweave.InstallError, RuntimeError) as e:
        return die(f"fetch: {e}")
    os.symlink(os.path.join(top, "bin"), os.path.join(dest, "bin"))
    for prog, want in build["reports"].items():
        r = subprocess.run([os.path.join(dest, "bin", prog), "--version"], capture_output=True, text=True, timeout=30)
        got = r.stdout.strip()
        if r.returncode or got != want:
            return die(f"fetch: {prog} --version printed {got!r}, the pin says {want!r}")
    say(f"fetch: InterWeave {version} ({build['name']}, {build['size']} bytes, sha256 {build['sha256']}) -> {top}")
    return 0


def phase_init() -> int:
    if not os.path.exists(os.path.join(BIN, "transport-daemon")):
        return die("no transport-daemon under " + BIN + ": run the fetch phase, or set INTERWEAVE_BIN")
    import episodic
    mkdirs(WORK)
    if not os.path.exists(os.path.join(dirs()["data"], "interweave", "profiles", "gzcoord", "identity.key")):
        ctl("identity", "init")
    show = ctl("identity", "show")
    try:
        agent_id = episodic.own_agent_id()
    except episodic.JournalError as e:
        return die(f"this account has no agent id: {e}")
    os.makedirs(SHARE, mode=0o1777, exist_ok=True)
    try:
        os.chmod(SHARE, 0o1777)
    except PermissionError:
        pass
    path = os.path.join(SHARE, f"{LOGIN}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"login": LOGIN, "host": HOST, "agent_id": agent_id, "peer_id": show.strip(), "identity_show": show}, fh)
    os.chmod(path, 0o644)
    say(f"init: {LOGIN} agent {agent_id} PeerId {show.strip()} -> {path}")
    return 0


def phase_roster() -> int:
    import test_gzcoord_carrier_roster as RT
    from gzcoord.carrier import roster
    infos = [json.load(open(os.path.join(SHARE, f))) for f in sorted(os.listdir(SHARE))
             if f.endswith(".json") and f not in ("roster.json",) and not f.endswith(".result.json")]
    if len(infos) != 2:
        return die(f"expected the two accounts' init files in {SHARE}, found {len(infos)}")
    work = os.path.join(WORK, "roster-keys")
    os.makedirs(work, mode=0o700, exist_ok=True)
    rootk = RT.Agent(work, "root", "00000000-0000-7000-8000-000000000001", "user")
    agents = [RT.Agent(work, f"a{i}", info["agent_id"], info["login"]) for i, info in enumerate(infos)]
    rows = []
    for i, (info, agent) in enumerate(zip(infos, agents)):
        r = {"agent_id": info["agent_id"], "login": info["login"], "peer_id": info["peer_id"], "endpoint": "gzcoord",
             "port": PORT_BASE + i, "identity_show": info["identity_show"],
             "login_signature": agent.sign(info["identity_show"].encode())}
        r["countersignature"] = rootk.sign(roster.canonical_row(r))
        rows.append(r)
    fab = os.path.join(SHARE, "fabric")
    shutil.rmtree(fab, ignore_errors=True)
    os.makedirs(os.path.join(fab, "identities", "keys"))
    lineage = {rootk.agent_id: {"login": rootk.login, "fingerprint": rootk.primary, "parent": None}}
    lineage.update({a.agent_id: {"login": a.login, "fingerprint": a.primary, "parent": rootk.agent_id} for a in agents})
    json.dump(lineage, open(os.path.join(fab, "identities", "keys", "lineage.json"), "w"))
    for a in [rootk, *agents]:
        open(os.path.join(fab, "identities", "keys", f"{a.agent_id}.asc"), "wb").write(a.pub)
    genv = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x.invalid", "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@x.invalid"}
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "throwaway keys"],
                 ["update-ref", "refs/remotes/origin/main", "HEAD"]):
        subprocess.run(["git", "-C", fab, *args], check=True, capture_output=True, env=genv, timeout=60)
    with open(os.path.join(SHARE, "roster.json"), "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "profile": "gzcoord", "endpoint": "gzcoord", "port_range": list(PORT_RANGE), "rows": rows}, fh)
    for dp, dn, fn in os.walk(SHARE):
        os.chmod(dp, 0o1777 if dp == SHARE else 0o755)
        for f in fn:
            os.chmod(os.path.join(dp, f), 0o644)
    for a in [rootk, *agents]:
        RT.drop_key(a.home)
    shutil.rmtree(work, ignore_errors=True)
    say("roster: " + ", ".join(f"{r['login']}:{r['port']}" for r in rows) + f" -> {SHARE}/roster.json")
    return 0


def pids_path() -> str:
    return os.path.join(WORK, "pids.json")


def spawn(argv: list[str], env: dict[str, str], log: str, cwd: str | None = None) -> int:
    p = subprocess.Popen(argv, env=env, stdout=open(log, "ab"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         start_new_session=True, cwd=cwd)
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
    from gzcoord.carrier import roster
    r = roster.load(os.path.join(SHARE, "roster.json"))
    good, refused = roster.valid_rows(r, roster.GitMainKeys(os.path.join(SHARE, "fabric")))
    for x in refused:
        say(f"serve: row of {x.login} refused: {x.reason}")
    mine = next((row for row in good if row["login"] == LOGIN), None)
    if mine is None:
        return die("no valid roster row for this account")
    roster.write_config(os.path.join(dirs()["cfg"], "interweave", "profiles", "gzcoord", "config.yaml"),
                        roster.render_config(r, good, mine["agent_id"]))
    spawn([os.path.join(BIN, "transport-daemon"), "--profile", "gzcoord"], daemon_env(), os.path.join(WORK, "daemon.log"))
    sock = os.path.join(dirs()["run"], "interweave", "gzcoord.sock")
    if not until(lambda: os.path.exists(sock), 30):
        return die(f"the daemon did not come up; see {WORK}/daemon.log")
    spawn([CMD, "run"], carrier_env(), os.path.join(WORK, "carrier.log"))
    from gzcoord.carrier import server
    if not until(lambda: os.path.exists(server.socket_path(dirs()["run"])), 60):
        return die(f"the carrier did not come up; see {WORK}/carrier.log")
    say(f"serve: {LOGIN} daemon on 127.0.0.1:{mine['port']} and carrier up")
    return 0


def phase_exchange() -> int:
    from gzcoord.carrier import server
    sock = server.socket_path(dirs()["run"])
    roster_doc = json.load(open(os.path.join(SHARE, "roster.json")))
    other = next(row["login"] for row in roster_doc["rows"] if row["login"] != LOGIN)
    t0 = int(time.time() * 1000)
    out: dict[str, object] = {"login": LOGIN, "other": other, "sent": {}}

    def mk(tag: str, body: str) -> tuple[str, str]:
        h = f"{t0 + (0 if tag == 'small' else 1):012x}"
        mid = f"{h[:8]}-{h[8:]}-7000-8000-{hashlib.sha256((LOGIN + tag).encode()).hexdigest()[:12]}"
        return mid, (f"[GZCOORD/1] INFO\nFROM: {HOST}/{LOGIN}\nROLE: r\nTO: {HOST}/{other}\nMESSAGE-ID: {mid}\n"
                     f"SUBJECT: j89 live {tag}\n\nCONTEXT:\n{body}\n")
    big = "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(3200))
    for tag, body in (("small", "hello across accounts"), ("big", big)):
        mid, text = mk(tag, body)
        t = time.monotonic()
        ans = server.call(sock, {"op": "send", "message_id": mid, "text": text}, timeout=30)
        done = until(lambda: mid not in [x["mid"] for x in server.call(sock, {"op": "status"})["outstanding"]], 180)
        out["sent"][tag] = {"mid": mid, "bytes": len(text), "queued": ans, "receipted": done,
                            "seconds": round(time.monotonic() - t, 2)}
        say(f"exchange: sent {tag} ({len(text)} bytes) to {other}: receipted={done} in {out['sent'][tag]['seconds']} s")
    arr = os.path.join(dirs()["state"], "agents", LOGIN, "gzcoord-arrivals.jsonl")

    def seen() -> list[dict]:
        try:
            return [json.loads(l) for l in open(arr)]
        except FileNotFoundError:
            return []
    got = until(lambda: len({x["mid"] for x in seen()}) >= 2, 180)
    out["arrived"] = [{k: x[k] for k in ("mid", "carrier", "verdict")} for x in seen()]
    say(f"exchange: {other}'s messages arrived here: {got} {out['arrived']}")
    json.dump(out, open(os.path.join(SHARE, f"{LOGIN}.result.json"), "w"))
    os.chmod(os.path.join(SHARE, f"{LOGIN}.result.json"), 0o644)
    ok = got and all(v["receipted"] for v in out["sent"].values())
    say("exchange: " + ("OK" if ok else "FAILED"))
    return 0 if ok else 1


def phase_portcheck() -> int:
    from gzcoord.carrier import roster
    r = json.load(open(os.path.join(SHARE, "roster.json")))
    theirs = next(row["port"] for row in r["rows"] if row["login"] != LOGIN)
    results = {}
    for label, port, expect_start in (("the other account's port", theirs, False), ("a free port (control)", 47190, True)):
        work = os.path.join(WORK, f"x{port}")
        shutil.rmtree(work, ignore_errors=True)
        mkdirs(work)
        ctl("identity", "init", work=work, profile="gzcoord")
        cfg = os.path.join(work, "cfg", "interweave", "profiles", "gzcoord", "config.yaml")
        roster.write_config(cfg, (
            "schema_version: 2\nprofile: { name: gzcoord }\ntrust:\n  policy: static-allowlist\n  allowed_peers: []\n"
            "endpoints:\n  default_direct_endpoint: gzcoord\n  entries:\n"
            "    - { id: gzcoord, enabled: true, advertise: false, allowed_client_kinds: [automated-client] }\n"
            "channels: { desired: [] }\ntransport: { listen: { addresses: [\"/ip4/127.0.0.1/tcp/%d\"] } }\n"
            "observability: { log_level: info }\n" % port))
        p = subprocess.Popen([os.path.join(BIN, "transport-daemon"), "--profile", "gzcoord"], env=daemon_env(work),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL)
        try:
            rc = p.wait(timeout=15)
            started = False
            tail = (p.stdout.read() or "").strip().splitlines()[-2:]
        except subprocess.TimeoutExpired:
            started, rc, tail = True, None, []
            p.send_signal(signal.SIGTERM)
            p.wait(timeout=30)
        results[label] = {"port": port, "started": started, "exit": rc, "stderr_tail": tail}
        say(f"portcheck: {label} {port}: daemon {'STARTED and ran' if started else f'exited {rc}'} "
            f"{'' if started else tail}")
        shutil.rmtree(work, ignore_errors=True)
        if started != expect_start:
            say("portcheck: UNEXPECTED")
            return 1
    json.dump(results, open(os.path.join(SHARE, f"{LOGIN}.portcheck.json"), "w"))
    os.chmod(os.path.join(SHARE, f"{LOGIN}.portcheck.json"), 0o644)
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
    shutil.rmtree(WORK, ignore_errors=True)
    say(f"stop: {LOGIN} processes ended, {WORK} removed")
    return 0


def main(argv: list[str]) -> int:
    phases = {"fetch": phase_fetch, "init": phase_init, "roster": phase_roster, "serve": phase_serve, "exchange": phase_exchange,
              "portcheck": phase_portcheck, "stop": phase_stop}
    if len(argv) != 1 or argv[0] not in phases:
        print(__doc__.split("\n\n")[0] + "\nusage: " + " | ".join(phases), file=sys.stderr)
        return 1
    return phases[argv[0]]()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
