#!/usr/bin/env python3
"""ADR-042: an agent's store applies only commits signed by its writers —
its own key and its recorded parent's, read at the fabric's origin/main —
and refuses anything else, named, recorded and said until repaired.

A parent and a child, each a scratch home with its own keyring (never
$HOME/.gnupg: tests/test_secret_store.py says why), share a bare remote
and a scratch fabric checkout whose origin/main stands for the merged
identities/keys/. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import fcntl
import json
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
        # set asks the registry which names are managed (secretstore/reserved.py).
        os.makedirs(os.path.join(fabric, "projects"))
        shutil.copy(os.path.join(ROOT, "projects", "registry.json"), os.path.join(fabric, "projects", "registry.json"))
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
        status = lambda env, *a: subprocess.run([sys.executable, SYNC, "status", *a], env=env,  # noqa: E731
                                                capture_output=True, text=True)
        sync = status(parent)
        check("the parent's status says its mirror has no base, with the repair and the owner (review of #94)",
              sync.returncode == 1 and f"NO BASE: the mirror of agent {KID} has no trusted base" in sync.stdout
              and f"trust-base --store {mirror}, with the owner" in sync.stdout, sync.stdout)
        p = run(parent, "trust-base", "--store", mirror)
        check("trust-base records the mirror's base at its head", p.returncode == 0, p.stderr)
        check("…and status says it no more", "NO BASE" not in status(parent).stdout, status(parent).stdout)
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
        # The control: a complete store, synced, reads OK before anything is refused.
        import pwd
        me = pwd.getpwuid(os.getuid()).pw_name
        for name, value in (("AGENT_LOGIN", me), ("AGENT_HOST", "h"), ("OPENROUTER_API_KEY", "k"),
                            ("CLAUDE_BRIDGE_AUTH_TOKEN", "b"), ("GIT_USER_NAME", "n"), ("GIT_USER_EMAIL", "e@x"),
                            ("GIT_SIGNING_KEY", cfpr), ("GIT_GPG_PROGRAM", "gpg"),
                            ("SSH_PRIVATE_KEY", "private"), ("SSH_PUBLIC_KEY", "public")):
            run(child, "set", name, "--managed", stdin=value)
        subprocess.run([sys.executable, SYNC, "sync", "--quiet"], env=child, capture_output=True, text=True)
        sync = subprocess.run([sys.executable, SYNC, "status"], env=child, capture_output=True, text=True)
        check("control: the complete, synced store's status is OK", sync.returncode == 0, sync.stdout + sync.stderr)
        # A store with no trusted base refuses everything it is given: NOT OK,
        # said as a refusal is, in all three forms (review of #94).
        cbase = git(child, cstore, "config", "--get", "agent-fabric.trustedbase").stdout.strip()
        git(child, cstore, "config", "--unset", "agent-fabric.trustedbase")
        sync, quiet, js = status(child), status(child, "--quiet"), status(child, "--json")
        check("the own store with no base: status NOT OK, naming trust-base",
              sync.returncode == 1 and "NO BASE: the store has no trusted base" in sync.stdout
              and "fabric-secrets store trust-base, once" in sync.stdout and "NOT OK" in sync.stdout, sync.stdout)
        check("…--quiet says it in one line, exit 1",
              quiet.returncode == 1 and quiet.stdout == "" and quiet.stderr.count("\n") == 1
              and quiet.stderr.startswith("fabric-secrets: NO BASE: the store"), repr(quiet.stderr))
        check("…--json lists it by store, in fabric-ctl keys' state name",
              js.returncode == 1 and json.loads(js.stdout).get("no_trusted_base")
              == [{"store": "own", "state": "no base", "path": cstore}], js.stdout[:600])
        # The base is the store's own .git/config's: one in the caller's
        # environment (or ~/.gitconfig) was read as the store's, and trusted it.
        hostile = {**child, "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "agent-fabric.trustedbase",
                   "GIT_CONFIG_VALUE_0": cbase}
        sync = status(hostile)
        p = run(hostile, "set", "HOSTILE_BASE", stdin="h")
        check("a base from the environment is no base: status NO BASE, and a write still refuses",
              sync.returncode == 1 and "NO BASE: the store" in sync.stdout
              and p.returncode == 1 and "has no trusted base" in p.stderr, (sync.stdout, p.stderr))
        # A GIT_DIR in the caller's environment (a git hook runs with one)
        # sent `git -C <store> config --local` to that repository's config.
        other = os.path.join(tmp, "other-repo")
        subprocess.run(["git", "init", "-q", other], check=True, env=child)
        git(child, other, "config", "agent-fabric.trustedbase", cbase)
        planted = {**child, "GIT_DIR": os.path.join(other, ".git"), "GIT_WORK_TREE": other,
                   "GIT_INDEX_FILE": os.path.join(other, ".git", "index")}
        sync = status(planted)
        p = run(planted, "set", "PLANTED_BASE", stdin="h")
        check("another repository's base through GIT_DIR is no base: status NO BASE, a write refuses",
              sync.returncode == 1 and "NO BASE: the store" in sync.stdout
              and p.returncode == 1 and "has no trusted base" in p.stderr, (sync.stdout, p.stderr))
        conf =os.path.join(cstore, ".git", "config")
        os.rename(conf, conf + ".aside")
        os.mkdir(conf)   # unreadable as a file, also to root
        sync = status(child)
        os.rmdir(conf)
        os.rename(conf + ".aside", conf)
        check("a config that cannot be read is BASE UNREADABLE, never no base or OK",
              sync.returncode == 1 and "BASE UNREADABLE: the store: .git/config could not be read (IsADirectoryError)"
              in sync.stdout and "NO BASE" not in sync.stdout, sync.stdout)
        os.rename(os.path.join(cstore, ".git"), os.path.join(cstore, ".git.aside"))
        sync = status(child)
        os.rename(os.path.join(cstore, ".git.aside"), os.path.join(cstore, ".git"))
        check("a store whose .git is gone is BASE UNREADABLE, never OK (#96 review)",
              sync.returncode == 1 and "BASE UNREADABLE: the store: .git/config could not be read (FileNotFoundError)"
              in sync.stdout and "NOT OK" in sync.stdout, sync.stdout)
        git(child, cstore, "config", "agent-fabric.trustedbase", cbase)
        sync = status(child)
        check("…the control: the base back, status is OK again", sync.returncode == 0 and "BASE" not in sync.stdout, sync.stdout)
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
        check("fabric-secrets status says the refusal, and is not OK because of it", sync.returncode == 1
              and "REFUSED: the store refused commit" in sync.stdout and "not signed" in sync.stdout, sync.stdout)
        # Repaired: the remote put back (the parent's or the owner's work).
        git(child, other, "reset", "-q", "--hard", "HEAD~1")
        git(child, other, "push", "-q", "--force", "origin", "HEAD:main")
        p = run(child, "set", "AFTER", stdin="a")
        sync = subprocess.run([sys.executable, SYNC, "status"], env=child, capture_output=True, text=True)
        check("repaired, the next verified fetch clears it", p.returncode == 0 and "REFUSED" not in sync.stdout,
              (p.stderr, sync.stdout))
        # A writer's signed commit that gpg could not judge: verify-commit is
        # silent when its TMPDIR is unusable, as for an unsigned commit, but
        # the commit carries a signature, so it is no refusal (coordinator,
        # 01a117f0-1fff). The unsigned case above is the control.
        p = run(parent, "put", "kid", "UNJUDGED", stdin="u")
        check("control: the parent's signed put reaches the remote", p.returncode == 0, p.stderr)
        head = git(child, cstore, "rev-parse", "HEAD").stdout.strip()
        p = run({**child, "TMPDIR": os.path.join(tmp, "no-such-dir")}, "set", "AFTER2", stdin="a")
        sync = subprocess.run([sys.executable, SYNC, "status"], env=child, capture_output=True, text=True)
        check("a signed commit with no verdict stops the write, 'could not be verified', nothing applied",
              p.returncode == 1 and "could not be verified" in p.stderr and "nothing applied" in p.stderr
              and "refused" not in p.stderr and git(child, cstore, "rev-parse", "HEAD").stdout.strip() == head
              and not os.path.exists(os.path.join(cstore, "env", "UNJUDGED.gpg")), p.stderr)
        check("…and records no refusal: status says none", "REFUSED" not in sync.stdout, sync.stdout)
        p = run(child, "set", "AFTER2", stdin="a")
        check("…verify able to run, the same commit is taken", p.returncode == 0
              and os.path.exists(os.path.join(cstore, "env", "UNJUDGED.gpg")), p.stderr)
        # Whoever can push to the remote writes the headers: a forged one must
        # not turn the refusal into "could not be verified" (review of
        # d4117868..de20af4a, P2). Each is refused, recorded, then repaired.
        armour = "-----BEGIN PGP SIGNATURE-----\n \n AAAA\n -----END PGP SIGNATURE-----"
        for what, header in (("junk inside PGP armour", "gpgsig " + armour),
                             ("the other hash's header (gpgsig-sha256 in a sha1 store)", "gpgsig-sha256 " + armour),
                             ("a header in no signature format", "gpgsig not a signature")):
            git(child, other, "fetch", "-q", "origin")
            git(child, other, "reset", "-q", "--hard", "origin/main")
            tip = git(child, other, "rev-parse", "HEAD").stdout.strip()
            tree = git(child, other, "rev-parse", "HEAD^{tree}").stdout.strip()
            body = (f"tree {tree}\nparent {tip}\nauthor t <t@t> 0 +0000\ncommitter t <t@t> 0 +0000\n"
                    f"{header}\n\nforged\n")
            forged = subprocess.run(["git", "-C", other, "hash-object", "-t", "commit", "-w", "--stdin"], env=child,
                                    input=body, capture_output=True, text=True).stdout.strip()
            git(child, other, "push", "-q", "origin", f"{forged}:refs/heads/main")
            head = git(child, cstore, "rev-parse", "HEAD").stdout.strip()
            p = run(child, "set", "AFTER3", stdin="a")
            sync = subprocess.run([sys.executable, SYNC, "status"], env=child, capture_output=True, text=True)
            check(f"{what}: refused 'not signed', not applied, and status says it",
                  forged and p.returncode == 1 and "refused: not signed" in p.stderr
                  and git(child, cstore, "rev-parse", "HEAD").stdout.strip() == head
                  and "REFUSED: the store refused commit" in sync.stdout, (forged, p.stderr, sync.stdout))
            git(child, other, "push", "-q", "--force", "origin", f"{tip}:refs/heads/main")
            p = run(child, "set", "AFTER3", stdin="a")
            check(f"{what}: repaired, the write goes through", p.returncode == 0, p.stderr)
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

        def forged_bundle(source: str, env: dict) -> str:
            """The source's main with one unsigned commit on top, armored."""
            fork = tempfile.mkdtemp(prefix="fork-", dir=tmp)
            subprocess.run(["git", "clone", "-q", source, fork], env=env, check=True, capture_output=True)
            with open(os.path.join(fork, "env", "FORGED.gpg"), "w") as fh:
                fh.write("x\n")
            git(env, fork, "add", "-A")
            git(env, fork, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-qm", "forged")
            return secret_store._bundle_armored(fork)
        head = git(nkid, nstore, "rev-parse", "HEAD").stdout.strip()
        p = run(nkid, "take-bundle", stdin=forged_bundle(nmirror, parent))
        check("on main, a bundle carrying an unsigned commit is refused, and nothing is taken",
              p.returncode == 1 and "refused: not signed" in p.stderr
              and git(nkid, nstore, "rev-parse", "HEAD").stdout.strip() == head
              and not os.path.exists(os.path.join(nstore, "env", "FORGED.gpg")), p.stderr)
        mbase = git(parent, nmirror, "config", "--get", "agent-fabric.trustedbase").stdout.strip()
        mhead = git(parent, nmirror, "rev-parse", "HEAD").stdout.strip()
        p = subprocess.run([sys.executable, TOOL, "seed-child", new_id, "--remote", os.path.join(tmp, "new-remote.git")],
                           env=parent, input=forged_bundle(nstore, nkid), capture_output=True, text=True)
        check("a mirror with a base is never re-based by a bundle: its unsigned commit is refused",
              p.returncode == 1 and "refused: not signed" in p.stderr
              and git(parent, nmirror, "config", "--get", "agent-fabric.trustedbase").stdout.strip() == mbase
              and git(parent, nmirror, "rev-parse", "HEAD").stdout.strip() == mhead, p.stderr)

        print("review of ADR-042: F1-F5 and two risks")
        refusal_file = lambda store: os.path.join(store, ".git", "agent-fabric-refusal.json")  # noqa: E731

        def forge_on(remote_repo: str, env: dict) -> str:
            """One unsigned commit pushed on top of a remote's main; the head before it."""
            fork = tempfile.mkdtemp(prefix="forge-", dir=tmp)
            subprocess.run(["git", "clone", "-q", remote_repo, fork], env=env, check=True, capture_output=True)
            before = git(env, fork, "rev-parse", "HEAD").stdout.strip()
            os.makedirs(os.path.join(fork, "env"), exist_ok=True)
            with open(os.path.join(fork, "env", "FORGED.gpg"), "w") as fh:
                fh.write("x\n")
            git(env, fork, "add", "-A")
            git(env, fork, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-qm", "forged")
            git(env, fork, "push", "-q", "origin", "HEAD:main")
            return before

        def unforge(remote_repo: str, head: str) -> None:
            subprocess.run(["git", "-C", remote_repo, "update-ref", "refs/heads/main", head], check=True)

        # F5, and the refusal's temporary name: store push takes the remote
        # only as a verified fast-forward; a directory where the old fixed
        # .tmp name lay does not stop the refusal being recorded.
        head = git(child, cstore, "rev-parse", "HEAD").stdout.strip()
        before = forge_on(remote, child)
        os.makedirs(refusal_file(cstore) + ".tmp")
        p = run(child, "push")
        check("store push refuses an unsigned commit on the remote: HEAD unchanged, nothing pushed over it",
              p.returncode == 1 and "refused: not signed" in p.stderr
              and git(child, cstore, "rev-parse", "HEAD").stdout.strip() == head, p.stderr)
        check("…and the refusal is recorded, whatever lies at the old .tmp name", os.path.exists(refusal_file(cstore)))
        os.rmdir(refusal_file(cstore) + ".tmp")
        unforge(remote, before)
        p = run(child, "push")
        check("repaired, store push goes through", p.returncode == 0, p.stderr)

        # A refusal record that cannot be parsed is no clean bill (review of #94).
        with open(refusal_file(cstore), "w") as fh:
            fh.write('{"commit": "abc", "rea')
        sync = subprocess.run([sys.executable, SYNC, "status"], env=child, capture_output=True, text=True)
        check("a truncated refusal record keeps status non-OK, and says so",
              sync.returncode == 1 and "REFUSAL UNREADABLE: the store" in sync.stdout, sync.stdout)
        os.remove(refusal_file(cstore))
        sync = subprocess.run([sys.executable, SYNC, "status"], env=child, capture_output=True, text=True)
        check("…the control: with no record, nothing of it is said", "REFUSAL" not in sync.stdout, sync.stdout)

        # F3: a refusal recorded on a child's mirror is said by the parent's status.
        before = forge_on(remote, child)
        p = run(parent, "refresh-mirror", "kid")
        sync = subprocess.run([sys.executable, SYNC, "status"], env=parent, capture_output=True, text=True)
        check("a refusal on a child's mirror is said by the parent's fabric-secrets status, naming the child",
              p.returncode == 1 and f"REFUSED: the mirror of agent {KID} refused commit" in sync.stdout
              and sync.returncode == 1, (p.stderr, sync.stdout))
        unforge(remote, before)
        p = run(parent, "refresh-mirror", "kid")
        sync = subprocess.run([sys.executable, SYNC, "status"], env=parent, capture_output=True, text=True)
        check("…and cleared by its next verified fetch", p.returncode == 0 and f"mirror of agent {KID}" not in sync.stdout,
              (p.stderr, sync.stdout))
        # Not being able to look is no clean bill: a children directory that
        # cannot be listed was read as no mirrors (review of #94).
        kids = os.path.dirname(mirror)
        os.rename(kids, kids + ".aside")
        open(kids, "w").close()
        sync = status(parent, "--json")
        os.remove(kids)
        os.rename(kids + ".aside", kids)
        check("status fails when the mirrors cannot be listed, and says why",
              sync.returncode == 1 and "could not be read" in json.loads(sync.stdout).get("error", "")
              and "NotADirectoryError" in json.loads(sync.stdout)["error"], sync.stdout[:600])
        sync = status(parent, "--json")
        check("…the control: listed again, no such error", "could not be read" not in json.loads(sync.stdout).get("error", ""),
              sync.stdout[:600])

        # F2: a write whose signing fails leaves nothing staged, says so, and the
        # next write works. git signs through `gpg -bsau`: only that fails.
        fake = os.path.join(tmp, "nosign-bin")
        os.makedirs(fake)
        real_gpg = shutil.which("gpg")
        with open(os.path.join(fake, "gpg"), "w") as fh:
            fh.write(f"#!/bin/sh\nfor a; do case \"$a\" in -bsau|--detach-sign) echo 'signing failed' >&2; exit 2;; esac; done\n"
                     f"exec {real_gpg} \"$@\"\n")
        os.chmod(os.path.join(fake, "gpg"), 0o755)
        nosign = {**child, "PATH": f"{fake}:{child['PATH']}"}
        p = run(nosign, "set", "UNSIGNED_WRITE", stdin="u")
        check("a set whose signing fails says it could not sign, and leaves the store clean",
              p.returncode == 1 and "could not sign" in p.stderr and git(child, cstore, "status", "--porcelain").stdout == ""
              and not os.path.exists(os.path.join(cstore, "env", "UNSIGNED_WRITE.gpg")), (p.stderr, git(child, cstore, "status", "--porcelain").stdout))
        p = run(child, "set", "AFTER_UNSIGNED", stdin="a")
        check("…and the next set works", p.returncode == 0, p.stderr)
        hook = os.path.join(cstore, ".git", "hooks", "pre-commit")
        os.makedirs(os.path.dirname(hook), exist_ok=True)
        with open(hook, "w") as fh:
            fh.write("#!/bin/sh\necho 'a hook said no' >&2\nexit 1\n")
        os.chmod(hook, 0o755)
        p = run(child, "set", "HOOKED", stdin="h")
        os.remove(hook)
        check("a commit that fails for another reason says it could not commit, never could not sign (review of #94)",
              p.returncode == 1 and "could not commit" in p.stderr and "could not sign" not in p.stderr
              and git(child, cstore, "status", "--porcelain").stdout == "", (p.stderr, git(child, cstore, "status", "--porcelain").stdout))
        # The reset that undoes a failed write takes every tracked change with
        # it, so a write starts only from a clean store (review of #94).
        own_entry = os.path.join(cstore, "env", "OWN.gpg")
        with open(own_entry, "ab") as fh:
            fh.write(b"a hand edit")
        edited = open(own_entry, "rb").read()
        p = run(child, "set", "ON_DIRTY", stdin="d")
        check("a set on a store with an uncommitted change refuses, naming it, and keeps the change",
              p.returncode == 1 and "uncommitted changes (env/OWN.gpg)" in p.stderr
              and open(own_entry, "rb").read() == edited
              and not os.path.exists(os.path.join(cstore, "env", "ON_DIRTY.gpg")), p.stderr)
        git(child, cstore, "checkout", "-q", "--", "env/OWN.gpg")
        mentry = os.path.join(mirror, "env", "GH_TOKEN.gpg")
        with open(mentry, "ab") as fh:
            fh.write(b"a hand edit")
        p = run(parent, "put", "kid", "ON_DIRTY", stdin="d")
        check("…a put on a dirty mirror too", p.returncode == 1 and "uncommitted changes (env/GH_TOKEN.gpg)" in p.stderr
              and open(mentry, "rb").read().endswith(b"a hand edit"), p.stderr)
        git(parent, mirror, "checkout", "-q", "--", "env/GH_TOKEN.gpg")
        p = run(child, "set", "ON_CLEAN", stdin="c")
        check("…the control: clean again, the set goes through", p.returncode == 0, p.stderr)
        late = role("late")
        late_id = secret_store.mint_agent_id(secret_store.born_ms_of("now"))
        p = run({**late, "PATH": f"{fake}:{late['PATH']}"}, "init", "--agent-id", late_id)
        lstore = late["AGENT_FABRIC_SECRET_STORE"]
        check("an init whose first commit cannot be signed fails, and stages nothing",
              p.returncode == 1 and "could not sign" in p.stderr
              and not [l for l in git(late, lstore, "status", "--porcelain").stdout.splitlines() if not l.startswith("??")],
              (p.stderr, git(late, lstore, "status", "--porcelain").stdout))
        p = run(late, "init", "--agent-id", late_id)
        check("…and its retry records the base at its first commit, though .git was already there",
              p.returncode == 0 and git(late, lstore, "config", "--get", "agent-fabric.trustedbase").stdout.strip()
              == git(late, lstore, "rev-parse", "HEAD").stdout.strip(), p.stderr)

        # A risk: writers not known yet is no refusal. late is on no main.
        late_remote = os.path.join(tmp, "late-remote.git")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", late_remote], check=True)
        git(late, lstore, "remote", "add", "origin", late_remote)
        git(late, lstore, "push", "-q", "origin", "HEAD:main")
        forge_on(late_remote, late)
        p = run(late, "set", "X", stdin="x")
        check("a store whose writers are not yet on main stops, but records no refusal: not a security event",
              p.returncode == 1 and "not yet on the fabric's main" in p.stderr and "nothing applied" in p.stderr
              and not os.path.exists(refusal_file(lstore)), p.stderr)

        # F1: a child on main, its mirror deleted, re-seeded from a forged
        # bundle: the mirror is rebuilt from the verified remote, the bundle's
        # unsigned commit refused, nothing pushed.
        new_remote = os.path.join(tmp, "new-remote.git")
        rhead = subprocess.run(["git", "-C", new_remote, "rev-parse", "main"], capture_output=True, text=True).stdout.strip()
        shutil.rmtree(nmirror)
        p = subprocess.run([sys.executable, TOOL, "seed-child", new_id, "--remote", new_remote],
                           env=parent, input=forged_bundle(nstore, nkid), capture_output=True, text=True)
        check("a deleted mirror of a child on main takes no base from a bundle: its unsigned commit refused, nothing pushed",
              p.returncode == 1 and "refused: not signed" in p.stderr
              and subprocess.run(["git", "-C", new_remote, "rev-parse", "main"], capture_output=True, text=True).stdout.strip()
              == rhead, p.stderr)
        check("…the mirror rebuilt from the child's remote, verified from the root, its base that head",
              git(parent, nmirror, "config", "--get", "agent-fabric.trustedbase").stdout.strip() == rhead
              and git(parent, nmirror, "rev-parse", "HEAD").stdout.strip() == rhead)
        before = forge_on(new_remote, parent)
        shutil.rmtree(nmirror)
        p = subprocess.run([sys.executable, TOOL, "seed-child", new_id, "--remote", new_remote],
                           env=parent, input=run(nkid, "bundle").stdout, capture_output=True, text=True)
        check("a remote carrying an unsigned commit gives no mirror: refused, and nothing left behind",
              p.returncode == 1 and "refused: not signed" in p.stderr and not os.path.exists(nmirror), p.stderr)
        check("…and the refusal names the owner's repair, not a rebuild that would refuse again (review of #94)",
              "the owner's to repair by hand" in p.stderr and f"trust-base --store {nmirror}" in p.stderr, p.stderr)
        # The refusal's record lay inside the mirror removed with it, so status
        # never said it (review of #96): kept beside the mirror, until a
        # verified fetch clears it.
        sync = subprocess.run([sys.executable, SYNC, "status"], env=parent, capture_output=True, text=True)
        check("…and the parent's status says that refusal, though the mirror is gone",
              sync.returncode == 1 and f"REFUSED: the mirror of agent {new_id} refused commit" in sync.stdout
              and os.path.exists(nmirror + ".refusal.json"), sync.stdout)
        unforge(new_remote, before)
        os.makedirs(os.path.join(nmirror, ".git"))
        # Two seed-childs on one mirror removed each other's (review of #94):
        # one at a time, the second refused while the first holds the lock.
        lock = os.open(nmirror + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        p = subprocess.run([sys.executable, TOOL, "seed-child", new_id, "--remote", new_remote],
                           env=parent, input=run(nkid, "bundle").stdout, capture_output=True, text=True)
        os.close(lock)
        check("a seed-child while another holds the mirror is refused, and touches nothing",
              p.returncode == 1 and f"another seed-child of agent {new_id} is running" in p.stderr
              and os.listdir(os.path.join(nmirror, ".git")) == [], p.stderr)
        p = subprocess.run([sys.executable, TOOL, "seed-child", new_id, "--remote", new_remote],
                           env=parent, input=run(nkid, "bundle").stdout, capture_output=True, text=True)
        check("a mirror that is there with no base is refused before it is touched",
              p.returncode == 1 and "has no trusted base" in p.stderr and os.listdir(os.path.join(nmirror, ".git")) == [],
              p.stderr)
        check("…its advice is the owner's trust-base, never a removal that loops (review of #94)",
              f"trust-base --store {nmirror}" in p.stderr and "remove the mirror to rebuild" not in p.stderr, p.stderr)
        shutil.rmtree(nmirror)
        p = subprocess.run([sys.executable, TOOL, "seed-child", new_id, "--remote", new_remote],
                           env=parent, input=run(nkid, "bundle").stdout, capture_output=True, text=True)
        sync = subprocess.run([sys.executable, SYNC, "status"], env=parent, capture_output=True, text=True)
        check("the kept refusal is over once the mirror is rebuilt and takes a verified head",
              p.returncode == 0 and not os.path.exists(nmirror + ".refusal.json")
              and f"mirror of agent {new_id}" not in sync.stdout, (p.stderr, sync.stdout))
    finally:
        for g in gnupgs:
            subprocess.run(["gpgconf", "--homedir", g, "--kill", "all"], capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)
    print("test_store_signing: " + ("OK" if not fails else f"FAILED — {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
