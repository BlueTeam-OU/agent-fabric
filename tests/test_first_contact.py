#!/usr/bin/env python3
"""A new account's first contact with its store (agent-fabric ADR-038): it
has no GitHub key yet, since its SSH key reaches it from that store, so its
first commit goes to its parent as a bundle (store-enroll.sh --born-now,
`store bundle | store seed-child`) and the filled store comes back the same
way (`store child-bundle | store take-bundle`). python-dev-01, the first
account made after the stores replaced Doppler, stopped at that push.

Real keyrings and the real store module, as test_store-enroll.sh drives
them: two scratch homes, each keyring OUTSIDE its home (a GNUPGHOME equal to
$HOME/.gnupg shares the real gpg-agent), the account reached only through a
fake host executor, bare repositories standing in for GitHub. The account's
git rewrites every remote to a path that does not exist: it has no key."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENROLL = os.path.join(HERE, "runtime", "provisioning", "secrets", "store-enroll.sh")
STORE = os.path.join(HERE, "tools", "fabric", "secret_store.py")
ACCOUNT_SECRETS = "projects/agent-fabric/bin/fabric-secrets"

# Nothing of the session's or the runner's decides a case.
BASE_ENV = {k: v for k, v in os.environ.items()
            if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "GIT_", "GNUPGHOME")) and k != "CLAUDECODE"}


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f"\n       {str(detail).strip()[:1500]}"))
        fails += not good

    print("first contact: a refused push is reported by git's error, not its advice")
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_secret_store_under_test", STORE)
    st = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(st)
    github = ("ERROR: Repository not found.\nfatal: Could not read from remote repository.\n\n"
              "Please make sure you have the correct access rights\nand the repository exists.\n")
    try:
        st._run(["sh", "-c", 'printf "%s" "$1" >&2; exit 128', "sh", github], label="git push")
        said = ""
    except st.StoreError as e:
        said = str(e)
    check("GitHub's not-found answer names the failure", said == "git push: fatal: Could not read from remote repository.",
          said)
    try:
        st._run(["sh", "-c", "echo 'plain last line' >&2; exit 1"], label="gpg --decrypt")
        said = ""
    except st.StoreError as e:
        said = str(e)
    check("…and a tool with no such line still gives its last one", said == "gpg --decrypt: plain last line", said)

    t = tempfile.mkdtemp(prefix="first-contact-")
    gnupg = {r: os.path.join(t, f"{r}-gnupg") for r in ("parent", "kid")}
    try:
        fab, remotes, binp = os.path.join(t, "fabric"), os.path.join(t, "remotes"), os.path.join(t, "bin")
        for d in (os.path.join(fab, "identities", "keys"), remotes, binp,
                  os.path.join(t, "parent", "projects"), os.path.join(t, "kid", "projects")):
            os.makedirs(d)
        for g in gnupg.values():
            os.makedirs(g, mode=0o700)
        os.symlink(HERE, os.path.join(t, "kid", "projects", "agent-fabric"))
        with open(os.path.join(t, "hosts.json"), "w") as f:
            json.dump({"version": 1, "hosts": {"far-host": {"ssh": "op@far", "operator": "op", "fabric": fab}},
                       "placement": {"kid": "far-host"}}, f)
        # The account has no key: its git sends every remote to nowhere.
        with open(os.path.join(t, "kid", ".gc"), "w") as f:
            f.write(f'[url "file:///nonexistent-no-key/"]\n\tinsteadOf = {remotes}/\n')
        hx = os.path.join(binp, "hostexec")
        with open(hx, "w") as f:
            f.write(f"""#!/usr/bin/env bash
[[ "$1" == far-host && "$2" == --as && "$3" == kid && "$4" == -- ]] || {{ echo "unexpected: $*" >&2; exit 9; }}
shift 4
cd "{t}/kid" && env HOME="{t}/kid" GNUPGHOME="{gnupg['kid']}" AGENT_FABRIC_ROOT="{fab}" GIT_CONFIG_GLOBAL="{t}/kid/.gc" "$@"
""")
        gh = os.path.join(binp, "gh")
        with open(gh, "w") as f:
            f.write(f"""#!/usr/bin/env bash
name="${{3##*/}}"
case "$1 $2" in
  "repo view") [[ -d "{remotes}/$name.git" ]] ;;
  "repo create") git init -q --bare -b main "{remotes}/$name.git" ;;
  *) exit 9 ;;
