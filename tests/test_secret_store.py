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

            # A Claude account's template lives in the parent's own store;
            # assigning puts its token into the child's store (ADR-031).
            TOKEN = "sk-ant-oat01-" + "t" * 20
            p = run(parent, "template-set", "work-account", stdin=TOKEN)
            check("the parent keeps a template in its own store", p.returncode == 0, p.stderr)
            p = run(parent, "templates", "--json")
            tl = json.loads(p.stdout or "[]")
            check("templates names the account by fingerprint only", [t["account"] for t in tl] == ["work-account"]
                  and TOKEN not in p.stdout and len(tl[0]["token_sha256_12"]) == 12, p.stdout + p.stderr)
            p = run(parent, "assign", "work-account", "kid", "--json")
            rows = json.loads(p.stdout or "[]")
            check("assign writes the token into the child's store", p.returncode == 0
                  and rows and rows[0]["status"] == "written" and rows[0]["from"] == "none" and TOKEN not in p.stdout,
                  p.stdout + p.stderr)
            p = run(parent, "assign", "work-account", "kid", "--json")
            check("assigning again is unchanged, and remembers the account", json.loads(p.stdout)[0]["status"] == "unchanged"
                  and json.loads(p.stdout)[0]["from"] == "work-account", p.stdout)
            p = run(parent, "assign", "no-such", "kid")
            check("an unknown template is refused", p.returncode == 1 and "not a template" in p.stderr, p.stderr)

            # The child reads it after a pull, and only in-process.
            subprocess.run(["git", "-C", child_store, "pull", "-q", "origin", "main"], check=True, env=child)
            sys.path.insert(0, os.path.dirname(TOOL))
            got = subprocess.run([sys.executable, "-c",
                                  "import secret_store as s, json; v=s.values(); print(json.dumps({k: len(x) for k, x in v.items()}))"],
                                 cwd=os.path.dirname(TOOL), env=child, capture_output=True, text=True)
            lens = json.loads(got.stdout or "{}")
            check("the child reads it (values() in-process)", lens.get("GH_TOKEN") == len(SECRET)
                  and lens.get("CLAUDE_CODE_OAUTH_TOKEN") == len(TOKEN), got.stderr)
            p = run(child, "set", "AGENT_LOGIN", stdin="kid\n")
            check("the agent sets its own entry", p.returncode == 0 and "set" in p.stdout, p.stderr)
            p = run(child, "names")
            check("names lists names, never values", "AGENT_LOGIN" in p.stdout and "GH_TOKEN" in p.stdout
                  and SECRET not in p.stdout, p.stdout)

            # fabric-secrets sync writes the SAME secrets.env from the store
            # as from Doppler, for the same values (ADR-038 §5 rule 7).
            me = subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
            vals = {"AGENT_LOGIN": me, "AGENT_HOST": "somewhere", "OPENROUTER_API_KEY": "or-x",
                    "GH_TOKEN": SECRET, "CLAUDE_BRIDGE_AUTH_TOKEN": "bridge-x",
                    "CLAUDE_CODE_OAUTH_TOKEN": TOKEN}   # as the assignment above wrote it
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
            subprocess.run(["git", "-C", mirror, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                            "commit", "-qam", "a store re-keyed elsewhere"], check=True, env=parent)
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

            # ── review of #63 ────────────────────────────────────────────
            # F1: a multi-line value (a PEM key) comes back exactly; setting
            # it again is unchanged; an empty value is a value.
            pem = "-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA" + "b" * 60 + "\nCCCC\n-----END OPENSSH PRIVATE KEY-----\n"
            run(child, "set", "SSH_PRIVATE_KEY", stdin=pem + "\n")   # stdin's own newline is dropped, the PEM's kept
            got = subprocess.run([sys.executable, "-c", "import secret_store as s, json, hashlib; v=s.values();"
                                  "print(json.dumps({k: hashlib.sha256(x.encode()).hexdigest() for k, x in v.items()}))"],
                                 cwd=os.path.dirname(TOOL), env=child, capture_output=True, text=True)
            import hashlib
            hashes = json.loads(got.stdout or "{}")
            check("F1: a multi-line value comes back exactly", hashes.get("SSH_PRIVATE_KEY") == hashlib.sha256(pem.encode()).hexdigest(),
                  got.stderr)
            p = run(child, "set", "SSH_PRIVATE_KEY", stdin=pem + "\n")
            check("F1: setting the same multi-line value again is unchanged", "unchanged" in p.stdout, p.stdout + p.stderr)
            p = run(child, "set", "EMPTY_ONE", stdin="")
            check("F1: an empty value is stored", p.returncode == 0 and "EMPTY_ONE" in run(child, "names").stdout, p.stderr)

            # F4: the agent's own write reaches the remote, and a parent's put
            # afterwards merges with it; the child then reads both.
            remote_names = lambda: subprocess.run(["git", "--git-dir", remote, "ls-tree", "-r", "--name-only", "main"],
                                                  capture_output=True, text=True).stdout
            check("F4: the agent's own set is pushed", "env/EMPTY_ONE.gpg" in remote_names(), remote_names())
            with open(os.path.join(mirror, ".gpg-id"), "w") as fh:   # undo the re-key case above
                fh.write(child_fpr + "\n")
            subprocess.run(["git", "-C", mirror, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                            "commit", "-qam", "back to the committed key"], check=True, env=parent)
            p = run(parent, "put", "kid", "PARENT_WROTE", stdin="x")
            check("F4: a parent's put after the agent's own write merges and pushes", p.returncode == 0
                  and "env/PARENT_WROTE.gpg" in remote_names() and "env/EMPTY_ONE.gpg" in remote_names(), p.stderr)
            p = run(child, "set", "AFTER_PARENT", stdin="y")
            check("F4: the agent's next write takes the parent's first", p.returncode == 0
                  and "PARENT_WROTE" in run(child, "names").stdout, p.stderr)
            # A remote that cannot be reached is a failed sync, not a stale one.
            os.rename(remote, remote + ".away")
            r4 = subprocess.run([fsync, "sync", "--json"], env=dop, capture_output=True, text=True)
            os.rename(remote + ".away", remote)
            check("F4: a store that cannot be brought up to its remote fails the sync", r4.returncode == 1
                  and "store:" in r4.stdout, r4.stdout[-300:])

            # N2: a set retried after a rejected push leaves the remote whole.
            hook = os.path.join(remote, "hooks", "pre-receive")
            with open(hook, "w") as fh:
                fh.write("#!/bin/sh\nexit 1\n")
            os.chmod(hook, 0o755)
            p = run(child, "set", "RETRIED", stdin="r1")
            check("N2: a rejected push is an error", p.returncode == 1, p.stdout + p.stderr)
            os.remove(hook)
            p = run(child, "set", "RETRIED", stdin="r1")
            check("N2: the retry pushes what the failed push left behind", p.returncode == 0
                  and "env/RETRIED.gpg" in remote_names(), p.stdout + p.stderr)

            # N3: digest --source reads THAT source, whatever the account's is,
            # and an unknown one is refused.
            src_file = os.path.join(child["HOME"], ".config", "agent-fabric", "secrets-source")
            open(src_file, "w").write("doppler\n")
            json.dump({"AGENT_LOGIN": me, "GH_TOKEN": "a-doppler-only-value"}, open(os.path.join(tmp, "dp.json"), "w"))
            ds = subprocess.run([fsync, "digest", "--source", "store"], env=dop, capture_output=True, text=True)
            dd = subprocess.run([fsync, "digest", "--source", "doppler"], env=dop, capture_output=True, text=True)
            check("N3: digest --source store reads the store while the account is on doppler",
                  json.loads(ds.stdout)["source"] == "store" and json.loads(dd.stdout)["source"] == "doppler"
                  and json.loads(ds.stdout)["values_sha256"] != json.loads(dd.stdout)["values_sha256"], ds.stdout + dd.stdout)
            bogus = subprocess.run([fsync, "digest", "--source", "elsewhere"], env=dop, capture_output=True, text=True)
            check("N3: an unknown --source is refused", bogus.returncode == 2 and "usage" in bogus.stderr, bogus.stderr)
            open(src_file, "w").write("store\n")

            # The digest: the same hash from the store as sync reports.
            run(child, "set", "AGENT_LOGIN", stdin=me)
            dg = subprocess.run([fsync, "digest", "--source", "store"], env=dop, capture_output=True, text=True)
            sy = subprocess.run([fsync, "sync", "--json"], env=dop, capture_output=True, text=True)
            check("digest --source store is the hash sync applies", dg.returncode == 0
                  and json.loads(dg.stdout)["values_sha256"] == json.loads(sy.stdout)["values_sha256"], dg.stdout + dg.stderr)
            check("…and neither prints a value", SECRET not in dg.stdout + sy.stdout and TOKEN not in dg.stdout + sy.stdout)

            # F8: import-doppler names what it did not import.
            json.dump({"GOOD_NAME": "v", "lower_case": "v", "NOT_A_STRING": 5}, open(os.path.join(tmp, "dp.json"), "w"))
            p = run({**dop, "AGENT_FABRIC_SECRETS_CONFIG": "agents_kid"}, "import-doppler")
            check("F8: import-doppler names what it skipped", p.returncode == 0 and "lower_case" in p.stderr
                  and "NOT_A_STRING" in p.stderr, p.stdout + p.stderr)

            # F2, F3: each key on its own, one root, no cycle.
            kd = os.path.join(fabric, "identities", "keys")
            root_login = [w for w, r in json.load(open(os.path.join(kd, "lineage.json"))).items() if r["parent"] is None][0]
            saved = {f: open(os.path.join(kd, f)).read() for f in os.listdir(kd)}
            def restore():
                for f, t in saved.items():
                    open(os.path.join(kd, f), "w").write(t)
            def verify_says(what: str) -> bool:
                r = run(parent, "verify")
                return r.returncode == 1 and what in r.stdout
            open(os.path.join(kd, "kid.asc"), "w").write(saved[f"{root_login}.asc"])
            open(os.path.join(kd, f"{root_login}.asc"), "w").write(saved["kid.asc"])
            check("F2: swapped key files are refused", verify_says("not the recorded"))
            restore()
            open(os.path.join(kd, "kid.asc"), "w").write(saved["kid.asc"] + saved[f"{root_login}.asc"])
            check("F2: a key file holding a second key is refused", verify_says("not only the recorded one"))
            restore()
            lin = json.loads(saved["lineage.json"])
            for label, mutate, what in (
                    ("F3: two roots", lambda d: d["kid"].update(parent=None), "2 roots"),
                    ("F3: a login as its own parent", lambda d: d["kid"].update(parent="kid"), "is its own parent"),
                    ("F3: a cycle", lambda d: (d["kid"].update(parent=root_login), d[root_login].update(parent="kid")), "loops")):
                d = json.loads(json.dumps(lin))
                mutate(d)
                json.dump(d, open(os.path.join(kd, "lineage.json"), "w"))
                check(label + " is refused", verify_says(what), run(parent, "verify").stdout)
                restore()
            check("…and the untouched keys verify clean again", run(parent, "verify").returncode == 0)
            d = json.loads(saved["lineage.json"])
            d["kid"] = "not an object"
            json.dump(d, open(os.path.join(kd, "lineage.json"), "w"))
            r = run(parent, "verify")
            check("a lineage entry that is not an object is a finding, not a traceback",
                  r.returncode == 1 and "kid is not an object" in r.stdout and "Traceback" not in r.stderr, r.stdout + r.stderr)
            restore()

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
