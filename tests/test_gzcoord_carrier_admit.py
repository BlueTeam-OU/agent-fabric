#!/usr/bin/env python3
"""tools/fabric/gzcoord/carrier/admit.py (ADR-064 rules 2-3): a row roster-row
makes and roster-admit admits is a row valid_rows counts; a tampered
identity_show, a foreign key, a duplicate agent id/login/PeerId/port, a port
outside the range and an existing transport key each refuse or leave the key
untouched. Real OpenPGP keys in scratch homes; a fake transportctl that logs
its calls. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import stat
import threading
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from gzcoord.carrier import admit as A  # noqa: E402
from gzcoord.carrier import roster as R  # noqa: E402
from signing_fixture import drop_key  # noqa: E402
import test_gzcoord_carrier_roster as T  # noqa: E402

fails = 0
VERSION = "transportctl 0.1.0+7196157887c2"

FAKE = """#!{py}
import os, sys
d = os.environ["FAKE_CTL"]
open(os.path.join(d, "calls"), "a").write(" ".join(sys.argv[1:]) + "\\n")
a = sys.argv[1:]
if a == ["--version"]:
    print(open(os.path.join(d, "version")).read(), end="")
elif a[2:] == ["identity", "init"]:
    key = os.path.join(os.environ["XDG_DATA_HOME"], "interweave", "profiles", a[1], "identity.key")
    os.makedirs(os.path.dirname(key), exist_ok=True)
    open(key, "w").write("SECRET")
elif a[2:] == ["identity", "show"]:
    print(open(os.path.join(d, "show")).read(), end="")
else:
    sys.exit(3)
