#!/usr/bin/env python3
"""Tests for tools/fabric/store_enroll.py's internals; the behaviour is
runtime/provisioning/secrets/test_store-enroll.sh's, run unchanged against
the store-enroll.sh shim (ADR-040 §5 rule 5). What is here is what that
suite does not reach: the usage paths, an unreadable hosts registry, a
step that hangs, either side of the bundle pipeline failing, a dry run,
and the store tool's exit codes as the enrolment reads them. A fake store
tool and a fake host executor stand in; nothing here makes a key. Plain
script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import store_enroll as se  # noqa: E402

SHIM = os.path.join(HERE, "runtime", "provisioning", "secrets", "store-enroll.sh")


def clean_env(**extra) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_"))}
    env.update(extra)
    return env


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    def shim(*args: str, **env) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", SHIM, *args], capture_output=True, text=True, timeout=60,
                              env=clean_env(AGENT_FABRIC_PYTHON=sys.executable, **env))

    with tempfile.TemporaryDirectory() as tmp:
        def put(path: str, text: str, mode: int = 0o644) -> str:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.chmod(path, mode)
            return path

        print("usage")
        r = shim("--help")
        check("--help: the help text on stdout, exit 0", r.returncode == 0 and r.stdout == se.HELP and r.stderr == "")
        r = shim()
        check("no login: the same text on stderr, exit 2", r.returncode == 2 and r.stderr == se.HELP and r.stdout == "")
        r = shim("--frob", "kid")
        check("an unknown flag: one line, exit 2",
              r.returncode == 2 and r.stderr == "store-enroll: unknown flag --frob\n")
        r = shim("kid", "--help", "--frob")
        check("--help stops the parse where it stands", r.returncode == 0 and r.stdout == se.HELP)
        r = shim("kid", "--host")
        check("--host without a value: one line, exit 1, never a traceback",
              r.returncode == 1 and r.stderr == "store-enroll: --host needs a host id\n")
        r = shim("--rename", "only-one")
        check("--rename takes exactly two logins", r.returncode == 1 and "--rename takes <old> <new>" in r.stderr)
        r = shim("--self", "kid")
        check("--self takes none", r.returncode == 1 and "--self takes no login" in r.stderr)
        check("flags in any order, = and spaced", se.parse(["a", "--host=h", "--born-now", "b", "--dry-run"])[0]["host"] == "h"
              and se.parse(["--host", "h2", "a"]) == ({"dry": False, "self": False, "rename": False, "born_now": False,
                                                       "host": "h2", "help": False}, ["a"]))

        # A fake store tool: answers from files the case writes.
        fake = put(f"{tmp}/store.py", """import os, sys
d = os.environ["FAKE_STORE"]
cmd = sys.argv[1]
def code(name, default=0):
    p = os.path.join(d, name)
    return int(open(p).read()) if os.path.exists(p) else default
if cmd == "id-of":
    rc = code("id-of.rc", 3)
    if rc == 0: print("01a0f782-7e06-7dee-811f-0a860ed93bf3")
    elif rc != 3: print("noise on stderr", file=sys.stderr); print("last line on stderr", file=sys.stderr)
    sys.exit(rc)
if cmd == "export-key": sys.exit(code("export-key.rc"))
if cmd == "mint-id": print("01a0f782-7e06-7dee-811f-0a860ed93bf3"); sys.exit(0)
if cmd == "seed-child":
    data = sys.stdin.read(); open(os.path.join(d, "seeded"), "w").write(data); sys.exit(code("seed.rc"))
