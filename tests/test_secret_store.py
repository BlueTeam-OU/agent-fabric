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
import re
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "fabric", "secret_store.py")
sys.path.insert(0, os.path.dirname(TOOL))
import secret_store  # noqa: E402 — the id helpers, beside the CLI under test
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

        # From a directory that is no repository, as an account's own may be:
        # backup --verify passed only because the suite ran inside one.
        def run(env: dict, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, TOOL, *args], env=env, input=stdin, cwd=tmp,
                                  capture_output=True, text=True)

        # Two agents, their ids minted from births (ADR-039).
        PID = secret_store.mint_agent_id(secret_store.born_ms_of("2026-01-14 21:27:33.247294044 +0100"))
        KID = secret_store.mint_agent_id(secret_store.born_ms_of("now"))
        try:
            p = run(parent, "init")
            check("init without an agent id is refused", p.returncode == 1 and "no agent id" in p.stderr, p.stderr)
            # The parent's own key is the root of the chain.
            p = run(parent, "init", "--agent-id", PID)
            check("init makes a key and a store", p.returncode == 0 and "(made)" in p.stdout, p.stderr)
            caps = secret_store._key_caps(subprocess.run(["gpg", "--with-colons", "--list-keys"], env=parent,
                                                         capture_output=True, text=True).stdout)
            check("…its primary only certifies, and each use is its own subkey (ADR-038 rule 1)",
                  caps == ("c", {"e", "s", "a"}), repr(caps))
            p2 = run(parent, "init")
            check("init again keeps the key", p2.returncode == 0 and "(made)" not in p2.stdout, p2.stderr)
            subs = [l for l in subprocess.run(["gpg", "--with-colons", "--list-keys"], env=parent,
                                              capture_output=True, text=True).stdout.splitlines() if l.startswith("sub:")]
            check("…and adds nothing to a complete key: still exactly one subkey per use",
                  "subkeys added" not in p2.stdout and len(subs) == 3, p2.stdout + f" {len(subs)} subkeys")
            p = run(parent, "certify", "--root")
            check("the root records its own key, no parent", p.returncode == 0 and "(root)" in p.stdout, p.stderr)

            # The child, on its own "host": its key, its store, its remote.
            p = run(child, "init", "--agent-id", KID, "--remote", remote)
            check("the child makes its own key", p.returncode == 0, p.stderr)
            child_store = child["AGENT_FABRIC_SECRET_STORE"]
            p = run(child, "init", "--agent-id", PID)
            check("an agent id is never replaced", p.returncode == 1 and "never replaced" in p.stderr, p.stderr)
            check("the store records its id", open(os.path.join(child_store, ".agent-id")).read().strip() == KID)
            child_fpr = open(os.path.join(child_store, ".gpg-id")).read().split()[0]
            subprocess.run(["git", "-C", child_store, "push", "-q", "origin", "HEAD:main"], check=True, env=child)
            exported = os.path.join(tmp, "child.asc")
            subprocess.run(["gpg", "--armor", "--export", child_fpr], env=child, check=True,
                           stdout=open(exported, "w"))

            # Verify before certification: a child recorded without its
            # parent's signature is a finding.
            lin = os.path.join(fabric, "identities", "keys", "lineage.json")
            doc = json.load(open(lin))
            check("the root is recorded by its id, with its login and birth",
                  list(doc) == [PID] and doc[PID]["login"] and doc[PID]["born"] == "2026-01-14T20:27:33.247Z", repr(doc))
            doc[KID] = {"login": "kid", "fingerprint": child_fpr, "parent": PID}
            json.dump(doc, open(lin, "w"))
            open(os.path.join(fabric, "identities", "keys", f"{KID}.asc"), "w").write(open(exported).read())
            p = run(parent, "verify")
            check("an uncertified child key is refused", p.returncode == 1 and "not certified by its parent" in p.stdout,
                  p.stdout + p.stderr)

            p = run(parent, "certify", "kid", exported)
            check("the parent certifies the child's key", p.returncode == 0 and child_fpr in p.stdout, p.stderr)
            p = run(parent, "verify")
            check("the certified key passes verify", p.returncode == 0 and "clean" in p.stdout, p.stdout + p.stderr)

            # The parent writes into the child's store through its own
            # clone of the child's remote, and cannot read what it wrote.
            mirror = os.path.join(parent["HOME"], ".local", "share", "agent-fabric", "children", KID)
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
            p = run(parent, "assign", "work-account", KID, "--json")
            byid = json.loads(p.stdout or "[]")
            check("assign by agent id is the same agent: unchanged, and named by its login",
                  p.returncode == 0 and byid and byid[0]["status"] == "unchanged" and byid[0]["login"] == "kid", p.stdout + p.stderr)
            own_env = os.path.join(parent["AGENT_FABRIC_SECRET_STORE"], "env")
            check("…the parent's record is keyed by the agent id, not the login",
                  os.path.exists(os.path.join(own_env, f"CLAUDE_ASSIGNED_{KID.replace('-', '').upper()}.gpg"))
                  and not os.path.exists(os.path.join(own_env, "CLAUDE_ASSIGNED_KID.gpg")), repr(sorted(os.listdir(own_env))))
            p = run(parent, "assign", "work-account", "nobody-here", "--json")
            check("an agent lineage does not know is a failed row, not a traceback",
                  p.returncode == 1 and json.loads(p.stdout)[0]["status"] == "failed", p.stdout + p.stderr)
            p = run(parent, "assign", "no-such", "kid")
            check("an unknown template is refused", p.returncode == 1 and "not a template" in p.stderr, p.stderr)

            # provision (the Doppler enrolment's replacement): the parent
            # fills the child's store with put, reads nothing back, prints
            # no value. Shared names are an allowlist.
            PROV = os.path.join(ROOT, "tools", "fabric", "store_provision.py")
            prov = lambda *a: subprocess.run([sys.executable, PROV, *a], env=parent, cwd=tmp, capture_output=True, text=True)
            rows_of = lambda p: {(r.get("name"), r["status"]) for r in json.loads(p.stdout or "[]")}
            for k, v in (("GH_TOKEN", "parent-gh-token"), ("GIT_USER_NAME", "Fleet Person"), ("SSH_PUBLIC_KEY", "ssh-ed25519 AAAAshared"),
                         ("OPENROUTER_PROVISIONING_KEY", "prov-" + SECRET)):
                run(parent, "set", k, stdin=v)
            p = prov("share", "kid")
            got = rows_of(p)
            check("provision share: the parent's shared names the child lacks are written; one it holds is present",
                  p.returncode == 0 and ("GIT_USER_NAME", "written") in got and ("SSH_PUBLIC_KEY", "written") in got
                  and ("GH_TOKEN", "present") in got and ("SSH_PRIVATE_KEY", "skipped") in got, p.stdout + p.stderr)
            check("…and never a name off the allowlist, nor a value",
                  not os.path.exists(os.path.join(mirror, "env", "OPENROUTER_PROVISIONING_KEY.gpg"))
                  and SECRET not in p.stdout + p.stderr and "Fleet Person" not in p.stdout, p.stdout)
            p = prov("share", "kid")
            check("provision share again: present, nothing written", p.returncode == 0
                  and not any(st == "written" for _, st in rows_of(p)), p.stdout)
            for named in ("OPENROUTER_PROVISIONING_KEY", "OPENROUTER_API_KEY"):
                p = prov("share", "kid", "--name", named)
                check(f"provision share --name {named}: refused, off the allowlist (review of #69, F2)", p.returncode == 1
                      and "not a shared name" in p.stderr and not os.path.exists(os.path.join(mirror, "env", f"{named}.gpg")),
                      p.stdout + p.stderr)
            p = prov("identity", "kid", "--host", "h1")
            check("provision identity writes AGENT_LOGIN and AGENT_HOST", p.returncode == 0
                  and rows_of(p) == {("AGENT_LOGIN", "written"), ("AGENT_HOST", "written")}, p.stdout + p.stderr)
            p = prov("identity", "kid", "--host", "h1")
            check("…and leaves them alone once present", rows_of(p) == {("AGENT_LOGIN", "present"), ("AGENT_HOST", "present")}, p.stdout)

            # issue-key against a local stand-in for OpenRouter: the
            # provisioning key goes in the header, the minted key into the
            # child's store, and a put that fails after the mint deletes it.
            import http.server, threading
            seen = []
            class Keys(http.server.BaseHTTPRequestHandler):
                def log_message(self, *a): pass
                def do_POST(self):
                    seen.append(("POST", self.path, self.headers.get("Authorization")))
                    if os.path.exists(os.path.join(tmp, "break-put")):
                        os.rename(remote, remote + ".away")
                    if os.path.exists(os.path.join(tmp, "refuse-push")):
                        hook = os.path.join(remote, "hooks", "pre-receive")
                        open(hook, "w").write("#!/bin/sh\nexit 1\n")
                        os.chmod(hook, 0o755)
                    data = {} if os.path.exists(os.path.join(tmp, "no-hash")) else {"hash": "h4sh"}
                    body = json.dumps({"key": "sk-or-minted-" + SECRET, "data": data}).encode()
                    self.send_response(201); self.end_headers(); self.wfile.write(body)
                def do_DELETE(self):
                    seen.append(("DELETE", self.path, self.headers.get("Authorization")))
                    self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
            srv = http.server.HTTPServer(("127.0.0.1", 0), Keys)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                base = f"http://127.0.0.1:{srv.server_port}/api/v1"
                ik = lambda *a: subprocess.run([sys.executable, PROV, "issue-key", "openrouter", *a], cwd=tmp, capture_output=True,
                                               text=True, env={**parent, "OPENROUTER_API_BASE": base})
                p = ik("kid")
                check("issue-key: minted with the parent's provisioning key, named after the login, put in the child's store",
                      p.returncode == 0 and rows_of(p) == {("OPENROUTER_API_KEY", "written")}
                      and seen[:1] == [("POST", "/api/v1/keys", "Bearer prov-" + SECRET)]
                      and os.path.exists(os.path.join(mirror, "env", "OPENROUTER_API_KEY.gpg")), p.stdout + p.stderr + repr(seen))
                check("…and prints no value", SECRET not in p.stdout + p.stderr and "sk-or-minted" not in p.stdout)
                p = ik("kid")
                check("issue-key again: present, not minted again", rows_of(p) == {("OPENROUTER_API_KEY", "present")}
                      and len(seen) == 1, p.stdout + repr(seen))
                open(os.path.join(tmp, "break-put"), "w").close()
                p = ik("kid", "--replace")
                os.rename(remote + ".away", remote)
                os.remove(os.path.join(tmp, "break-put"))
                check("issue-key: a put that fails after the mint deletes the key it minted, and says so",
                      p.returncode == 1 and ("DELETE", "/api/v1/keys/h4sh", "Bearer prov-" + SECRET) in seen
                      and "deleted again" in p.stdout, p.stdout + p.stderr + repr(seen))
                # F1: the pull succeeds and the PUSH is refused, after the
                # commit: the mirror must not keep it, or the re-run reads
                # the key as present and the store never gets one.
                subprocess.run(["git", "-C", mirror, "rm", "-q", "env/OPENROUTER_API_KEY.gpg"], env=parent, check=True)
                subprocess.run(["git", "-C", mirror, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                                "commit", "-qm", "drop the key for the push case"], env=parent, check=True)
                subprocess.run(["git", "-C", mirror, "push", "-q", "origin", "HEAD:main"], env=parent, check=True)
                open(os.path.join(tmp, "refuse-push"), "w").close()
                n0 = len(seen)
                p = ik("kid")
                os.remove(os.path.join(tmp, "refuse-push"))
                os.remove(os.path.join(remote, "hooks", "pre-receive"))
                ahead = subprocess.run(["git", "-C", mirror, "rev-list", "--count", "origin/main..HEAD"], env=parent,
                                       capture_output=True, text=True).stdout.strip()
                check("F1: a refused push is undone in the mirror as well as at OpenRouter",
                      p.returncode == 1 and "deleted again" in p.stdout and ahead == "0"
                      and not os.path.exists(os.path.join(mirror, "env", "OPENROUTER_API_KEY.gpg"))
                      and ("DELETE", "/api/v1/keys/h4sh", "Bearer prov-" + SECRET) in seen[n0:], p.stdout + f" ahead={ahead}")
                # M2: the reset after the refused push fails as well (the
                # hook locks the mirror's index): both reasons are said.
                hook = os.path.join(remote, "hooks", "pre-receive")
                open(hook, "w").write(f"#!/bin/sh\ntouch '{mirror}/.git/index.lock'\nexit 1\n")
                os.chmod(hook, 0o755)
                p = run(parent, "put", "kid", "RESET_CASE", stdin="v")
                os.remove(hook)
                os.remove(os.path.join(mirror, ".git", "index.lock"))
                subprocess.run(["git", "-C", mirror, "reset", "-q", "--hard", "origin/main"], env=parent, check=True)
                check("M2: a reset that fails too is said, with the push's reason and the reset's",
                      p.returncode == 1 and "git push" in p.stderr
                      # git's own wording of the lock differs by version (Fedora's last
                      # line names another process, Debian's says to remove the file):
                      # the reset's reason is whatever follows the mirror's path.
                      and re.search(r"could not be reset to its remote \([^()]*children/[^:]+: \S[^)]*\)", p.stderr),
                      p.stderr[-400:])
                p = ik("kid")
                check("F1: …so the re-run mints and writes, never 'present'", p.returncode == 0
                      and rows_of(p) == {("OPENROUTER_API_KEY", "written")}, p.stdout + p.stderr)
                # F4: a key with no handle cannot be deleted, and the row says so.
                open(os.path.join(tmp, "no-hash"), "w").close()
                open(os.path.join(tmp, "break-put"), "w").close()
                p = ik("kid", "--replace")
                os.rename(remote + ".away", remote)
                for f in ("no-hash", "break-put"):
                    os.remove(os.path.join(tmp, f))
                check("F4: an undo that deleted nothing says NOT deleted, never 'deleted again'",
                      p.returncode == 1 and "NOT deleted" in p.stdout and "deleted again" not in p.stdout, p.stdout)
            finally:
                srv.shutdown()
                srv.server_close()

            # The child reads it after a pull, and only in-process.
            subprocess.run(["git", "-C", child_store, "pull", "-q", "origin", "main"], check=True, env=child)
            sys.path.insert(0, os.path.dirname(TOOL))
            got = subprocess.run([sys.executable, "-c",
                                  "import secret_store as s, json; v=s.values(); print(json.dumps({k: len(x) for k, x in v.items()}))"],
                                 cwd=os.path.dirname(TOOL), env=child, capture_output=True, text=True)
            lens = json.loads(got.stdout or "{}")
            check("the child reads it (values() in-process)", lens.get("GH_TOKEN") == len(SECRET)
                  and lens.get("CLAUDE_CODE_OAUTH_TOKEN") == len(TOKEN), got.stderr)
            p = run(child, "set", "OWN_NOTE", stdin="kid\n")
            check("the agent sets its own entry", p.returncode == 0 and "set" in p.stdout, p.stderr)
            p = run(child, "names")
            check("names lists names, never values", "AGENT_LOGIN" in p.stdout and "GH_TOKEN" in p.stdout
                  and SECRET not in p.stdout, p.stdout)

            # fabric-secrets sync applies what the store holds (ADR-038 §5 rule 7).
            me = subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
            vals = {"AGENT_LOGIN": me, "AGENT_HOST": "somewhere", "OPENROUTER_API_KEY": "or-x",
                    "GH_TOKEN": SECRET, "CLAUDE_BRIDGE_AUTH_TOKEN": "bridge-x",
                    "CLAUDE_CODE_OAUTH_TOKEN": TOKEN}   # as the assignment above wrote it
            for k, v in vals.items():
                run(child, "set", k, stdin=v)
            fsync = os.path.join(ROOT, "runtime", "provisioning", "secrets", "fabric-secrets")
            envf = os.path.join(child["HOME"], ".config", "agent-fabric", "secrets.env")
            body = lambda: "".join(l for l in open(envf) if not l.startswith("#"))
            r2 = subprocess.run([fsync, "sync", "--json"], env=child, capture_output=True, text=True)
            from_store = body() if os.path.exists(envf) else ""
            check("sync applies the store's values to secrets.env", r2.returncode in (0, 2)
                  and SECRET in from_store and "export OPENROUTER_API_KEY=or-x" in from_store,
                  f"rc {r2.returncode} {r2.stderr[-200:]}")
            check("sync never prints a value", SECRET not in r2.stdout + r2.stderr)
            check("the report names the store as its source", '"source": "store"' in r2.stdout, r2.stdout[:200])
            run(child, "set", "AGENT_LOGIN", stdin="someone-else")
            r3 = subprocess.run([fsync, "sync"], env=child, capture_output=True, text=True)
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
            r4 = subprocess.run([fsync, "sync", "--json"], env=child, capture_output=True, text=True)
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

            # F7: put pulls BEFORE it compares keys. Another clone pushes a
            # re-key; the parent's mirror has not pulled it yet.
            other = os.path.join(tmp, "other-clone")
            subprocess.run(["git", "clone", "-q", remote, other], check=True, env=parent)
            open(os.path.join(other, ".gpg-id"), "w").write("0" * 40 + "\n")
            g = ["git", "-C", other, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
            subprocess.run(g + ["commit", "-qam", "re-keyed elsewhere"], check=True, env=parent)
            subprocess.run(g + ["push", "-q", "origin", "HEAD:main"], check=True, env=parent)
            p = run(parent, "put", "kid", "AFTER_REKEY", stdin="z")
            check("F7: a re-key pushed elsewhere is seen before the key check, and the put is refused",
                  p.returncode == 1 and "another key" in p.stderr, p.stdout + p.stderr)
            open(os.path.join(other, ".gpg-id"), "w").write(child_fpr + "\n")
            subprocess.run(g + ["commit", "-qam", "back"], check=True, env=parent)
            subprocess.run(g + ["push", "-q", "origin", "HEAD:main"], check=True, env=parent)
            subprocess.run(["git", "-C", mirror, "pull", "-q", "--rebase", "origin", "main"], env=parent, capture_output=True)

            # The report's values_sha256: the same hash for the same store,
            # and never a value beside it.
            run(child, "set", "AGENT_LOGIN", stdin=me)
            sy = subprocess.run([fsync, "sync", "--json"], env=child, capture_output=True, text=True)
            sy2 = subprocess.run([fsync, "sync", "--json"], env=child, capture_output=True, text=True)
            check("two syncs of one store report one values_sha256", sy.returncode in (0, 2)
                  and len(json.loads(sy.stdout)["values_sha256"]) == 64
                  and json.loads(sy.stdout)["values_sha256"] == json.loads(sy2.stdout)["values_sha256"], sy.stdout[-300:])
            check("…and the report prints no value", SECRET not in sy.stdout and TOKEN not in sy.stdout)

            # F2, F3: each key on its own, one root, no cycle.
            kd = os.path.join(fabric, "identities", "keys")
            root_login = PID
            saved = {f: open(os.path.join(kd, f)).read() for f in os.listdir(kd)}
            def restore():
                for f, t in saved.items():
                    open(os.path.join(kd, f), "w").write(t)
            def verify_says(what: str) -> bool:
                r = run(parent, "verify")
                return r.returncode == 1 and what in r.stdout
            open(os.path.join(kd, f"{KID}.asc"), "w").write(saved[f"{root_login}.asc"])
            open(os.path.join(kd, f"{root_login}.asc"), "w").write(saved[f"{KID}.asc"])
            check("F2: swapped key files are refused", verify_says("not the recorded"))
            restore()
            open(os.path.join(kd, f"{KID}.asc"), "w").write(saved[f"{KID}.asc"] + saved[f"{root_login}.asc"])
            check("F2: a key file holding a second key is refused", verify_says("not only the recorded one"))
            restore()
            lin = json.loads(saved["lineage.json"])
            for label, mutate, what in (
                    ("F3: two roots", lambda d: d[KID].update(parent=None), "2 roots"),
                    ("F3: an agent as its own parent", lambda d: d[KID].update(parent=KID), "is its own parent"),
                    ("F3: a cycle", lambda d: (d[KID].update(parent=root_login), d[root_login].update(parent=KID)), "loops"),
                    ("ADR-039: an entry keyed by a login", lambda d: d.update(kid=d.pop(KID)), "kid is not an agent id"),
                    ("ADR-039: two agents with one login", lambda d: d[KID].update(login=d[PID]["login"]), "both have the login"),
                    ("ADR-039: a birth that is not the id's", lambda d: d[KID].update(born="2020-01-01T00:00:00.000Z"), "is not its id's time"),
                    ("ADR-039: an entry with no birth", lambda d: d[KID].pop("born"), "is not its id's time")):
                d = json.loads(json.dumps(lin))
                mutate(d)
                json.dump(d, open(os.path.join(kd, "lineage.json"), "w"))
                check(label + " is refused", verify_says(what), run(parent, "verify").stdout)
                restore()
            check("…and the untouched keys verify clean again", run(parent, "verify").returncode == 0)
            d = json.loads(saved["lineage.json"])
            d[KID] = "not an object"
            json.dump(d, open(os.path.join(kd, "lineage.json"), "w"))
            r = run(parent, "verify")
            check("a lineage entry that is not an object is a finding, not a traceback",
                  r.returncode == 1 and f"{KID} is not an object" in r.stdout and "Traceback" not in r.stderr, r.stdout + r.stderr)
            restore()
            # A committed key whose authentication subkey is dropped: one use
            # missing is a finding, whatever else holds.
            noauth = subprocess.run(["gpg", "--armor", "--export", "--export-filter", "drop-subkey=usage =~ a", child_fpr],
                                    env=parent, capture_output=True, text=True).stdout
            open(os.path.join(kd, f"{KID}.asc"), "w").write(noauth)
            check("ADR-038 rule 1: a committed key without its authentication subkey is refused",
                  verify_says("no authentication subkey"), run(parent, "verify").stdout)
            restore()
            # Review of #64, P3-8: the certification must be on the user id
            # addressed to the agent's id. A key the parent signed before it
            # carried that id holds a parent signature on another user id
            # only, which is not enough.
            late = role("late")
            lg2 = ["gpg", "--batch", "--pinentry-mode", "loopback", "--passphrase", ""]
            subprocess.run(lg2 + ["--quick-gen-key", "late <late@agents.agent-fabric>", "ed25519", "cert", "never"],
                           env=late, check=True, capture_output=True)
            lfp = [l.split(":")[9] for l in subprocess.run(["gpg", "--with-colons", "--list-keys"], env=late,
                   capture_output=True, text=True).stdout.splitlines() if l.startswith("fpr:")][0]
            for use in (("cv25519", "encr"), ("ed25519", "sign"), ("ed25519", "auth")):
                subprocess.run(lg2 + ["--quick-add-key", lfp, *use, "never"], env=late, check=True, capture_output=True)
            before = subprocess.run(["gpg", "--armor", "--export", lfp], env=late, capture_output=True).stdout
            subprocess.run(["gpg", "--batch", "--import"], input=before, env=parent, capture_output=True)
            pfp = open(os.path.join(parent["AGENT_FABRIC_SECRET_STORE"], ".gpg-id")).read().split()[0]
            subprocess.run(lg2 + ["--default-key", pfp, "--quick-sign-key", lfp], env=parent, check=True, capture_output=True)
            LATE = secret_store.mint_agent_id(secret_store.born_ms_of("now"))
            subprocess.run(lg2 + ["--quick-add-uid", lfp, f"late <{LATE}@agents.agent-fabric>"], env=late, check=True, capture_output=True)
            after = subprocess.run(["gpg", "--armor", "--export", lfp], env=late, capture_output=True).stdout
            subprocess.run(["gpg", "--batch", "--import"], input=after, env=parent, capture_output=True)
            open(os.path.join(kd, f"{LATE}.asc"), "wb").write(
                subprocess.run(["gpg", "--armor", "--export", lfp], env=parent, capture_output=True).stdout)
            d = json.loads(saved["lineage.json"])
            d[LATE] = {"login": "late", "born": secret_store.born_of(LATE), "fingerprint": lfp, "parent": PID}
            json.dump(d, open(os.path.join(kd, "lineage.json"), "w"))
            check("P3-8: a parent signature on another user id is not a certification of the agent id",
                  verify_says(f"{LATE}.asc: not certified by its parent"), run(parent, "verify").stdout)
            # An entry whose key carries a different id: no user id addressed to it.
            OTHER = secret_store.mint_agent_id(secret_store.born_ms_of("now"))
            os.rename(os.path.join(kd, f"{LATE}.asc"), os.path.join(kd, f"{OTHER}.asc"))
            d[OTHER] = {**d.pop(LATE), "born": secret_store.born_of(OTHER)}
            json.dump(d, open(os.path.join(kd, "lineage.json"), "w"))
            check("P3-8: a key that carries no user id addressed to its entry's id is refused",
                  verify_says(f"{OTHER}.asc: no valid user id addressed to {OTHER}"), run(parent, "verify").stdout)
            os.remove(os.path.join(kd, f"{OTHER}.asc"))
            # A primary that also authenticates: its use belongs on a subkey.
            PRIM = secret_store.mint_agent_id(secret_store.born_ms_of("now"))
            subprocess.run(lg2 + ["--quick-gen-key", f"prim <{PRIM}@agents.agent-fabric>", "ed25519", "cert,auth", "never"],
                           env=late, check=True, capture_output=True)
            pr = [l.split(":")[9] for l in subprocess.run(["gpg", "--with-colons", "--list-keys", f"<{PRIM}@agents.agent-fabric>"],
                  env=late, capture_output=True, text=True).stdout.splitlines() if l.startswith("fpr:")][0]
            for use in (("cv25519", "encr"), ("ed25519", "sign"), ("ed25519", "auth")):
                subprocess.run(lg2 + ["--quick-add-key", pr, *use, "never"], env=late, check=True, capture_output=True)
            open(os.path.join(kd, f"{PRIM}.asc"), "wb").write(
                subprocess.run(["gpg", "--armor", "--export", pr], env=late, capture_output=True).stdout)
            d = json.loads(saved["lineage.json"])
            d[PRIM] = {"login": "prim", "born": secret_store.born_of(PRIM), "fingerprint": pr, "parent": PID}
            json.dump(d, open(os.path.join(kd, "lineage.json"), "w"))
            check("ADR-038 rule 1: a primary that also authenticates is refused",
                  verify_says(f"{PRIM}.asc: the primary key itself encrypts or authenticates"), run(parent, "verify").stdout)
            os.remove(os.path.join(kd, f"{PRIM}.asc"))
            subprocess.run(["gpgconf", "--homedir", late["GNUPGHOME"], "--kill", "all"], capture_output=True)
            restore()

            # ADR-039: a rename moves one field; the id, key and store stay.
            p = run(parent, "rename", "kid", "kiddo")
            after = json.load(open(os.path.join(kd, "lineage.json")))
            check("rename changes the login and nothing else", p.returncode == 0 and after[KID]["login"] == "kiddo"
                  and after[KID]["fingerprint"] == child_fpr and sorted(os.listdir(kd)) == sorted(saved), p.stdout + p.stderr)
            p = run(parent, "put", "kiddo", "AFTER_RENAME", stdin="r")
            check("…the renamed agent is still written to, by its new login", p.returncode == 0, p.stderr)
            p = run(parent, "put", KID, "BY_ID", stdin="r")
            check("…and by its id", p.returncode == 0, p.stderr)
            check("…and verify stays clean", run(parent, "verify").returncode == 0)
            p = run(parent, "rename", "kiddo", after[PID]["login"])
            check("a rename onto a login another agent has is refused", p.returncode == 1 and "already an agent's" in p.stderr, p.stderr)
            run(parent, "rename", "kiddo", "kid")

            # A key made before ids existed gains the id's user id, same key.
            legacy = role("legacy")
            lg = ["gpg", "--batch", "--pinentry-mode", "loopback", "--passphrase", ""]
            subprocess.run(lg + ["--quick-gen-key", "legacy <legacy@agents.agent-fabric>", "ed25519", "cert,sign", "never"],
                           env=legacy, check=True, capture_output=True)
            lfpr = [l.split(":")[9] for l in subprocess.run(["gpg", "--with-colons", "--list-secret-keys"], env=legacy,
                    capture_output=True, text=True).stdout.splitlines() if l.startswith("fpr:")][0]
            os.makedirs(legacy["AGENT_FABRIC_SECRET_STORE"])
            open(os.path.join(legacy["AGENT_FABRIC_SECRET_STORE"], ".gpg-id"), "w").write(lfpr + "\n")
            LID = secret_store.mint_agent_id(secret_store.born_ms_of("now"))
            p = run(legacy, "init", "--agent-id", LID)
            uids = subprocess.run(["gpg", "--with-colons", "--list-keys", lfpr], env=legacy, capture_output=True, text=True).stdout
            check("a pre-id key keeps its fingerprint and gains the id's user id", p.returncode == 0 and "(made)" not in p.stdout
                  and f"<{LID}@agents.agent-fabric>" in uids and open(os.path.join(legacy["AGENT_FABRIC_SECRET_STORE"], ".gpg-id")).read().strip() == lfpr,
                  p.stdout + p.stderr)
            check("…and the subkey of each use it lacked, said as such", secret_store._key_caps(uids)[1] == {"e", "s", "a"}
                  and "subkeys added: encryption, signing, authentication" in p.stdout, p.stdout + repr(secret_store._key_caps(uids)))
            subprocess.run(["gpgconf", "--homedir", legacy["GNUPGHOME"], "--kill", "all"], capture_output=True)
            # A store with a key and no agent id: the sheet names the key file
            # by the id, so it is refused rather than name one never written.
            noid = role("noid")
            subprocess.run(lg + ["--quick-gen-key", "noid <noid@agents.agent-fabric>", "ed25519", "cert,sign", "never"],
                           env=noid, check=True, capture_output=True)
            nfpr = [l.split(":")[9] for l in subprocess.run(["gpg", "--with-colons", "--list-secret-keys"], env=noid,
                    capture_output=True, text=True).stdout.splitlines() if l.startswith("fpr:")][0]
            os.makedirs(noid["AGENT_FABRIC_SECRET_STORE"])
            open(os.path.join(noid["AGENT_FABRIC_SECRET_STORE"], ".gpg-id"), "w").write(nfpr + "\n")
            if shutil.which("paperkey"):
                p = run(noid, "paper", "--out", os.path.join(tmp, "noid-sheet.txt"))
                check("the recovery sheet is refused without an agent id", p.returncode == 1
                      and "no agent id yet" in p.stderr and not os.path.exists(os.path.join(tmp, "noid-sheet.txt")), p.stderr)
            p = run(noid, "id")
            check("store id: exit 3 when the store has no agent id yet", p.returncode == 3 and not p.stdout, p.stdout + p.stderr)
            subprocess.run(["gpgconf", "--homedir", noid["GNUPGHOME"], "--kill", "all"], capture_output=True)
            p = run(parent, "mint-id", "2026-08-13 21:56:22.653442123 +0200")
            check("mint-id: a UUIDv7 of that birth", p.returncode == 0 and secret_store.AGENT_ID_RE.match(p.stdout.strip())
                  and secret_store.born_of(p.stdout.strip()) == "2026-08-13T19:56:22.653Z", p.stdout + p.stderr)
            check("mint-id refuses what is not a time", run(parent, "mint-id", "-").returncode == 1)

            # Proton Drive (ADR-038 §7): the stores as bundles with a
            # manifest, the key's recovery copy; a fake CLI keeps uploads in
            # a scratch tree mirroring the Drive paths.
            drive = os.path.join(tmp, "drive")
            os.makedirs(os.path.join(drive, "my-files"))
            fake = os.path.join(tmp, "fake-proton-drive")
            with open(fake, "w") as fh:
                fh.write("""#!/usr/bin/env python3
import os, shutil, sys
D = %r
a = [x for x in sys.argv[1:] if x not in ("-t",)]
cmd = a[:2]; rest = a[2:]
loc = lambda p: os.path.join(D, p.lstrip("/"))
open(os.path.join(D, "..", "proton.env"), "a").write(os.environ.get("PROTON_DRIVE_CREDENTIALS_STORE", "") + "\\n")
if cmd == ["filesystem", "list"]:
    # The real CLI's table, never bare paths: code that parsed paths from
    # it passed against a fake that printed them, and failed live.
    rest = [x for x in rest if x not in ("-t", "folder")]
    if not os.path.isdir(loc(rest[0])): sys.exit(1)
    for n in sorted(os.listdir(loc(rest[0]))):
        print(("\U0001f5c2\ufe0f " if os.path.isdir(os.path.join(loc(rest[0]), n)) else "\U0001f4c4 ")
              + " \U0001f451 agent-fabric@proton.me Sep 29 2026 14:37 - " + n)
elif cmd == ["filesystem", "info"]:
    if os.path.exists(os.path.join(D, "..", "no-session")):
        print("Error: session expired, please log in", file=sys.stderr); sys.exit(1)
    sys.exit(0 if os.path.exists(loc(rest[0])) else 1)
elif cmd == ["filesystem", "trash"]:
    os.makedirs(os.path.join(D, "trash"), exist_ok=True)
    shutil.move(loc(rest[0]), os.path.join(D, "trash", os.path.basename(rest[0])))
elif cmd == ["filesystem", "delete"]:
    if not rest[0].startswith("/trash/"): sys.exit(4)
    os.remove(loc(rest[0]))
elif cmd == ["filesystem", "create-folder"]:
    os.makedirs(os.path.join(loc(rest[0]), rest[1]))
elif cmd == ["filesystem", "upload"]:
    if os.path.exists(os.path.join(D, "..", "fail-upload")):
        print("Error: upload failed", file=sys.stderr); sys.exit(1)
    # The real CLI's strategies; an unknown one is refused, as it refuses it.
    if "-f" in rest and rest[rest.index("-f") + 1] not in ("create-new-revision", "rename", "replace", "skip"): sys.exit(3)
    rest = [x for x in rest if x not in ("-f", "create-new-revision")]
    shutil.copy(rest[0], os.path.join(loc(rest[1]), os.path.basename(rest[0])))
elif cmd == ["filesystem", "download"]:
    if "-f" in rest and rest[rest.index("-f") + 1] not in ("rename", "remove", "skip"): sys.exit(3)
    rest = [x for x in rest if x not in ("-f", "remove")]
    shutil.copy(loc(rest[0]), os.path.join(rest[1], os.path.basename(rest[0])))
else:
    sys.exit(9)
""" % drive)
            os.chmod(fake, 0o755)
            penv = {**parent, "PROTON_DRIVE_BIN": fake}
            p = run(penv, "backup")
            up = os.path.join(drive, "my-files", "agent-fabric", "secrets")
            files = sorted(os.listdir(up)) if os.path.isdir(up) else []
            check("backup uploads a bundle of its own store and of each child mirror, and a manifest",
                  p.returncode == 0 and "manifest.json" in files and f"agent-fabric-secrets-{KID}.bundle" in files
                  and len([f for f in files if f.endswith(".bundle")]) == 2, p.stdout + p.stderr + repr(files))
            man = json.load(open(os.path.join(up, "manifest.json"))) if "manifest.json" in files else {}
            check("…the manifest names each bundle's sha256 and head", set(man.get("stores", {})) >= {KID} and man["stores"][KID].get("login") == "kid"
                  and all(len(r["sha256"]) == 64 and len(r["head"]) == 40 for r in man.get("stores", {}).values()), repr(man)[:300])
            check("…with the CLI's session read from pass over this store",
                  set(open(os.path.join(tmp, "proton.env")).read().split()) == {"pass"})
            p = run(penv, "backup")
            check("a second backup, into folders that exist, succeeds", p.returncode == 0, p.stdout + p.stderr)
            p = run(penv, "backup", "--verify")
            check("backup --verify: every bundle matches its manifest", p.returncode == 0 and "matches" in p.stdout, p.stdout + p.stderr)
            with open(os.path.join(up, f"agent-fabric-secrets-{KID}.bundle"), "ab") as fh:
                fh.write(b"tampered")
            p = run(penv, "backup", "--verify")
            check("backup --verify catches a bundle that is not the manifest's", p.returncode == 1
                  and f"agent-fabric-secrets-{KID}.bundle: its sha256 is not the manifest's" in p.stdout, p.stdout + p.stderr)
            # Option B: the owner's recovery key. Made here without a
            # prompt (a passphrase on the command line, test only); in use
            # it is `recovery-key init`, in the owner's terminal.
            rhome = os.path.join(tmp, "recovery-gnupg")
            os.makedirs(rhome, mode=0o700)
            RPASS = "correct horse battery staple"
            rg = ["gpg", "--homedir", rhome, "--batch", "--pinentry-mode", "loopback", "--passphrase", RPASS]
            subprocess.run(rg + ["--quick-gen-key", "agent-fabric recovery <recovery@agents.agent-fabric>", "ed25519", "cert", "never"],
                           check=True, capture_output=True)
            rfpr = [l.split(":")[9] for l in subprocess.run(["gpg", "--homedir", rhome, "--with-colons", "--list-keys"],
                    capture_output=True, text=True).stdout.splitlines() if l.startswith("fpr:")][0]
            subprocess.run(rg + ["--quick-add-key", rfpr, "cv25519", "encr", "never"], check=True, capture_output=True)
            with open(os.path.join(fabric, "identities", "recovery.asc"), "w") as fh:
                fh.write(subprocess.run(["gpg", "--homedir", rhome, "--armor", "--export", rfpr], capture_output=True, text=True).stdout)
            if shutil.which("paperkey"):
                p = run({**penv, "CLAUDECODE": "1"}, "recovery-copy")
                own = parent["AGENT_FABRIC_SECRET_STORE"]
                copy = os.path.join(own, "recovery", f"{PID}.key.gpg")
                check("recovery-copy writes the copy into the store, inside a model session, printing a path only",
                      p.returncode == 0 and os.path.exists(copy) and "written" in p.stdout and "BEGIN" not in p.stdout
                      and len(p.stdout) < 250, p.stdout + p.stderr)
                opened = subprocess.run(rg + ["--decrypt", copy], capture_output=True, text=True)
                # The content, not words a template would carry anyway: an
                # f-string lost once left "{sheet}" in place of the key, and
                # "REVOCATION" still matched the literal "{revocation}".
                check("…only the recovery key opens it, and it is the key and its revocation",
                      opened.returncode == 0 and "Secret portions of key" in opened.stdout
                      and "BEGIN PGP PUBLIC KEY BLOCK" in opened.stdout and "{sheet}" not in opened.stdout
                      and "{revocation}" not in opened.stdout, opened.stderr[-200:])
                mine = subprocess.run(["gpg", "--batch", "--decrypt", copy], env=parent, capture_output=True, text=True)
                check("…and not even the agent that wrote it can read it back", mine.returncode != 0 and "fingerprint" not in mine.stdout)
                p = run(penv, "recovery-copy")
                check("recovery-copy again is unchanged", p.returncode == 0 and "unchanged" in p.stdout, p.stdout + p.stderr)
                p = run(penv, "backup")
                kf = os.path.join(drive, "my-files", "agent-fabric", "keys")
                check("backup carries each store's encrypted copy to keys/", p.returncode == 0
                      and f"{PID}.key.gpg" in (os.listdir(kf) if os.path.isdir(kf) else []), p.stdout + p.stderr)
                p = run(penv, "backup", "--verify")
                check("…and --verify checks each copy there against the manifest", p.returncode == 0, p.stdout + p.stderr)
                with open(os.path.join(kf, f"{PID}.key.gpg"), "ab") as fh:
                    fh.write(b"truncated or replaced")
                p = run(penv, "backup", "--verify")
                check("…a copy in keys/ that is not the manifest's is a finding", p.returncode == 1
                      and f"keys/{PID}.key.gpg: its sha256 is not the manifest's" in p.stdout, p.stdout + p.stderr)
                os.remove(os.path.join(kf, f"{PID}.key.gpg"))
                p = run(penv, "backup", "--verify")
                check("…a copy missing from keys/ is a finding", p.returncode == 1
                      and f"keys/{PID}.key.gpg: could not be downloaded" in p.stdout, p.stdout + p.stderr)
                p = run(penv, "backup")   # the copy put back whole for what follows
            else:
                check("paperkey is installed where this suite runs", False, "paperkey missing")
            p = run({**penv, "CLAUDECODE": "1"}, "recovery-key", "init")
            check("recovery-key init refuses inside a model session", p.returncode == 1 and "model session" in p.stderr, p.stderr)
            p = run(penv, "recovery-key", "init")
            check("recovery-key init refuses without a terminal for the passphrase", p.returncode == 1
                  and "not a terminal" in p.stderr, p.stderr)
            subprocess.run(["gpgconf", "--homedir", rhome, "--kill", "all"], capture_output=True)
            # What init makes, without its terminal: the key the owner's
            # passphrase protects, checked by the agent's own KEYINFO.
            mk = os.path.join(tmp, "recovery-made")
            os.makedirs(mk, mode=0o700)
            made = subprocess.run([sys.executable, "-c", (
                "import json, sys; sys.path.insert(0, sys.argv[1]); import secret_store as s; "
                "f, pub, priv = s._make_recovery_key(sys.argv[2], sys.argv[3]); "
                "print(json.dumps({'fpr': f, 'pub': 'BEGIN PGP PUBLIC KEY BLOCK' in pub, 'priv': 'BEGIN PGP PRIVATE KEY BLOCK' in priv}))"),
                os.path.join(ROOT, "tools", "fabric"), mk, RPASS], capture_output=True, text=True, env=parent)
            out = json.loads(made.stdout or "{}")
            mk0 = os.path.join(tmp, "recovery-unprotected")
            os.makedirs(mk0, mode=0o700)
            bare = subprocess.run([sys.executable, "-c", (
                "import sys; sys.path.insert(0, sys.argv[1]); import secret_store as s\n"
                "try:\n    s._make_recovery_key(sys.argv[2], ''); print('made')\n"
                "except s.StoreError as e:\n    print('refused:', e)\n"),
                os.path.join(ROOT, "tools", "fabric"), mk0], capture_output=True, text=True, env=parent)
            subprocess.run(["gpgconf", "--homedir", mk0, "--kill", "all"], capture_output=True)
            check("P3-8: a recovery key with no passphrase is refused before anything is published",
                  bare.stdout.startswith("refused:") and "not protected" in bare.stdout, bare.stdout + bare.stderr[-200:])
            check("recovery key: both halves made, every secret part protected", made.returncode == 0
                  and out.get("pub") and out.get("priv") and len(out.get("fpr", "")) == 40, made.stderr[-300:])
            if made.returncode == 0:
                sealed = subprocess.run(["gpg", "--homedir", mk, "--batch", "--trust-model", "always", "--armor",
                                         "--encrypt", "-r", out["fpr"]], input="probe", capture_output=True, text=True).stdout
                subprocess.run(["gpgconf", "--homedir", mk, "--kill", "all"], capture_output=True)
                wrong = subprocess.run(["gpg", "--homedir", mk, "--batch", "--pinentry-mode", "loopback", "--passphrase",
                                        "not the passphrase", "--decrypt"], input=sealed, capture_output=True, text=True)
                right = subprocess.run(["gpg", "--homedir", mk, "--batch", "--pinentry-mode", "loopback", "--passphrase",
                                        RPASS, "--decrypt"], input=sealed, capture_output=True, text=True)
                check("…it opens with the passphrase and not without it",
                      wrong.returncode != 0 and right.returncode == 0 and right.stdout == "probe", wrong.stderr[-200:])
            subprocess.run(["gpgconf", "--homedir", mk, "--kill", "all"], capture_output=True)

            # Rotation (review of #64, P2): the new key goes up beside the
            # old one before recovery.asc names it, and the old one goes
            # only after; a failed upload leaves the old key whole.
            rotate = (
                "import json, sys; sys.path.insert(0, sys.argv[1]); import secret_store as s\n"
                "s._read_recovery_passphrase = lambda: sys.argv[2]\n"
                "sys.stdin = type('T', (), {'isatty': lambda self: True})()\n"
                "try:\n    r = s.recovery_key_init(force=True); print(json.dumps(r))\n"
                "except s.StoreError as e:\n    print(json.dumps({'error': str(e)}))\n")
            rot = lambda: json.loads(subprocess.run([sys.executable, "-c", rotate, os.path.join(ROOT, "tools", "fabric"), RPASS],
                                                    env=penv, capture_output=True, text=True).stdout or "{}")
            pubf = os.path.join(fabric, "identities", "recovery.asc")
            fpr_of = lambda: secret_store._key_file_fingerprint(pubf)
            kdrive = os.path.join(drive, "my-files", "agent-fabric", "keys")
            first = rot()
            check("recovery-key init: the key goes up named by its fingerprint, then recovery.asc names it",
                  first.get("fingerprint") == fpr_of() and os.path.exists(os.path.join(kdrive, f"recovery-key-{fpr_of()[-16:]}.asc")),
                  repr(first))
            open(os.path.join(tmp, "fail-upload"), "w").close()
            failed = rot()
            os.remove(os.path.join(tmp, "fail-upload"))
            check("…a rotation whose upload fails leaves recovery.asc and the old key in Proton as they were",
                  "error" in failed and fpr_of() == first.get("fingerprint")
                  and os.path.exists(os.path.join(kdrive, f"recovery-key-{first['fingerprint'][-16:]}.asc")), repr(failed))
            second = rot()
            check("…a rotation that succeeds names the new key, and deletes the old one from Proton",
                  second.get("fingerprint") == fpr_of() != first.get("fingerprint")
                  and os.path.exists(os.path.join(kdrive, f"recovery-key-{second['fingerprint'][-16:]}.asc"))
                  and not os.path.exists(os.path.join(kdrive, f"recovery-key-{first['fingerprint'][-16:]}.asc"))
                  and not os.listdir(os.path.join(drive, "trash")), repr(second))
            # A lapsed session is said in the CLI's words, never a traceback.
            open(os.path.join(tmp, "no-session"), "w").close()
            p = run(penv, "backup")
            os.remove(os.path.join(tmp, "no-session"))
            check("a lapsed Proton session: the CLI's error and the sign-in hint, no traceback",
                  p.returncode == 1 and "session expired" in p.stderr and "auth login" in p.stderr
                  and "Traceback" not in p.stderr, p.stderr[-300:])

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
