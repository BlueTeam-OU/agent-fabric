#!/usr/bin/env python3
"""runtime/provisioning/secrets/store-enroll.sh: the parent gives an
account its key and store (ADR-038) through the host executor, as it
would on another host. The account is a separate scratch home and keyring
reached only through a fake hostexec, the repositories are bare ones
standing in for GitHub, and the fabric checkout is a scratch copy. Each
keyring is OUTSIDE its home: a GNUPGHOME equal to $HOME/.gnupg is the
account's default and shares the real gpg-agent. Ported from
runtime/provisioning/secrets/test_store-enroll.sh (ADR-040 Wave 6), case
for case. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENROLL = os.path.join(ROOT, "runtime", "provisioning", "secrets", "store-enroll.sh")
STORE = os.path.join(ROOT, "tools", "fabric", "secret_store.py")
LOGIN = pwd.getpwuid(os.geteuid()).pw_name
REAL_KEYS = os.path.expanduser("~/.gnupg/private-keys-v1.d")


def listing(path: str) -> list[str]:
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    before = listing(REAL_KEYS)
    t = tempfile.mkdtemp()
    try:
        fab = f"{t}/fabric"
        for d in (f"{fab}/identities/keys", f"{t}/remotes", f"{t}/bin"):
            os.makedirs(d)
        # The fabric is a checkout: a store's writers are read at its
        # origin/main (ADR-042 rule 2); what enrolment certifies counts once
        # published there, as a merged identities/keys/ PR is.
        fab_git = ["git", "-C", fab, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
        subprocess.run(["git", "init", "-q", "-b", "main", fab], check=True, timeout=30, capture_output=True)

        def publish() -> None:
            for a in (["add", "-A"], ["commit", "-q", "--allow-empty", "-m", "identities"],
                      ["update-ref", "refs/remotes/origin/main", "HEAD"]):
                subprocess.run(fab_git + a, check=True, timeout=30, capture_output=True)
        # The two homes are born apart: an id's time is its home's creation
        # to the millisecond, and two homes made in one millisecond could not
        # tell a child's birth read on its host from one read on the parent.
        for r in ("parent", "kid"):
            os.makedirs(f"{t}/{r}/projects")
            os.makedirs(f"{t}/{r}-gnupg", 0o700)
            time.sleep(0.05)
        os.symlink(ROOT, f"{t}/kid/projects/agent-fabric")   # the account's own checkout, from its home
        calls = f"{t}/calls"

        def put(path: str, text: str, mode: int | None = None) -> None:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            if mode is not None:
                os.chmod(path, mode)

        def read(path: str) -> str:
            try:
                with open(path, encoding="utf-8") as fh:
                    return fh.read()
            except OSError:
                return ""

        put(f"{t}/hosts.json", json.dumps({"version": 1, "hosts": {"far-host": {"ssh": "op@far", "operator": "op",
                                                                             "fabric": fab}},
                                           "placement": {"kid": "far-host"}}) + "\n")
        # The host executor: runs the command as "kid", in kid's home, with
        # kid's keyring.
        put(f"{t}/bin/hostexec", "#!/usr/bin/env bash\n"
            f'echo "hostexec $*" >> "{calls}"\n'
            '[[ "$1" == far-host && "$2" == --as && "$3" == kid && "$4" == -- ]] || { echo "unexpected: $*" >&2; exit 9; }\n'
            "shift 4\n"
            f'[[ -e "{t}/fail-push" && "$*" == *"store push"* ]] && {{ echo "push rejected" >&2; exit 1; }}\n'
            f'[[ -e "{t}/fail-id" && "$*" == *"store id"* ]] && {{ echo "cannot read" >&2; exit 1; }}\n'
            f'[[ -e "{t}/bad-id" && "$*" == *"store id"* ]] && {{ printf \'a banner\\nnot-an-id\\n\'; exit 0; }}\n'
            f'cd "{t}/kid" && env -u CLAUDECODE HOME="{t}/kid" GNUPGHOME="{t}/kid-gnupg" AGENT_FABRIC_ROOT="{fab}" '
            f'GIT_CONFIG_GLOBAL="{t}/kid/.gc" "$@"\n', 0o755)
        # gh: "repo view" fails until "repo create" makes the bare repository.
        put(f"{t}/bin/gh", "#!/usr/bin/env bash\n"
            f'echo "gh $*" >> "{calls}"\n'
            'name="${3##*/}"\n'
            'case "$1 $2" in\n'
            f'  "repo view") [[ -d "{t}/remotes/$name.git" ]] ;;\n'
            f'  "repo create") git init -q --bare -b main "{t}/remotes/$name.git" ;;\n'
            f'  "repo edit") [[ ! -e "{t}/fail-edit" ]] ;;\n'
            "  *) exit 9 ;;\nesac\n", 0o755)
        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_")) and k not in ("GIT_DIR",
                                                                                                     "CLAUDECODE")}
        parent = {**base, "HOME": f"{t}/parent", "GNUPGHOME": f"{t}/parent-gnupg", "AGENT_FABRIC_ROOT": fab,
                  "GIT_CONFIG_GLOBAL": f"{t}/parent/.gc", "AGENT_FABRIC_HOSTS_REGISTRY": f"{t}/hosts.json",
                  "AGENT_FABRIC_HOSTEXEC": f"{t}/bin/hostexec", "GH": f"{t}/bin/gh",
                  "AGENT_FABRIC_SECRETS_REMOTE_BASE": f"{t}/remotes"}

        def P(*argv: str, stdin: str | None = None, env: dict | None = None) -> tuple[int, str]:
            r = subprocess.run(list(argv), env=env or parent, input=stdin, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, timeout=300)
            return r.returncode, r.stdout

        def store(*args: str, stdin: str | None = None) -> tuple[int, str]:
            return P(sys.executable, STORE, *args, stdin=stdin)

        def lid(login: str) -> str:
            try:
                d = json.loads(read(f"{fab}/identities/keys/lineage.json"))
                return next((a for a, r in d.items() if r.get("login") == login), "")
            except (ValueError, AttributeError):
                return ""

        def born_ms(path: str) -> str:
            # An id's time is its birth; here, the home's creation time to the
            # millisecond.
            w = subprocess.run(["stat", "-c", "%w", path], stdout=subprocess.PIPE, text=True, timeout=10).stdout.strip()
            return subprocess.run(["date", "-d", w, "+%s%3N"], stdout=subprocess.PIPE, text=True, timeout=10).stdout.strip()

        def id_ms(agent_id: str) -> str:
            return str(int(agent_id.replace("-", "")[:12], 16)) if agent_id else ""

        def clear_calls() -> None:
            put(calls, "")

        print("store-enroll: the parent first")
        rc, out = P(ENROLL, "kid")
        check("a parent without its own store is refused", rc == 1 and "no store yet" in out, f"rc={rc}\n{out}")
        rc, out = P(ENROLL, "--self")
        pid = lid(LOGIN)
        try:
            first_parent = list(json.loads(read(f"{fab}/identities/keys/lineage.json")).values())[0].get("parent", "x")
        except (ValueError, IndexError, AttributeError):
            first_parent = "x"
        check("--self: the parent's repository, named by its agent id, its store and root key",
              rc == 0 and bool(pid) and os.path.isdir(f"{t}/remotes/agent-fabric-secrets-{pid}.git") and first_parent is None,
              f"rc={rc}\n{out}")
        check("…its id's time is its home's creation time", bool(pid) and id_ms(pid) == born_ms(f"{t}/parent"),
              f"{pid} vs {born_ms(f'{t}/parent')}")
        publish()

        # #65 carried: --self with a malformed .agent-id in its store stops and
        # mints nothing; a lineage that is not JSON stops a child's enrolment
        # rather than reading as "no agent" and minting a second id.
        aid_file = f"{t}/parent/.local/share/agent-fabric/secrets/.agent-id"
        keep = read(aid_file)
        put(aid_file, "not-an-id\n")
        clear_calls()
        rc, out = P(ENROLL, "--self")
        put(aid_file, keep)
        check("--self with a malformed .agent-id: exit 1, nothing made",
              rc == 1 and "agent id could not be read" in out and "repo create" not in read(calls), f"rc={rc}\n{out}")
        lin = f"{fab}/identities/keys/lineage.json"
        keep = read(lin)
        put(lin, "{ not json\n")
        clear_calls()
        rc, out = P(ENROLL, "kid")
        put(lin, keep)
        check("a lineage that cannot be read stops the enrolment before anything is asked or made",
              rc == 1 and "lineage.json could not be read" in out and "repo create" not in read(calls)
              and "hostexec" not in read(calls), f"rc={rc}\n{out}")

        print("store-enroll: an account on another host")
        # A store whose id cannot be read, or answers something that is not
        # one: the enrolment stops before any repository is made for it.
        for f in ("fail-id", "bad-id"):
            put(f"{t}/{f}", "")
            clear_calls()
            rc, out = P(ENROLL, "kid")
            os.remove(f"{t}/{f}")
            check(f"{f}: the enrolment stops, and no repository is made",
                  rc == 1 and "repo create" not in read(calls) and re.search(r"could not be read|is not one", out)
                  is not None, f"rc={rc}\n{out}")
        # Review of #64, P2: a first run that stops after init (its push
        # rejected) leaves the id in the account's store; the re-run takes
        # it, never a new one.
        put(f"{t}/fail-push", "")
        rc, out = P(ENROLL, "kid")
        os.remove(f"{t}/fail-push")
        first_id = read(f"{t}/kid/.local/share/agent-fabric/secrets/.agent-id").strip()
        check("a first run whose push fails stops after init, the id in the account's store",
              rc == 1 and bool(first_id) and "kid: push failed" in out, f"rc={rc}\n{out}")
        rc, out = P(ENROLL, "kid")
        publish()   # the child's keys PR, merged
        check("the child gets its key and store, and is certified",
              rc == 0 and re.search(r"kid: agent [0-9a-f-]{36}, key certified", out) is not None, f"rc={rc}\n{out}")
        check("…every account step went through the host executor to its placed host",
              "hostexec far-host --as kid" in read(calls), read(calls))
        kid = lid("kid")
        check("…the re-run enrols it under the id its store already held", bool(kid) and kid == first_id,
              f"{kid} vs {first_id}")
        check("…its repository's description gives the Linux login and the agent id",
              f"--description agent-fabric secrets. Linux login: kid. Agent id: {kid}." in read(calls),
              "\n".join(ln for ln in read(calls).split("\n") if "repo create" in ln))
        check("…its repository is named by its agent id",
              bool(kid) and os.path.isdir(f"{t}/remotes/agent-fabric-secrets-{kid}.git"), " ".join(listing(f"{t}/remotes")))
        check("…its id's time is ITS home's creation time, read on its host",
              bool(kid) and id_ms(kid) == born_ms(f"{t}/kid"), kid)
        check("…and the parent holds a mirror of the child's store",
              os.path.isdir(f"{t}/parent/.local/share/agent-fabric/children/{kid}/.git"))
        verify = subprocess.run([sys.executable, STORE, "verify"], env={**base, "AGENT_FABRIC_ROOT": fab},
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
        check("…and lineage verifies", verify.returncode == 0, verify.stdout)
        rc, out = P(ENROLL, "kid")
        secs = subprocess.run(["gpg", "--homedir", f"{t}/kid-gnupg", "--list-secret-keys", "--with-colons"],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=60).stdout
        check("a second run keeps the child's one key and its id",
              rc == 0 and sum(1 for ln in secs.split("\n") if ln.startswith("sec")) == 1 and lid("kid") == kid,
              f"rc={rc}\n{out}")
        check("the parent can now write into the child's store", store("put", "kid", "GH_TOKEN", stdin="top secret\n")[0] == 0)
        rc, out = P(ENROLL, "kid")
        check("a re-run after the parent's put takes it and converges, never pushing the account's older head",
              rc == 0 and "GH_TOKEN" in subprocess.run(["git", "--git-dir", f"{t}/remotes/agent-fabric-secrets-{kid}.git", "ls-tree",
                                                         "-r", "--name-only", "main"], stdout=subprocess.PIPE, text=True,
                                                        timeout=60).stdout, f"rc={rc}\n{out}")
        # A mirror that cannot be brought up to date fails the enrolment: a
        # stale mirror read as current is the parent's wrong view of the
        # store (#63's carried items). The second run above is the control.
        mirror = f"{t}/parent/.local/share/agent-fabric/children/{kid}"
        url = subprocess.run(["git", "-C", mirror, "remote", "get-url", "origin"], stdout=subprocess.PIPE,
                             text=True, timeout=60, check=True).stdout.strip()
        subprocess.run(["git", "-C", mirror, "remote", "set-url", "origin", f"{t}/remotes/gone.git"], timeout=60, check=True)
        rc, out = P(ENROLL, "kid")
        subprocess.run(["git", "-C", mirror, "remote", "set-url", "origin", url], timeout=60, check=True)
        check("a mirror that cannot be brought up to date is a failure, not a note",
              rc == 1 and "kid: its mirror could not be brought up to date" in out
              and not re.search(r"kid: agent .*mirrored", out), f"rc={rc}\n{out}")
        rc, out = P(ENROLL, "nobody")
        check("an unplaced login is refused by name", rc == 1 and "nobody: not placed" in out, f"rc={rc}\n{out}")

        # A retried assign pushes the parent's own record that an earlier
        # failed push left behind (the parent's remote rejects one push).
        pr = f"{t}/remotes/agent-fabric-secrets-{pid}.git"
        store("template-set", "work", stdin="sk-ant-oat01-tttttttttttttttttttt\n")
        put(f"{pr}/hooks/pre-receive", "#!/bin/sh\nexit 1\n", 0o755)
        rc, out = store("assign", "work", "kid")
        os.remove(f"{pr}/hooks/pre-receive")
        rc2, out2 = store("assign", "work", "kid")
        tree = subprocess.run(["git", "--git-dir", pr, "ls-tree", "-r", "--name-only", "main"], stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True, timeout=60).stdout
        check("a retried assign pushes the record a failed push left behind",
              f"env/CLAUDE_ASSIGNED_{kid.replace('-', '').upper()}.gpg" in tree.split("\n") and rc == 1 and rc2 == 0,
              f"rc={rc}/{rc2}\n{out}\n{out2}")

        # The default remote is SSH: accounts reach GitHub with their own
        # key, and none has an HTTPS credential helper for a private
        # repository.
        no_base = {k: v for k, v in parent.items() if k not in ("AGENT_FABRIC_SECRETS_REMOTE_BASE", "GIT_CONFIG_GLOBAL")}
        rc, out = P(ENROLL, "kid", "--dry-run", env=no_base)
        check("the default remote is SSH, the scheme every account can push with",
              f"store init --agent-id {kid} --remote git@github.com:gzapi-org/agent-fabric-secrets-{kid}.git" in out, out)

        # A rename: the login, in lineage and in the description; nothing
        # stored moves.
        rc, out = P(ENROLL, "--rename", "kid", "kiddo")
        check("--rename changes the login and the description; the id, key, repository and mirror stay",
              rc == 0 and lid("kiddo") == kid and not lid("kid") and os.path.isdir(f"{t}/remotes/agent-fabric-secrets-{kid}.git")
              and os.path.isfile(f"{fab}/identities/keys/{kid}.asc")
              and os.path.isdir(f"{t}/parent/.local/share/agent-fabric/children/{kid}/.git")
              and f"repo edit gzapi-org/agent-fabric-secrets-{kid} --description agent-fabric secrets. Linux login: kiddo. "
                  f"Agent id: {kid}." in read(calls), f"rc={rc}\n{out}")
        verify = subprocess.run([sys.executable, STORE, "verify"], env={**base, "AGENT_FABRIC_ROOT": fab},
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        check("…the renamed agent is written to by its new login, and verifies",
              store("put", "kiddo", "AFTER_RENAME", stdin="x\n")[0] == 0 and verify.returncode == 0)
        put(f"{t}/fail-edit", "")
        rc, out = P(ENROLL, "--rename", "kiddo", "kid3")
        os.remove(f"{t}/fail-edit")
        check("…a rename whose description edit fails exits 1 and says what is left",
              rc == 1 and "description still names kiddo" in out, f"rc={rc}\n{out}")
    finally:
        for g in (f"{t}/parent-gnupg", f"{t}/kid-gnupg"):
            subprocess.run(["gpgconf", "--homedir", g, "--kill", "all"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=30)
        shutil.rmtree(t, ignore_errors=True)

    check("the account's own keyring is left as it was found", before == listing(REAL_KEYS))
    print(f"\ntest_store_enroll_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
