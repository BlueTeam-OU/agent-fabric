#!/usr/bin/env python3
"""ADR-042: an agent's store applies only commits signed by its writers —
its own key and its recorded parent's, read at the fabric's origin/main —
and refuses anything else, named, recorded and said until repaired.

A parent and a child, each a scratch home with its own keyring (never
$HOME/.gnupg: tests/test_secret_store.py says why), share a bare remote
and a scratch fabric checkout whose origin/main stands for the merged
identities/keys/. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "fabric", "secret_store.py")
SYNC = os.path.join(ROOT, "tools", "fabric", "secrets_sync.py")
sys.path.insert(0, os.path.dirname(TOOL))
import secret_store  # noqa: E402 — the id helpers, beside the CLI under test


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:500]}"))
        fails += not good

    tmp = tempfile.mkdtemp(prefix="store-signing-")
    gnupgs = []
    try:
        fabric = os.path.join(tmp, "fabric")
        os.makedirs(os.path.join(fabric, "identities", "keys"))
        fab_git = ["git", "-C", fabric, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
        subprocess.run(["git", "init", "-q", "-b", "main", fabric], check=True)

        def publish() -> None:
            """What certify wrote, merged: the fabric's origin/main moves."""
            for a in (["add", "-A"], ["commit", "-q", "--allow-empty", "-m", "identities"],
                      ["update-ref", "refs/remotes/origin/main", "HEAD"]):
                subprocess.run(fab_git + a, check=True, capture_output=True)
        remote = os.path.join(tmp, "child-remote.git")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", remote], check=True)

        def role(name: str) -> dict:
            h, g = os.path.join(tmp, name), os.path.join(tmp, f"{name}-gnupg")
            os.makedirs(h)
            os.makedirs(g, mode=0o700)
            gnupgs.append(g)
            return {**{k: v for k, v in os.environ.items() if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "CLAUDE"))},
                    "HOME": h, "GNUPGHOME": g, "AGENT_FABRIC_ROOT": fabric,
                    "AGENT_FABRIC_SECRET_STORE": os.path.join(h, "store"), "GIT_CONFIG_GLOBAL": os.path.join(h, ".gitconfig")}

        parent, child, stranger = role("parent"), role("child"), role("stranger")

        def run(env: dict, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, TOOL, *args], env=env, input=stdin, cwd=tmp, capture_output=True, text=True)

        def git(env: dict, repo: str, *args: str) -> subprocess.CompletedProcess:
            return subprocess.run(["git", "-C", repo, *args], env=env, capture_output=True, text=True)

        PID = secret_store.mint_agent_id(secret_store.born_ms_of("2026-01-14 21:27:33 +0100"))
        KID = secret_store.mint_agent_id(secret_store.born_ms_of("now"))
        cstore, mirror = child["AGENT_FABRIC_SECRET_STORE"], os.path.join(tmp, "parent", ".local", "share", "agent-fabric",
                                                                          "children", KID)

        print("signing: every commit by its writer")
        run(parent, "init", "--agent-id", PID)
        run(parent, "certify", "--root")
        publish()
        p = run(child, "init", "--agent-id", KID, "--remote", remote)
        check("init makes the child's store", p.returncode == 0, p.stderr)
        cfpr = open(os.path.join(cstore, ".gpg-id")).read().split()[0]
        pfpr = open(os.path.join(parent["AGENT_FABRIC_SECRET_STORE"], ".gpg-id")).read().split()[0]
        check("a new store's own first commit is its trusted base",
              git(child, cstore, "config", "--get", "agent-fabric.trustedbase").stdout.strip()
              == git(child, cstore, "rev-parse", "HEAD").stdout.strip())
        git(child, cstore, "push", "-q", "origin", "HEAD:main")
        exported = os.path.join(tmp, "child.asc")
        with open(exported, "w") as fh:
            subprocess.run(["gpg", "--armor", "--export", cfpr], env=child, check=True, stdout=fh)
        p = run(parent, "certify", "kid", exported)
        check("the parent certifies the child", p.returncode == 0, p.stderr)
        publish()

        def signer(env: dict, repo: str, rev: str = "HEAD") -> str:
            """The primary key a commit's signature belongs to, as the fabric's
            main knows the two writers."""
            ring = tempfile.mkdtemp(prefix="ring-", dir=tmp)
            os.chmod(ring, 0o700)
            gnupgs.append(ring)
            for who in (PID, KID):
                subprocess.run(["gpg", "--batch", "--homedir", ring, "--import",
                                os.path.join(fabric, "identities", "keys", f"{who}.asc")], capture_output=True)
            r = subprocess.run(["git", "-C", repo, "verify-commit", "--raw", rev], env={**env, "GNUPGHOME": ring},
                               capture_output=True, text=True)
            valid = [ln.split() for ln in r.stderr.splitlines() if " VALIDSIG " in ln]
            return valid[0][-1] if valid else ""
        subprocess.run(["git", "clone", "-q", remote, mirror], check=True, env=parent, capture_output=True)
        p = run(parent, "put", "kid", "GH_TOKEN", stdin="t1")
        check("a mirror with no trusted base refuses, naming the step that gives it one",
              p.returncode == 1 and "trust-base" in p.stderr, p.stderr)
        p = run(parent, "trust-base", "--store", mirror)
        check("trust-base records the mirror's base at its head", p.returncode == 0, p.stderr)
        p = run(parent, "put", "kid", "GH_TOKEN", stdin="t1")
        check("the parent's put is signed with the parent's own key", p.returncode == 0 and signer(parent, mirror) == pfpr,
              (p.stderr, signer(parent, mirror), pfpr))
        p = run(child, "set", "OWN", stdin="o1")
        check("the agent's set takes the parent's put, verified, and is signed with its own key",
              p.returncode == 0 and signer(child, cstore) == cfpr
              and os.path.exists(os.path.join(cstore, "env", "GH_TOKEN.gpg")), (p.stderr, signer(child, cstore)))
        base_before = git(child, cstore, "config", "--get", "agent-fabric.trustedbase").stdout.strip()
        check("…and the base moved forward to what it verified",
              base_before and git(child, cstore, "merge-base", "--is-ancestor", base_before, "HEAD").returncode == 0
              and base_before != git(child, cstore, "rev-list", "--max-parents=0", "HEAD").stdout.strip())

        print("refusals: unsigned, an outsider, nothing applied, said until repaired")
        other = os.path.join(tmp, "other")
        subprocess.run(["git", "clone", "-q", remote, other], check=True, env=child, capture_output=True)
        g = ["-c", "user.name=t", "-c", "user.email=t@t"]
        with open(os.path.join(other, "env", "FORGED.gpg"), "w") as fh:
            fh.write("not ciphertext, and unsigned\n")
        git(child, other, "add", "-A")
        git(child, other, *g, "-c", "commit.gpgsign=false", "commit", "-qm", "forged")
        git(child, other, "push", "-q", "origin", "HEAD:main")
        head = git(child, cstore, "rev-parse", "HEAD").stdout.strip()
        p = run(child, "set", "AFTER", stdin="a")
        check("an unsigned commit on the remote refuses the write: named, not applied",
              p.returncode == 1 and "refused: not signed" in p.stderr and "nothing applied" in p.stderr
              and git(child, cstore, "rev-parse", "HEAD").stdout.strip() == head
              and not os.path.exists(os.path.join(cstore, "env", "FORGED.gpg")), p.stderr)
        sync = subprocess.run([sys.executable, SYNC, "status"], env=child, capture_output=True, text=True)
        check("fabric-secrets status says the refusal, and is not OK", sync.returncode == 1
              and "REFUSED: the store refused commit" in sync.stdout and "not signed" in sync.stdout, sync.stdout)
        # Repaired: the remote put back (the parent's or the owner's work).
        git(child, other, "reset", "-q", "--hard", "HEAD~1")
        git(child, other, "push", "-q", "--force", "origin", "HEAD:main")
        p = run(child, "set", "AFTER", stdin="a")
        sync = subprocess.run([sys.executable, SYNC, "status"], env=child, capture_output=True, text=True)
        check("repaired, the next verified fetch clears it", p.returncode == 0 and "REFUSED" not in sync.stdout,
              (p.stderr, sync.stdout))
        # A stranger's key: a valid signature, by no writer of this store.
        subprocess.run(["gpg", "--batch", "--passphrase", "", "--quick-gen-key", "stranger <s@x>", "ed25519", "sign", "never"],
                       env=stranger, capture_output=True, check=True)
        sfpr = subprocess.run(["gpg", "--with-colons", "--list-secret-keys"], env=stranger, capture_output=True,
                              text=True).stdout.split("fpr:::::::::")[1].split(":")[0]
        git(child, other, "pull", "-q", "origin", "main")
        with open(os.path.join(other, "env", "SNEAKY.gpg"), "w") as fh:
            fh.write("x\n")
        git(stranger, other, "add", "-A")
        git(stranger, other, *g, "-c", "commit.gpgsign=true", "-c", f"user.signingkey={sfpr}", "commit", "-qm", "sneaky")
        git(child, other, "push", "-q", "origin", "HEAD:main")
        p = run(parent, "put", "kid", "AFTER_SNEAK", stdin="z")
        check("a commit signed by a key outside the store's writers refuses the parent's put too",
              p.returncode == 1 and "refused:" in p.stderr and "fetch the fabric" in p.stderr
              and not os.path.exists(os.path.join(mirror, "env", "SNEAKY.gpg")), p.stderr)
        git(child, other, "reset", "-q", "--hard", "HEAD~1")
        git(child, other, "push", "-q", "--force", "origin", "HEAD:main")
        p = run(parent, "refresh-mirror", "kid")
        check("refresh-mirror is the verified fetch, and takes the repaired remote", p.returncode == 0, p.stderr)

        print("rotation: a new signing subkey verifies once its key is on main")
        subprocess.run(["gpg", "--batch", "--passphrase", "", "--quick-add-key", cfpr, "ed25519", "sign", "never"],
                       env=child, check=True, capture_output=True)
        p = run(child, "set", "ROTATED", stdin="r")
        check("the child writes with its newest signing subkey", p.returncode == 0, p.stderr)
        p = run(parent, "put", "kid", "AFTER_ROTATION", stdin="r")
        check("the parent refuses it while main holds the child's key without that subkey: fetch the fabric",
              p.returncode == 1 and "fetch the fabric" in p.stderr, p.stderr)
        with open(exported, "w") as fh:
            subprocess.run(["gpg", "--armor", "--export", cfpr], env=child, check=True, stdout=fh)
        p = run(parent, "certify", "kid", exported)
        check("store certify takes the rotated key", p.returncode == 0, p.stderr)
        p = run(parent, "put", "kid", "AFTER_ROTATION", stdin="r")
        check("…but until that is on main, still refused", p.returncode == 1, p.stderr)
        publish()
        p = run(parent, "put", "kid", "AFTER_ROTATION", stdin="r")
        check("merged, the rotated subkey's commit verifies and the put lands", p.returncode == 0, p.stderr)
        p = run(child, "set", "AFTER_ROTATION_2", stdin="r")
        check("…and the child takes the parent's put after the rotation", p.returncode == 0, p.stderr)

        print("the trusted base: explicit, forward only")
        base = git(child, cstore, "config", "--get", "agent-fabric.trustedbase").stdout.strip()
        first = git(child, cstore, "rev-list", "--max-parents=0", "HEAD").stdout.strip()
        p = run(child, "trust-base", first)
        check("a base never moves back", p.returncode == 1 and "only moves forward" in p.stderr, p.stderr)
        check("…and is left as it was", git(child, cstore, "config", "--get", "agent-fabric.trustedbase").stdout.strip() == base)
        p = run(child, "trust-base", "0" * 40)
        check("a base the store does not hold is refused", p.returncode == 1, p.stderr)

        print("first contact: once, from a bundle, while not on main")
        new_id = secret_store.mint_agent_id(secret_store.born_ms_of("now"))
        nkid = role("newkid")
        nstore = nkid["AGENT_FABRIC_SECRET_STORE"]
        run(nkid, "init", "--agent-id", new_id)
        p = run(nkid, "bundle")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", os.path.join(tmp, "new-remote.git")], check=True)
        sc = subprocess.run([sys.executable, TOOL, "seed-child", new_id, "--remote",
                             os.path.join(tmp, "new-remote.git")], env=parent, input=p.stdout, capture_output=True, text=True)
        nmirror = os.path.join(tmp, "parent", ".local", "share", "agent-fabric", "children", new_id)
        check("seed-child takes a new child's first commit, its key on no main, and records the bundle's head as the base",
              sc.returncode == 0 and git(parent, nmirror, "config", "--get", "agent-fabric.trustedbase").stdout.strip()
              == git(parent, nmirror, "rev-parse", "HEAD").stdout.strip(), sc.stderr)
        new_asc = os.path.join(tmp, "newkid.asc")
        nfpr = open(os.path.join(nstore, ".gpg-id")).read().split()[0]
        with open(new_asc, "w") as fh:
            subprocess.run(["gpg", "--armor", "--export", nfpr], env=nkid, check=True, stdout=fh)
        run(parent, "certify", "newkid", new_asc)   # in the working tree only: its keys PR is not merged
        p = run(parent, "put", "newkid", "TOKEN", stdin="t")
        check("the parent puts into the new mirror (its own key is on main)", p.returncode == 0, p.stderr)
        b = run(parent, "child-bundle", "newkid")
        p = run(nkid, "take-bundle", stdin=b.stdout)
        check("the child's first take-bundle, before its keys merge, takes it and records its base once",
              p.returncode == 0 and git(nkid, nstore, "config", "--get", "agent-fabric.firstcontact").returncode == 0, p.stderr)
        run(parent, "put", "newkid", "TOKEN2", stdin="t2")
        b = run(parent, "child-bundle", "newkid")
        p = run(nkid, "take-bundle", stdin=b.stdout)
        check("a second take-bundle before the merge refuses: not yet on main",
              p.returncode == 1 and "not yet on the fabric's main" in p.stderr
              and not os.path.exists(os.path.join(nstore, "env", "TOKEN2.gpg")), p.stderr)
        publish()
        p = run(nkid, "take-bundle", stdin=b.stdout)
        check("merged, the next one verifies and takes it", p.returncode == 0
              and os.path.exists(os.path.join(nstore, "env", "TOKEN2.gpg")), p.stderr)
    finally:
        for g in gnupgs:
            subprocess.run(["gpgconf", "--homedir", g, "--kill", "all"], capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)
    print("test_store_signing: " + ("OK" if not fails else f"FAILED — {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