esac
""")
        for p in (hx, gh):
            os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)
        penv = {**BASE_ENV, "HOME": os.path.join(t, "parent"), "GNUPGHOME": gnupg["parent"], "AGENT_FABRIC_ROOT": fab,
                "GIT_CONFIG_GLOBAL": os.path.join(t, "parent", ".gc"), "AGENT_FABRIC_HOSTS_REGISTRY": os.path.join(t, "hosts.json"),
                "AGENT_FABRIC_HOSTEXEC": hx, "GH": gh, "AGENT_FABRIC_SECRETS_REMOTE_BASE": remotes}

        def parent(*cmd: str, stdin: str | None = None) -> subprocess.CompletedProcess:
            return subprocess.run(list(cmd), env=penv, input=stdin, capture_output=True, text=True, timeout=300, cwd=t)

        def kid(*cmd: str, stdin: str | None = None) -> subprocess.CompletedProcess:
            return subprocess.run([hx, "far-host", "--as", "kid", "--", *cmd], env=BASE_ENV, input=stdin,
                                  capture_output=True, text=True, timeout=300)

        def lineage_id(login: str) -> str:
            with open(os.path.join(fab, "identities", "keys", "lineage.json")) as f:
                return next((a for a, r in json.load(f).items() if r.get("login") == login), "")

        print("first contact: the parent, then the control")
        r = parent(ENROLL, "--self")
        check("the parent's own store", r.returncode == 0, r.stderr)
        pid = lineage_id(subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip())
        own_remote = os.path.join(remotes, f"agent-fabric-secrets-{pid}.git")
        r = kid("git", "ls-remote", own_remote)
        r2 = parent("git", "ls-remote", own_remote)
        check("control: the account reaches no remote, its parent does", r.returncode != 0 and r2.returncode == 0,
              (r.returncode, r2.returncode, r.stderr))

        print("first contact: enrolment")
        r = parent(ENROLL, "kid")
        check("without --born-now the account's own push fails, as python-dev-01's did",
              r.returncode == 1 and "kid: push failed" in r.stderr, r.stderr)
        r = parent(ENROLL, "kid", "--born-now")
        kid_id = lineage_id("kid")
        check("with --born-now the enrolment completes", r.returncode == 0 and bool(kid_id), r.stderr)
        repo = os.path.join(remotes, f"agent-fabric-secrets-{kid_id}.git")
        shown = subprocess.run(["git", "--git-dir", repo, "show", "main:.agent-id"], capture_output=True, text=True)
        check("…its first commit reached its repository through the parent", shown.stdout.strip() == kid_id, shown.stderr)
        mirror = os.path.join(t, "parent", ".local", "share", "agent-fabric", "children", kid_id)
        check("…and the parent holds the mirror", os.path.isdir(os.path.join(mirror, ".git")))
        r = parent(ENROLL, "kid", "--born-now")
        check("a second run converges", r.returncode == 0, r.stderr)

        print("first contact: the filled store comes back as a bundle")
        r = parent("python3", STORE, "put", "kid", "GH_TOKEN", stdin="fixture-not-a-token\n")
        check("the parent writes into the child's store", r.returncode == 0, r.stderr)
        before = kid(ACCOUNT_SECRETS, "store", "names").stdout.split()
        bundle = parent("python3", STORE, "child-bundle", "kid")
        r = kid(ACCOUNT_SECRETS, "store", "take-bundle", stdin=bundle.stdout)
        after = kid(ACCOUNT_SECRETS, "store", "names").stdout.split()
        check("the account takes it with no remote reachable, and holds the entry",
              bundle.returncode == 0 and r.returncode == 0 and "GH_TOKEN" not in before and "GH_TOKEN" in after,
              (bundle.stderr, r.stdout, r.stderr, before, after))
        check("…and the bundle is ciphertext: the value is nowhere in it",
              "fixture-not-a-token" not in bundle.stdout and "BEGIN AGENT-FABRIC STORE BUNDLE" in bundle.stdout)

        print("first contact: what is refused")
        foreign = parent("python3", STORE, "bundle")
        r = kid(ACCOUNT_SECRETS, "store", "take-bundle", stdin=foreign.stdout)
        check("another agent's store is not taken", r.returncode != 0 and "nothing taken" in r.stderr, r.stderr)
        r = kid(ACCOUNT_SECRETS, "store", "take-bundle", stdin="not a bundle\n")
        check("text that is not a bundle is not taken", r.returncode != 0 and "no armour" in r.stderr, r.stderr)
        mine = kid(ACCOUNT_SECRETS, "store", "bundle")
        other = "01a0f782-7e06-7dee-811f-0a860ed93bf3"
        r = parent("python3", STORE, "seed-child", other, "--remote", os.path.join(remotes, "x.git"), stdin=mine.stdout)
        check("a parent refuses a bundle naming another agent than it minted",
              r.returncode != 0 and f"not {other}" in r.stderr and not os.path.exists(os.path.join(remotes, "x.git")), r.stderr)
    finally:
        for g in gnupg.values():
            subprocess.run(["gpgconf", "--homedir", g, "--kill", "all"], capture_output=True)
        shutil.rmtree(t, ignore_errors=True)

    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
