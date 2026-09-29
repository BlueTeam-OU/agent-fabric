#!/usr/bin/env python3
"""tools/fabric/secret_store.py (agent-fabric ADR-038): an agent's own
encrypted store, its parent writing without reading, lineage, and the
owner's sheet refused inside a model session.

Parent and child are two scratch homes with their own keyrings and
stores, sharing nothing but a bare git remote and a scratch fabric tree:
no step may rely on the two living on one host (§5 rules 4–5).

Each keyring sits OUTSIDE its scratch HOME. gpg treats a GNUPGHOME equal
to $HOME/.gnupg as the default home and uses the user's default
gpg-agent socket, the real keyring's agent. A test built that way once
wrote its keys into the running account's own keyring, and let the
"parent" decrypt the "child's" entry through the shared agent. The case
asserts both sockets are private, and that the real keyring is left as
it was found."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "fabric", "secret_store.py")
SECRET = "s3cr3t-value-never-printed"


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail[:400]}"))
        fails += not good

    real_keys = os.path.join(os.path.expanduser("~"), ".gnupg", "private-keys-v1.d")
    found = sorted(os.listdir(real_keys)) if os.path.isdir(real_keys) else []
    with tempfile.TemporaryDirectory() as tmp:
        fabric = os.path.join(tmp, "fabric")
        os.makedirs(os.path.join(fabric, "identities", "keys"))
        remote = os.path.join(tmp, "child-remote.git")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", remote], check=True)

        def role(name: str) -> dict:
            h = os.path.join(tmp, name)
            g = os.path.join(tmp, f"{name}-gnupg")   # never $HOME/.gnupg: see the docstring
            os.makedirs(h)
            os.makedirs(g, mode=0o700)
            return {**{k: v for k, v in os.environ.items() if k != "CLAUDECODE"},
                    "HOME": h, "GNUPGHOME": g, "AGENT_FABRIC_ROOT": fabric,
                    "AGENT_FABRIC_SECRET_STORE": os.path.join(h, "store"),
                    "GIT_CONFIG_GLOBAL": os.path.join(h, ".gitconfig")}

        parent, child = role("parent"), role("child")
        sock = lambda env: subprocess.run(["gpgconf", "--list-dirs", "agent-socket"], env=env,
                                          capture_output=True, text=True).stdout.strip()
        default_sock = subprocess.run(["gpgconf", "--list-dirs", "agent-socket"],
                                      env={k: v for k, v in os.environ.items() if k != "GNUPGHOME"},
                                      capture_output=True, text=True).stdout.strip()
        check("each role has its own gpg-agent, not the account's",
              len({sock(parent), sock(child), default_sock}) == 3, f"{sock(parent)} {sock(child)} {default_sock}")

        def run(env: dict, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, TOOL, *args], env=env, input=stdin,
                                  capture_output=True, text=True)

        try:
            # The parent's own key is the root of the chain.
            p = run(parent, "init")
            check("init makes a key and a store", p.returncode == 0 and "(made)" in p.stdout, p.stderr)
            p2 = run(parent, "init")
            check("init again keeps the key", p2.returncode == 0 and "(made)" not in p2.stdout, p2.stderr)
            p = run(parent, "certify", "--root")
            check("the root records its own key, no parent", p.returncode == 0 and "(root)" in p.stdout, p.stderr)

            # The child, on its own "host": its key, its store, its remote.
            p = run(child, "init", "--remote", remote)
            check("the child makes its own key", p.returncode == 0, p.stderr)
            child_store = child["AGENT_FABRIC_SECRET_STORE"]
            child_fpr = open(os.path.join(child_store, ".gpg-id")).read().split()[0]
            subprocess.run(["git", "-C", child_store, "push", "-q", "origin", "HEAD:main"], check=True, env=child)
            exported = os.path.join(tmp, "child.asc")
            subprocess.run(["gpg", "--armor", "--export", child_fpr], env=child, check=True,
                           stdout=open(exported, "w"))

            # Verify before certification: a child recorded without its
            # parent's signature is a finding.
            lin = os.path.join(fabric, "identities", "keys", "lineage.json")
            doc = json.load(open(lin))
            doc["kid"] = {"fingerprint": child_fpr, "parent": list(doc)[0]}
            json.dump(doc, open(lin, "w"))
            open(os.path.join(fabric, "identities", "keys", "kid.asc"), "w").write(open(exported).read())
            p = run(parent, "verify")
            check("an uncertified child key is refused", p.returncode == 1 and "not certified by its parent" in p.stdout,
                  p.stdout + p.stderr)

            p = run(parent, "certify", "kid", exported)
            check("the parent certifies the child's key", p.returncode == 0 and child_fpr in p.stdout, p.stderr)
            p = run(parent, "verify")
            check("the certified key passes verify", p.returncode == 0 and "clean" in p.stdout, p.stdout + p.stderr)

            # The parent writes into the child's store through its own
            # clone of the child's remote, and cannot read what it wrote.
            mirror = os.path.join(parent["HOME"], ".local", "share", "agent-fabric", "children", "kid")
            subprocess.run(["git", "clone", "-q", remote, mirror], check=True, env=parent)
            p = run(parent, "put", "kid", "GH_TOKEN", stdin=SECRET)
            check("the parent writes into the child's store", p.returncode == 0 and "written" in p.stdout, p.stderr)
            dec = subprocess.run(["gpg", "--batch", "--decrypt", os.path.join(mirror, "env", "GH_TOKEN.gpg")],
                                 env=parent, capture_output=True, text=True)
            check("the parent cannot decrypt it", dec.returncode != 0 and SECRET not in dec.stdout,
                  f"rc={dec.returncode} leaked={SECRET in dec.stdout} err={dec.stderr[-300:]}")
            p = run(parent, "put", "kid", "not-a-name", stdin=SECRET)
            check("a name that is not UPPER_SNAKE is refused", p.returncode == 1 and "not a secret name" in p.stderr)

            # The child reads it after a pull, and only in-process.
            subprocess.run(["git", "-C", child_store, "pull", "-q", "origin", "main"], check=True, env=child)
            sys.path.insert(0, os.path.dirname(TOOL))
            got = subprocess.run([sys.executable, "-c",
                                  "import secret_store as s, json; v=s.values(); print(json.dumps({k: len(x) for k, x in v.items()}))"],
                                 cwd=os.path.dirname(TOOL), env=child, capture_output=True, text=True)
            lens = json.loads(got.stdout or "{}")
            check("the child reads it (values() in-process)", lens.get("GH_TOKEN") == len(SECRET), got.stderr)
            p = run(child, "set", "AGENT_LOGIN", stdin="kid\n")
            check("the agent sets its own entry", p.returncode == 0 and "set" in p.stdout, p.stderr)
            p = run(child, "names")
            check("names lists names, never values", "AGENT_LOGIN" in p.stdout and "GH_TOKEN" in p.stdout
                  and SECRET not in p.stdout, p.stdout)

            # fabric-secrets sync writes the SAME secrets.env from the store
            # as from Doppler, for the same values (ADR-038 §5 rule 7).
            me = subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
            vals = {"AGENT_LOGIN": me, "AGENT_HOST": "somewhere", "OPENROUTER_API_KEY": "or-x",
                    "GH_TOKEN": SECRET, "CLAUDE_BRIDGE_AUTH_TOKEN": "bridge-x"}
            for k, v in vals.items():
                run(child, "set", k, stdin=v)
            stub = os.path.join(tmp, "stubbin")
            os.makedirs(stub)
            with open(os.path.join(stub, "doppler"), "w") as fh:
                fh.write("#!/bin/sh\ncase \"$*\" in *download*) cat " + os.path.join(tmp, "dp.json")
                         + ";; *only-names*) echo '{}';; *) exit 0;; esac\n")
            os.chmod(os.path.join(stub, "doppler"), 0o755)
            json.dump(vals, open(os.path.join(tmp, "dp.json"), "w"))
            fsync = os.path.join(ROOT, "runtime", "provisioning", "secrets", "fabric-secrets")
            envf = os.path.join(child["HOME"], ".config", "agent-fabric", "secrets.env")
            body = lambda: "".join(l for l in open(envf) if not l.startswith("#"))
            dop = {**child, "PATH": stub + os.pathsep + child["PATH"]}
            r1 = subprocess.run([fsync, "sync", "--json"], env=dop, capture_output=True, text=True)
            from_doppler = body() if os.path.exists(envf) else None
            os.makedirs(os.path.dirname(envf), exist_ok=True)
            open(os.path.join(os.path.dirname(envf), "secrets-source"), "w").write("store\n")
            r2 = subprocess.run([fsync, "sync", "--json"], env=dop, capture_output=True, text=True)
            from_store = body()
            check("sync from the store writes what sync from Doppler wrote", r1.returncode in (0, 2)
                  and r2.returncode in (0, 2) and from_doppler == from_store and SECRET in from_store,
                  f"rc {r1.returncode}/{r2.returncode} {r2.stderr[-200:]}")
            check("sync never prints a value", SECRET not in r1.stdout + r2.stdout + r1.stderr + r2.stderr)
            check("the report names the store as its source", '"project": "store"' in r2.stdout, r2.stdout[:200])
            # import-doppler: the login's own Doppler config into its store,
            # one commit, nothing printed but names.
            json.dump({**vals, "NEW_NAME": "fresh-x", "DOPPLER_PROJECT": "agent-fabric"}, open(os.path.join(tmp, "dp.json"), "w"))
            p = run({**dop, "AGENT_FABRIC_SECRETS_CONFIG": "agents_kid"}, "import-doppler")
            check("import-doppler copies the config's names, not Doppler's own", p.returncode == 0
                  and "NEW_NAME" in p.stdout and "DOPPLER_PROJECT" not in p.stdout and SECRET not in p.stdout,
                  p.stdout + p.stderr)
            p = run(child, "names")
            check("…and they are entries now", "NEW_NAME" in p.stdout, p.stdout)
            run(child, "set", "AGENT_LOGIN", stdin="someone-else")
            r3 = subprocess.run([fsync, "sync"], env=dop, capture_output=True, text=True)
            check("a store naming another login is refused, nothing applied", r3.returncode == 3
                  and body() == from_store, r3.stdout[-200:])

            # A store encrypted to another key than the committed one is
            # never written into: re-keying is a rotation.
            with open(os.path.join(mirror, ".gpg-id"), "w") as fh:
                fh.write("0" * 40 + "\n")
            p = run(parent, "put", "kid", "OTHER_NAME", stdin=SECRET)
            check("a store whose key disagrees with the committed one is refused", p.returncode == 1
                  and "another key" in p.stderr, p.stderr)

            # The owner's sheet: never inside a model session.
            p = run({**child, "CLAUDECODE": "1"}, "paper")
            check("paper refuses inside a model session", p.returncode == 1 and "model session" in p.stderr
                  and "BEGIN PGP" not in p.stdout, p.stderr)
            p = run(child, "paper")
            check("paper refuses a non-terminal stdout without --out", p.returncode == 1
                  and ("not a terminal" in p.stderr or "paperkey is not installed" in p.stderr), p.stderr)

            everything = "".join(open(os.path.join(dp, f), errors="ignore").read()
                                 for dp, _, fs in os.walk(os.path.join(child_store, ".git")) for f in fs
                                 if f.endswith((".txt", "HEAD", "COMMIT_EDITMSG")))
            check("no value in the store's commit messages", SECRET not in everything)
        finally:
            for r in (parent, child):
                subprocess.run(["gpgconf", "--homedir", r["GNUPGHOME"], "--kill", "all"], capture_output=True)

    left = sorted(os.listdir(real_keys)) if os.path.isdir(real_keys) else []
    check("the account's own keyring is left as it was found", left == found,
          f"{len(set(left) - set(found))} key file(s) added")
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