sys.exit(0)
""")
        state = f"{tmp}/fake"
        os.makedirs(state)
        saved_store, saved_env = se.STORE, dict(os.environ)
        se.STORE = fake
        os.environ.clear()
        os.environ.update(clean_env(FAKE_STORE=state, HOME=f"{tmp}/home"))
        try:
            e = se.Enrol(dry=False, born_now=True, host_flag="")
            print("the store tool's exit codes")
            err = io.StringIO()
            with redirect_stderr(err):
                got3 = e.id_of("kid")
            check("id-of exit 3 is 'no agent with that login': empty, nothing said", got3 == "" and err.getvalue() == "")
            put(f"{state}/id-of.rc", "0")
            check("id-of exit 0 is the id", e.id_of("kid") == "01a0f782-7e06-7dee-811f-0a860ed93bf3")
            put(f"{state}/id-of.rc", "1")
            err = io.StringIO()
            with redirect_stderr(err):
                got1 = e.id_of("kid")
            check("any other exit fails the call (never 'no agent': that would mint a second id), naming the last line",
                  got1 is None and "could not be read (exit 1): last line on stderr; nothing made" in err.getvalue())
            os.remove(f"{state}/id-of.rc")

            print("the hosts registry")
            e.hosts = put(f"{tmp}/hosts.json", "{ not json")
            err = io.StringIO()
            with redirect_stderr(err):
                ok = e.enrol_one("kid")
            check("a registry that cannot be read: one line, then 'not placed', never a traceback",
                  not ok and "Traceback" not in err.getvalue() and err.getvalue().count("\n") == 2
                  and "kid: not placed" in err.getvalue())
            e.hosts = put(f"{tmp}/hosts.json", json.dumps({"placement": {"kid": "far"}}))
            check("a placed login is found on its host", e.host_of("kid") == "far")
            e.host_flag = "named"
            check("--host names the host for every login", e.host_of("kid") == "named")
            e.host_flag = ""

            print("the bundle pipeline")
            hx = put(f"{tmp}/hx", "#!/usr/bin/env bash\nshift 4\n"
                     "case \"$*\" in *bundle*) echo BUNDLE; exit \"$(cat \"$FAKE_STORE/bundle.rc\" 2>/dev/null || echo 0)\";; esac\n"
                     "exit 0\n", 0o755)
            e.hx = hx
            check("both sides succeed: the bundle reaches seed-child",
                  e.seed("kid", "aid", "url") and open(f"{state}/seeded").read() == "BUNDLE\n")
            put(f"{state}/bundle.rc", "5")
            check("the account's bundle fails: the pipeline fails, as under pipefail", not e.seed("kid", "aid", "url"))
            os.remove(f"{state}/bundle.rc")
            put(f"{state}/seed.rc", "1")
            check("the parent's push of it fails: the pipeline fails", not e.seed("kid", "aid", "url"))
            os.remove(f"{state}/seed.rc")

            print("a step that hangs")
            saved_timeout = se.STEP_TIMEOUT_S
            se.STEP_TIMEOUT_S = 1
            err = io.StringIO()
            try:
                with redirect_stderr(err):
                    rc, _ = se.run(["sleep", "30"], capture=True)
            finally:
                se.STEP_TIMEOUT_S = saved_timeout
            check("is that step's failure, said in one line", rc == 124 and "no answer within 1 s" in err.getvalue())

            print("a dry run")
            gh = put(f"{tmp}/gh", "#!/usr/bin/env bash\necho \"$*\" >> \"$FAKE_STORE/gh.calls\"\n"
                     "[[ \"$1 $2\" == 'repo view' ]] && exit 1\nexit 0\n", 0o755)
            dry = se.Enrol(dry=True, born_now=True, host_flag="far")
            dry.gh, dry.hx = gh, hx
            err = io.StringIO()
            with redirect_stderr(err):
                ok = dry.enrol_one("kid")
            calls = open(f"{state}/gh.calls").read()
            check("says what it would make and makes nothing",
                  ok and "would: gh repo create gzapi-org/agent-fabric-secrets-01a0f782" in err.getvalue()
                  and "would: on far as kid: store init --agent-id" in err.getvalue() and "repo create" not in calls)
            with redirect_stderr(io.StringIO()):
                check("this login is never enrolled as a child", not dry.enrol_one(dry.me))

            print("a whole run, on fakes")
            remotes = f"{tmp}/remotes"
            os.makedirs(remotes)
            bare = f"{remotes}/agent-fabric-secrets-01a0f782-7e06-7dee-811f-0a860ed93bf3.git"
            subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare], check=True, timeout=30)
            seed = f"{tmp}/seed"
            subprocess.run(["git", "init", "-q", "-b", "main", seed], check=True, timeout=30)
            subprocess.run(["git", "-C", seed, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                            "commit", "-q", "--allow-empty", "-m", "store"], check=True, timeout=30)
            subprocess.run(["git", "-C", seed, "push", "-q", bare, "main"], check=True, timeout=30)
            os.environ["AGENT_FABRIC_SECRETS_REMOTE_BASE"] = remotes
            # The host executor runs the account's store as a fake that
            # answers a key (or garbage), and counts what it was asked.
            put(f"{tmp}/hx2", "#!/usr/bin/env bash\nshift 4\necho \"$*\" >> \"$FAKE_STORE/hx.calls\"\n"
                "case \"$*\" in *export-key*) cat \"$FAKE_STORE/key\";; *bundle*) echo BUNDLE;; "
                "*'store id'*) exit 3;; esac\nexit 0\n", 0o755)
            put(f"{state}/key", "-----BEGIN PGP PUBLIC KEY BLOCK-----\nx\n-----END PGP PUBLIC KEY BLOCK-----\n")
            put(f"{tmp}/gh2", "#!/usr/bin/env bash\necho \"$*\" >> \"$FAKE_STORE/gh2.calls\"\n"
                "case \"$1 $2\" in 'repo view') [[ -e \"$FAKE_STORE/exists\" ]];; "
                "'repo create') [[ ! -e \"$FAKE_STORE/create-fails\" ]];; esac\n", 0o755)

            def whole(logins, *, born_now=True, dry=False):
                for f in ("hx.calls", "gh2.calls", "seeded"):
                    if os.path.exists(f"{state}/{f}"):
                        os.remove(f"{state}/{f}")
                run = se.Enrol(dry=dry, born_now=born_now, host_flag="far")
                run.gh, run.hx = f"{tmp}/gh2", f"{tmp}/hx2"
                err = io.StringIO()
                try:
                    with redirect_stderr(err):
                        rc = run.enrol(logins)
                except se.Refused as exc:
                    rc = f"refused: {exc}"
                read = lambda f: open(f"{state}/{f}").read() if os.path.exists(f"{state}/{f}") else ""
                return rc, err.getvalue(), read("hx.calls"), read("gh2.calls"), read("seeded")

            rc, err, hx_calls, gh_calls, seeded = whole(["kid"])
            check("--born-now: the first commit goes as a bundle through the parent, never a push from the account",
                  rc == 0 and seeded == "BUNDLE\n" and "store bundle" in hx_calls and "store push" not in hx_calls, err)
            check("…the repository is made when gh cannot see it, and the run ends saying what to commit",
                  "repo create" in gh_calls and err.rstrip().endswith("commit identities/keys/ (the certified keys and lineage.json)"))
            put(f"{state}/exists", "")
            rc, err, hx_calls, gh_calls, seeded = whole(["kid"], born_now=False)
            check("without it, the account pushes; an existing repository is not made again",
                  rc == 0 and "store push" in hx_calls and "store bundle" not in hx_calls and "repo create" not in gh_calls, err)
            put(f"{state}/key", "a banner, not a key\n")
            rc, err, *_ = whole(["kid"])
            check("a public key that does not come back as one is refused", rc == 1 and "its public key did not come back" in err)
            put(f"{state}/key", "-----BEGIN PGP PUBLIC KEY BLOCK-----\nx\n-----END PGP PUBLIC KEY BLOCK-----\n")
            rc, err, hx_calls, *_ = whole([se.Enrol(dry=False, born_now=False, host_flag="").me, "kid"])
            check("one login failing does not stop the next; the run fails",
                  rc == 1 and "that is this login" in err and "kid: agent" in err, err)
            os.remove(f"{state}/exists")
            put(f"{state}/create-fails", "")
            rc, err, hx_calls, *_ = whole(["kid", "kid2"])
            check("a repository that cannot be made stops the whole run, before anything is asked of the account",
                  rc == "refused: could not create gzapi-org/agent-fabric-secrets-01a0f782-7e06-7dee-811f-0a860ed93bf3 "
                       "(the parent's gh must be able to create a private repository in gzapi-org)" and "init" not in hx_calls,
                  str(rc))
            os.remove(f"{state}/create-fails")
            rc, err, hx_calls, gh_calls, _ = whole(["kid"], dry=True)
            check("a dry run does not say to commit, and asks nothing of the account",
                  rc == 0 and "commit identities/keys/" not in err and "init" not in hx_calls)
            rn = se.Enrol(dry=False, born_now=False, host_flag="")
            rn.gh = f"{tmp}/gh2"
            try:
                with redirect_stderr(io.StringIO()):
                    rn.rename("ghost", "kiddo")
                check("renaming a login no agent holds is refused before anything changes", False)
            except se.Refused as exc:
                check("renaming a login no agent holds is refused before anything changes, by name",
                      str(exc) == "ghost: no agent with that login in identities/keys/lineage.json")
            put(f"{state}/id-of.rc", "0")
            rn = se.Enrol(dry=True, born_now=False, host_flag="")
            rn.gh = f"{tmp}/gh2"
            err = io.StringIO()
            with redirect_stderr(err):
                rc = rn.rename("kid", "kiddo")
            check("a rename's dry run says it and changes nothing",
                  rc == 0 and "would: agent 01a0f782-7e06-7dee-811f-0a860ed93bf3: login kid -> kiddo" in err.getvalue()
                  and "repo edit" not in (open(f"{state}/gh2.calls").read() if os.path.exists(f"{state}/gh2.calls") else ""))
            os.remove(f"{state}/id-of.rc")
        finally:
            se.STORE = saved_store
            os.environ.clear()
            os.environ.update(saved_env)

        print("the shim")
        r = subprocess.run(["bash", SHIM, "--help"], capture_output=True, text=True, timeout=30,
                           env=clean_env(AGENT_FABRIC_PYTHON=f"{tmp}/no-python"))
        check("no pinned interpreter: exit 127, one line", r.returncode == 127 and r.stderr.count("\n") == 1
              and "python_pin.py install" in r.stderr)

    print("test_store_enroll.py: OK" if not fails else f"test_store_enroll.py: {fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