"""


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def refuses(fn, *a, **k) -> str | None:
    try:
        fn(*a, **k)
    except A.AdmitError as e:
        return str(e)
    return None


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gza-") as d:
        root = T.Agent(d, "root", "00000000-0000-7000-8000-000000000001", "user")
        a = T.Agent(d, "a", "00000000-0000-7000-8000-00000000000a", "alpha")
        b = T.Agent(d, "b", "00000000-0000-7000-8000-00000000000b", "beta")
        c = T.Agent(d, "c", "00000000-0000-7000-8000-00000000000c", "gamma")
        stranger = T.Agent(d, "s", "00000000-0000-7000-8000-0000000000aa", "alpha")   # a key the lineage does not commit
        keys = T.Keys([a, b, c], root)
        release = os.path.join(d, "release.json")
        ctl = os.path.join(d, "fake", "transportctl")
        os.makedirs(os.path.dirname(ctl))
        open(ctl, "w").write(FAKE.format(py=sys.executable))
        os.chmod(ctl, 0o755)
        digest = hashlib.sha256(open(ctl, "rb").read()).hexdigest()

        def write_release(sha: object = digest, drop: bool = False) -> None:
            entry = {"reports": {"transportctl": VERSION}}
            if not drop:
                entry["program_sha256"] = {"transportctl": sha}
            json.dump({"current": "0.1.0", "releases": {"0.1.0": {"x86_64": entry, "aarch64": entry}}}, open(release, "w"))
        write_release()
        fake = os.path.dirname(ctl)

        def env_of(agent: T.Agent, name: str, version: str = VERSION, show: str | None = None) -> dict:
            home = os.path.join(d, "home-" + name)
            os.makedirs(home, exist_ok=True)
            open(os.path.join(fake, "version"), "w").write(version + "\n")
            open(os.path.join(fake, "show"), "w").write(show if show is not None else T.peer_id(name) + "\n")
            return {"PATH": os.environ["PATH"], "GNUPGHOME": agent.home, "FAKE_CTL": fake, "HOME": home,
                    "XDG_DATA_HOME": os.path.join(home, "data")}

        def calls() -> list[str]:
            p = os.path.join(fake, "calls")
            return open(p).read().splitlines() if os.path.exists(p) else []

        def reset() -> None:
            if os.path.exists(os.path.join(fake, "calls")):
                os.unlink(os.path.join(fake, "calls"))

        base = R.Roster("gzcoord", "gzcoord", (47100, 47199), ())
        doc = {"version": 1, "profile": "gzcoord", "endpoint": "gzcoord", "port_range": [47100, 47199], "rows": []}

        def make(agent: T.Agent, name: str, **kw) -> dict:
            return A.make_row(rost=base, keys=keys, agent_id=agent.agent_id, login=agent.login, release_path=release,
                              environ=kw.pop("environ", None) or env_of(agent, name), transportctl=ctl, **kw)

        def admit(row: dict, port: int, rost: R.Roster = base, d_: dict = doc, signer: T.Agent = root) -> dict:
            return A.admit_row(doc=d_, rost=rost, keys=keys, row_in=row, port=port, environ={
                "PATH": os.environ["PATH"], "GNUPGHOME": signer.home})

        try:
            ra = make(a, "a")
            check("roster-row: init ran once (no key yet), then show; version asked first",
                  calls() == ["--version", "--profile gzcoord identity init", "--profile gzcoord identity show"], str(calls()))
            check("roster-row: the row has the reader's fields minus port and countersignature, the PeerId, the roster's endpoint",
                  set(ra) == A.ROW_IN_KEYS and ra["peer_id"] == T.peer_id("a") and ra["endpoint"] == "gzcoord"
                  and ra["identity_show"] == T.peer_id("a") + "\n")
            out = admit(ra, 47101)
            check("roster-admit: a row roster-row made is valid to valid_rows (positive control)",
                  [r["login"] for r in R.valid_rows(R.Roster("gzcoord", "gzcoord", (47100, 47199), tuple(out["rows"])), keys)[0]]
                  == ["alpha"] and out["rows"][0]["port"] == 47101)
            check("roster-admit keeps the document's other fields and leaves the input document alone",
                  {k: out[k] for k in out if k != "rows"} == {k: doc[k] for k in doc if k != "rows"} and doc["rows"] == [])

            # a second login, second port
            rost1 = R.Roster("gzcoord", "gzcoord", (47100, 47199), tuple(out["rows"]))
            rb = make(b, "b")
            out2 = admit(rb, 47102, rost1, out)
            good, bad = R.valid_rows(R.Roster("gzcoord", "gzcoord", (47100, 47199), tuple(out2["rows"])), keys)
            check("a second admitted row counts beside the first", len(good) == 2 and not bad, str(bad))

            # existing transport key: untouched, init not run
            reset()
            keyfile = A.identity_key_path("gzcoord", env_of(a, "a"))
            before = open(keyfile).read(), os.stat(keyfile).st_mtime_ns
            make(a, "a")
            check("an existing transport key: identity init is not run and the key is untouched",
                  "--profile gzcoord identity init" not in calls() and (open(keyfile).read(), os.stat(keyfile).st_mtime_ns) == before,
                  str(calls()))

            # a dangling link at the key path is a key that is there
            reset()
            ed = env_of(b, "dl")
            kp = A.identity_key_path("gzcoord", ed)
            os.makedirs(os.path.dirname(kp), exist_ok=True)
            os.symlink(os.path.join(d, "nowhere"), kp)
            make(b, "dl", environ=ed)
            check("a dangling link at the key path counts as a key: identity init is not run", "--profile gzcoord identity init" not in calls(), str(calls()))

            # version
            for label, ver in (("an older transportctl", "transportctl 0.0.9"), ("a different build of the pin", VERSION + "x")):
                reset()
                e = env_of(c, "c", version=ver)
                msg = refuses(make, c, "c", environ=e)
                check(f"roster-row refuses {label}, and mints nothing", msg is not None and calls() == ["--version"]
                      and not os.path.exists(A.identity_key_path("gzcoord", e)), str(msg))
            msg = refuses(A.make_row, rost=base, keys=keys, agent_id=c.agent_id, login="gamma",
                          release_path=os.path.join(d, "nope.json"), environ=env_of(c, "c"), transportctl=ctl)
            check("roster-row refuses when release.json is absent", msg is not None)

            # the program is the one install.sh put in ~/.local/bin, never a PATH lookup
            e = env_of(c, "c")
            lookalike = os.path.join(d, "lookalike")
            os.makedirs(lookalike)
            os.symlink(ctl, os.path.join(lookalike, "transportctl"))
            os.makedirs(os.path.join(e["HOME"], ".local", "bin"), exist_ok=True)
            e["PATH"] = lookalike + os.pathsep + e["PATH"]
            reset()
            msg = refuses(A.make_row, rost=base, keys=keys, agent_id=c.agent_id, login="gamma", release_path=release, environ=e)
            check("roster-row does not use a transportctl found on PATH (none in ~/.local/bin: refused, nothing run)",
                  msg is not None and calls() == [], str(msg))
            os.symlink(ctl, os.path.join(e["HOME"], ".local", "bin", "transportctl"))
            check("  and uses the one in ~/.local/bin (positive control)",
                  A.make_row(rost=base, keys=keys, agent_id=c.agent_id, login="gamma", release_path=release, environ=e)["login"] == "gamma")
            shutil.rmtree(os.path.join(e["HOME"], "data"), ignore_errors=True)
            check("a relative XDG_DATA_HOME is ignored, as the XDG spec says",
                  A.identity_key_path("gzcoord", {"HOME": "/h", "XDG_DATA_HOME": "rel"}) == "/h/.local/share/interweave/profiles/gzcoord/identity.key")

            # the program is the release's: its digest is checked before it is run
            for label, kw in (("another digest", dict(sha="0" * 64)), ("a digest that is not hex", dict(sha="XYZ")),
                              ("no program_sha256", dict(drop=True))):
                write_release(**kw)
                reset()
                e = env_of(c, "c2")
                msg = refuses(A.make_row, rost=base, keys=keys, agent_id=c.agent_id, login="gamma", release_path=release,
                              environ=e, transportctl=ctl)
                check(f"roster-row refuses {label}, runs nothing and mints nothing",
                      msg is not None and calls() == [] and not os.path.exists(A.identity_key_path("gzcoord", e)), str(msg) + str(calls()))
            write_release()

            # not the committed login / key
            check("roster-row refuses a login other than the lineage's for the agent id",
                  refuses(A.make_row, rost=base, keys=keys, agent_id=c.agent_id, login="other", release_path=release,
                          environ=env_of(c, "c"), transportctl=ctl) is not None)
            reset()
            e = env_of(stranger, "s")
            os.unlink(os.path.join(fake, "calls")) if os.path.exists(os.path.join(fake, "calls")) else None
            msg = refuses(A.make_row, rost=base, keys=keys, agent_id=a.agent_id, login="alpha", release_path=release,
                          environ=e, transportctl=ctl)
            check("roster-row with a foreign key (the account holds another key than the committed one) signs nothing, "
                  "and mints nothing: no transportctl call, no key", msg is not None and calls() == []
                  and not os.path.exists(A.identity_key_path("gzcoord", e)), str(msg) + str(calls()))
            msg = refuses(make, c, "c", environ=env_of(c, "c", show="not a peer id"))
            check("roster-row refuses an identity show that is not one PeerId", msg is not None, str(msg))

            # admit refusals
            t = copy.deepcopy(rb)
            t["identity_show"] = T.peer_id("b") + "\n\n"
            check("roster-admit refuses an identity_show edited after the login signed it",
                  refuses(admit, t, 47103, rost1, out) is not None)
            t = dict(rb, login_signature=stranger.sign(rb["identity_show"].encode()))
            check("roster-admit refuses a login signature by a foreign key", refuses(admit, t, 47103, rost1, out) is not None)
            rc = make(c, "c")
            check("roster-admit refuses a duplicate port",
                  "port" in (refuses(admit, rc, 47101, rost1, out) or ""))
            check("roster-admit refuses a port outside the range", refuses(admit, rc, 47200, rost1, out) is not None
                  and refuses(admit, rc, 1, rost1, out) is not None)
            check("roster-admit refuses a duplicate agent id", "agent_id" in (refuses(admit, ra, 47110, rost1, out) or ""))
            check("roster-admit refuses a duplicate PeerId", "peer_id" in (refuses(admit, dict(rc, peer_id=ra["peer_id"]), 47110, rost1, out) or ""))
            check("roster-admit refuses a duplicate login", "login" in (refuses(admit, dict(rc, login="alpha"), 47110, rost1, out) or ""))
            check("roster-admit refuses a row with a field more or fewer",
                  refuses(admit, dict(rc, port=47111), 47110, rost1, out) is not None
                  and refuses(admit, {k: v for k, v in rc.items() if k != "endpoint"}, 47110, rost1, out) is not None)
            check("roster-admit refuses an endpoint other than the roster's",
                  refuses(admit, dict(rc, endpoint="other"), 47110, rost1, out) is not None)
            # a collision with an already-refused row is still a collision
            junk = dict(out["rows"][0], agent_id="00000000-0000-7000-8000-0000000000ee", login="junk",
                        peer_id=T.peer_id("junk"), port=47150, countersignature="x", endpoint="other")
            rostj = R.Roster("gzcoord", "gzcoord", (47100, 47199), tuple(out["rows"]) + (junk,))
            check("roster-admit refuses a port an already-refused row still claims",
                  refuses(admit, rc, 47150, rostj, out) is not None)
            class StaleKeys(T.Keys):          # the committed .asc is not the key the account holds
                def public_key(self, agent_id: str) -> bytes | None:
                    return stranger.pub if agent_id == a.agent_id else super().public_key(agent_id)
            msg = refuses(A.make_row, rost=base, keys=StaleKeys([a, b, c], root), agent_id=a.agent_id, login="alpha",
                          release_path=release, environ=env_of(a, "a"), transportctl=ctl)
            stale_msg = msg
            pubhome = os.path.join(d, "pubonly")
            os.makedirs(pubhome, mode=0o700)
            subprocess.run(["gpg", "--batch", "--homedir", pubhome, "--import"], input=a.pub, capture_output=True, check=True, timeout=60)
            reset()
            ep = env_of(a, "pub")
            ep["GNUPGHOME"] = pubhome
            msg = refuses(A.make_row, rost=base, keys=keys, agent_id=a.agent_id, login="alpha", release_path=release,
                          environ=ep, transportctl=ctl)
            check("roster-row in an account with only the committed PUBLIC key refuses before it mints anything",
                  msg is not None and "secret" in msg and calls() == [] and not os.path.exists(A.identity_key_path("gzcoord", ep)),
                  str(msg) + str(calls()))
            subprocess.run(["gpgconf", "--homedir", pubhome, "--kill", "all"], capture_output=True, timeout=30)
            # the primary's secret and the other subkeys' stay, the signing subkey's is gone: still a refusal before init
            nohome = os.path.join(d, "nosubsecret")
            shutil.copytree(a.home, nohome, ignore=shutil.ignore_patterns("S.*"))   # a running agent's sockets, kept in the home where /run/user is absent
            os.chmod(nohome, 0o700)
            subprocess.run(["gpgconf", "--homedir", nohome, "--kill", "all"], capture_output=True, timeout=30)
            subprocess.run(["gpg", "--batch", "--yes", "--homedir", nohome, "--delete-secret-keys", a.sub + "!"],
                           capture_output=True, timeout=60, check=True)
            reset()
            en = env_of(a, "nosub")
            en["GNUPGHOME"] = nohome
            msg = refuses(A.make_row, rost=base, keys=keys, agent_id=a.agent_id, login="alpha", release_path=release,
                          environ=en, transportctl=ctl)
            check("roster-row whose signing subkey has no secret (the primary's does) refuses before it mints anything",
                  msg is not None and "secret" in msg and calls() == [] and not os.path.exists(A.identity_key_path("gzcoord", en)),
                  str(msg) + str(calls()))
            subprocess.run(["gpgconf", "--homedir", nohome, "--kill", "all"], capture_output=True, timeout=30)
            check("roster-row refuses a signature that does not verify against the committed key", "does not verify" in (stale_msg or ""), str(stale_msg))
            check("roster-admit signed by a key that is not the lineage's root refuses",
                  refuses(admit, rc, 47103, rost1, out, signer=c) is not None)
            check("roster-admit: positive control for the refusals above — the same row at a free port is admitted",
                  len(admit(rc, 47103, rost1, out)["rows"]) == 2)

            from gzcoord.carrier import main as M
            rj = os.path.join(d, "row.json")
            json.dump(rc, open(rj, "w"))
            sink = open(os.devnull, "w")
            sys.stderr, saved = sink, sys.stderr
            try:
                usage = [M.main(x) for x in (["roster-admit"], ["roster-admit", rj], ["roster-admit", rj, "--port", "x"],
                                              ["roster-admit", rj, "--port", "-1"], ["roster-row", "extra"])]
            finally:
                sys.stderr = saved
            check("the commands' argv: a missing, non-numeric or negative --port and a stray argument are usage errors (1)",
                  usage == [1] * 5, str(usage))

            # one admit at a time: a second waits on the roster directory's lock
            rd = os.path.join(d, "locked")
            os.makedirs(rd)
            rp = os.path.join(rd, "roster.json")
            json.dump(doc, open(rp, "w"))
            saved_env = {k: os.environ.get(k) for k in ("GZCOORD_CARRIER_ROSTER", "AGENT_FABRIC_OPERATOR")}
            os.environ["GZCOORD_CARRIER_ROSTER"] = rp
            os.environ["AGENT_FABRIC_OPERATOR"] = os.path.join(d, "no-operator")
            import fcntl
            dfd = os.open(rd, os.O_RDONLY)
            fcntl.flock(dfd, fcntl.LOCK_EX)
            done = threading.Event()
            codes: list[int] = []
            sys.stderr, saved = sink, sys.stderr
            th = threading.Thread(target=lambda: (codes.append(M.main(["roster-admit", rj, "--port", "47103"])), done.set()))
            th.start()
            held = not done.wait(1.0)
            fcntl.flock(dfd, fcntl.LOCK_UN)
            os.close(dfd)
            released = done.wait(30)
            th.join()
            sys.stderr = saved
            # a holder that never lets go ends the wait, loudly
            dfd = os.open(rd, os.O_RDONLY)
            fcntl.flock(dfd, fcntl.LOCK_EX)
            wait_was, M.ADMIT_LOCK_WAIT = M.ADMIT_LOCK_WAIT, 1.0
            done2 = threading.Event()
            codes2: list[int] = []
            errs = os.path.join(d, "errs.txt")
            sys.stderr, saved = open(errs, "w"), sys.stderr
            th = threading.Thread(target=lambda: (codes2.append(M.main(["roster-admit", rj, "--port", "47103"])), done2.set()))
            th.start()
            ended = done2.wait(15)
            sys.stderr.close()
            sys.stderr = saved
            fcntl.flock(dfd, fcntl.LOCK_UN)
            os.close(dfd)
            th.join()
            M.ADMIT_LOCK_WAIT = wait_was
            check("roster-admit gives up with a refusal when the lock is never released",
                  ended and codes2 == [2] and "nothing admitted" in open(errs).read(), f"{ended} {codes2}")
            for k, v in saved_env.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
            check("roster-admit waits while another admit holds the roster's lock, and goes on when it is released",
                  held and released and codes == [2], f"{held} {released} {codes}")

            # atomic write
            path = os.path.join(d, "out", "roster.json")
            os.makedirs(os.path.dirname(path))
            A.write_roster(path, out)
            A.write_roster(path, out2)
            check("the roster is replaced atomically, 0644, with nothing left beside it",
                  json.load(open(path)) == out2 and stat.S_IMODE(os.stat(path).st_mode) == 0o644
                  and os.listdir(os.path.dirname(path)) == ["roster.json"])
        finally:
            for ag in (root, a, b, c, stranger):
                drop_key(ag.home)
    print("FAILED" if fails else "all ok")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
