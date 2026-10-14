#!/usr/bin/env python3
"""bin/fabric-sign (agent-fabric ADR-057), run as git runs it: a real `git commit`
with gpg.program / gpg.ssh.program naming the shim, in a throwaway GNUPGHOME
holding a key shaped like an agent's (a certify-only primary and one signing
subkey), against a fake `ots` that records its calls and can be told to fail.
What is proved: a commit signed in each format verifies, a timestamp request
that fails leaves no commit and no signature (and its positive control signs),
the proof waits in the spool keyed by the signature and becomes the commit's
note, a note carried over by an amend is replaced, and verification does not
depend on the proof. The live calendars are not contacted (docs/live-checks).

Exit codes: 0 all checks passed, 1 one or more failed."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from git_env import scrub_process_env  # noqa: E402
scrub_process_env()
from signing_fixture import drop_key, make_agent_key  # noqa: E402
from signing import notes, proof  # noqa: E402

SIGN = os.path.join(HERE, "bin", "fabric-sign")
T = tempfile.mkdtemp(prefix="test_fabric_sign.")
GNUPG, PRIMARY, SUB = make_agent_key(T)
SPOOL = f"{T}/spool"
OTS_LOG = f"{T}/ots.log"
REPO = f"{T}/repo"
FAKE_OTS = f"{T}/ots"
SCRATCH = f"{T}/tmp"
os.makedirs(SCRATCH)
fails = 0

with open(FAKE_OTS, "w", encoding="utf-8") as f:
    f.write(f'''#!{sys.executable}
import hashlib, os, sys
path = sys.argv[-1]
with open({OTS_LOG!r}, "a") as log:
    log.write(" ".join(sys.argv[1:-1]) + "\\n")
mode = os.environ.get("FAKE_OTS_MODE", "ok")
if mode == "fail":
    sys.stderr.write("Exception: Timeout\\n")
    sys.exit(1)
if mode == "nofile":
    sys.exit(0)
digest = hashlib.sha256(open(path, "rb").read() + (b"x" if mode == "wrongdigest" else b"")).digest()
open(path + ".ots", "wb").write({proof.MAGIC!r} + b"\\x01\\x08" + digest + b"\\x00calendar")
''')
os.chmod(FAKE_OTS, 0o755)


def check(label: str, good: bool, detail: str = "") -> None:
    global fails
    if good:
        print(f"  ok   {label}")
        return
    fails += 1
    print(f"  FAIL {label}: {detail}")


def env(**extra: str) -> dict[str, str]:
    return {"PATH": "/usr/bin:/bin", "HOME": f"{T}/home", "LANG": "C.UTF-8", "GNUPGHOME": GNUPG,
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
            "AGENT_FABRIC_PYTHON": sys.executable, "FABRIC_SIGN_OTS": FAKE_OTS, "FABRIC_SIGN_SPOOL": SPOOL,
            # Its own, removed with T: git 2.47 (Debian stable) leaves a .git_signing_key_tmp* in $TMPDIR for every
            # literal-key SSH signature, which the runner's leak check reports (2c8cda7d, test_signing_rule5).
            "TMPDIR": SCRATCH, "PYTHONDONTWRITEBYTECODE": "1", **extra}


def git(*args: str, e: dict | None = None, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", REPO, *args], env=e or env(), capture_output=True, text=True, input=stdin, timeout=120)


def fresh_repo() -> None:
    shutil.rmtree(REPO, ignore_errors=True)
    shutil.rmtree(SPOOL, ignore_errors=True)
    os.makedirs(REPO)
    git("init", "-q", "-b", "main")
    git("config", "notes.rewriteRef", notes.REF)


def sign_args(fmt: str) -> list[str]:
    if fmt == "openpgp":
        return ["-c", f"gpg.program={SIGN}", "-c", f"user.signingkey={SUB}!", "-c", "commit.gpgsign=true"]
    ssh_key = subprocess.run([SIGN, "key", "ssh", PRIMARY], env=env(), capture_output=True, text=True, timeout=60).stdout.strip()
    return ["-c", "gpg.format=ssh", "-c", f"gpg.ssh.program={SIGN}", "-c", f"user.signingkey={ssh_key}",
            "-c", "commit.gpgsign=true"]


def commit(fmt: str, name: str, *extra: str, e: dict | None = None) -> subprocess.CompletedProcess:
    with open(f"{REPO}/{name}", "w", encoding="utf-8") as f:
        f.write(name + "\n")
    git("add", name)
    return git(*sign_args(fmt), "commit", "-q", "-m", name, *extra, e=e)


def signature_of(rev: str = "HEAD") -> bytes:
    return notes.commit_signature(subprocess.run(["git", "-C", REPO, "cat-file", "commit", rev], capture_output=True, timeout=30).stdout)


def head() -> str:
    return git("rev-parse", "HEAD").stdout.strip()


def spooled() -> list[str]:
    return sorted(os.listdir(SPOOL)) if os.path.isdir(SPOOL) else []


def note_blob(rev: str = "HEAD") -> bytes | None:
    p = subprocess.run(["git", "-C", REPO, "notes", f"--ref={notes.REF}", "show", rev], capture_output=True, timeout=30)
    return p.stdout if p.returncode == 0 else None


def ots_calls() -> list[str]:
    try:
        with open(OTS_LOG, encoding="utf-8") as f:
            return f.read().splitlines()
    except FileNotFoundError:
        return []


def allowed_signers() -> str:
    pub = subprocess.run([SIGN, "key", "ssh", PRIMARY], env=env(), capture_output=True, text=True, timeout=60).stdout.strip()
    path = f"{T}/allowed_signers"
    with open(path, "w", encoding="utf-8") as f:
        f.write("t@example.invalid " + pub.removeprefix("key::") + "\n")
    return path


def verify(fmt: str) -> subprocess.CompletedProcess:
    cfg = ["-c", f"gpg.program={SIGN}"] if fmt == "openpgp" else \
        ["-c", "gpg.format=ssh", "-c", f"gpg.ssh.program={SIGN}", "-c", f"gpg.ssh.allowedSignersFile={allowed_signers()}"]
    return git(*cfg, "verify-commit", "HEAD")


def run() -> None:
    for fmt in ("openpgp", "ssh"):
        print(f"a commit signed in {fmt}")
        fresh_repo()
        r = commit(fmt, "a")
        check("git commit succeeds", r.returncode == 0, r.stderr)
        sig = signature_of()
        marker = b"BEGIN PGP SIGNATURE" if fmt == "openpgp" else b"BEGIN SSH SIGNATURE"
        check("the commit carries a signature of that format", marker in sig, sig[:60].decode(errors="replace"))
        v = verify(fmt)
        check("git verify-commit accepts it", v.returncode == 0, v.stderr)
        key = proof.key_of(sig)
        check("its proof waits in the spool, named by the signature's digest", spooled() == [key + ".ots"], str(spooled()))
        waiting = open(f"{SPOOL}/{key}.ots", "rb").read() if spooled() else b""
        check("…and is a proof of exactly that signature", proof.matches(sig, waiting))
        check("the stamp was asked for with no Bitcoin client", ots_calls() and ots_calls()[-1].startswith("--no-bitcoin"), str(ots_calls()))
        check("the spool is private", (os.stat(SPOOL).st_mode & 0o777) == 0o700 and
              (os.stat(f"{SPOOL}/{key}.ots").st_mode & 0o777) == 0o600)
        n = subprocess.run([SIGN, "note", "HEAD"], cwd=REPO, env=env(), capture_output=True, text=True, timeout=60)
        check("`note` attaches it", n.returncode == 0 and n.stdout.split() == ["ATTACHED", head()], n.stdout + n.stderr)
        check("the note is the proof, byte for byte", note_blob() == waiting)
        check("the spool entry stays until the note is seen to equal it", spooled() == [key + ".ots"], str(spooled()))
        n = subprocess.run([SIGN, "note", "HEAD"], cwd=REPO, env=env(), capture_output=True, text=True, timeout=60)
        check("`note` again changes nothing", n.stdout.split() == ["PRESENT", head()] and note_blob() == waiting, n.stdout)
        check("…and then the spool entry is gone", spooled() == [])

        print(f"the timestamp request fails ({fmt})")
        fresh_repo()
        commit(fmt, "base")
        before = head()
        scratch = f"{T}/tmp-{fmt}"
        shutil.rmtree(scratch, ignore_errors=True)
        os.makedirs(scratch)
        for mode in ("fail", "nofile", "wrongdigest"):
            r = commit(fmt, "b" + mode, e=env(FAKE_OTS_MODE=mode, TMPDIR=scratch))
            # Only *.sig: some git versions also leave their own .git_signing_key_tmp* (a public key) behind.
            left = [n for n in os.listdir(scratch) if n.endswith(".sig")]
            check(f"[{mode}] no signature is left in TMPDIR", left == [], str(left))
            check(f"[{mode}] the commit fails", r.returncode != 0, r.stdout)
            check(f"[{mode}] and no commit was made", head() == before, head())
            check(f"[{mode}] the message says the commit is not signed", "not signed" in r.stderr, r.stderr)
        r = commit(fmt, "gone", e=env(FABRIC_SIGN_OTS=f"{T}/no-such-ots"))
        check("a missing ots client fails the commit, naming it", r.returncode != 0 and "no-such-ots" in r.stderr and head() == before, r.stderr)
        check("no proof was kept for a signature that was withheld", len(spooled()) == 1, str(spooled()))
        r = commit(fmt, "control")
        check("positive control: the same commit with a working stamp signs", r.returncode == 0 and head() != before, r.stderr)
        if fmt == "ssh":
            control = f"{GNUPG}/sshcontrol"
            ours = open(control, encoding="utf-8").read()
            other = "0" * 40
            with open(control, "w", encoding="utf-8") as f:
                f.write(other)  # a hand edit that lost its final newline, and lists no key of ours
            r = commit(fmt, "sshcontrol")
            lines = open(control, encoding="utf-8").read().splitlines()
            check("a sshcontrol without a final newline keeps its last entry whole", r.returncode == 0 and other in lines, f"{lines} {r.stderr}")
            check("…and gains the key's keygrip on a line of its own", len(lines) == 2 and len(lines[1]) == 40, str(lines))
            with open(control, "w", encoding="utf-8") as f:
                f.write(ours)

        print(f"verification does not need the proof ({fmt})")
        r = commit(fmt, "v")
        shutil.rmtree(SPOOL, ignore_errors=True)
        v = verify(fmt)
        check("verify-commit passes with no proof anywhere and no network", v.returncode == 0, v.stderr)
        n = subprocess.run([SIGN, "note", "HEAD"], cwd=REPO, env=env(), capture_output=True, text=True, timeout=60)
        check("`note` with no proof says MISSING and exits 1", n.stdout.split()[:1] == ["MISSING"] and n.returncode == 1, n.stdout + n.stderr)

    print("a signature that gpg itself refuses")
    fresh_repo()
    git("config", "user.signingkey", "0" * 40)
    open(OTS_LOG, "w").close()
    with open(f"{REPO}/z", "w") as f:
        f.write("z\n")
    git("add", "z")
    r = git("-c", f"gpg.program={SIGN}", "-c", f"user.signingkey={'0' * 40}", "-c", "commit.gpgsign=true", "commit", "-q", "-m", "z")
    check("the commit fails", r.returncode != 0)
    check("no timestamp was requested for it and nothing waits", ots_calls() == [] and spooled() == [], str(ots_calls()))

    print("a note that an amend carried over")
    fresh_repo()
    commit("openpgp", "a")
    subprocess.run([SIGN, "note"], cwd=REPO, env=env(), capture_output=True, timeout=60)
    old_note = note_blob()
    r = git(*sign_args("openpgp"), "commit", "-q", "--amend", "-m", "a again")
    check("the amend signs again", r.returncode == 0, r.stderr)
    carried = note_blob()
    check("git carried the old proof over (the premise)", carried == old_note and not proof.matches(signature_of(), carried or b""))
    n = subprocess.run([SIGN, "note"], cwd=REPO, env=env(), capture_output=True, text=True, timeout=60)
    check("`note` replaces it with the new signature's", n.stdout.split()[0] == "ATTACHED" and proof.matches(signature_of(), note_blob() or b""), n.stdout)
    git(*sign_args("openpgp"), "commit", "-q", "--amend", "-m", "a third time")
    shutil.rmtree(SPOOL, ignore_errors=True)
    n = subprocess.run([SIGN, "note"], cwd=REPO, env=env(), capture_output=True, text=True, timeout=60)
    check("with no proof waiting a carried-over note is STALE, not accepted", n.stdout.split()[0] == "STALE" and n.returncode == 1, n.stdout)

    print("a note that git concatenated behind the right proof")
    fresh_repo()
    commit("openpgp", "a")
    first = proof.Spool(SPOOL).get(proof.key_of(signature_of()))
    subprocess.run([SIGN, "note"], cwd=REPO, env=env(), capture_output=True, timeout=60)
    other = proof.MAGIC + b"\x01\x08" + b"\x11" * 32 + b"\x00old"
    blob = subprocess.run(["git", "-C", REPO, "hash-object", "-w", "--stdin"], input=first + b"\n\n" + other, capture_output=True, timeout=30).stdout.decode().strip()
    git("notes", f"--ref={notes.REF}", "add", "-f", "-C", blob, "HEAD")
    check("(premise) the note now starts with the right proof", (note_blob() or b"").startswith(first) and note_blob() != first)
    n = subprocess.run([SIGN, "note"], cwd=REPO, env=env(), capture_output=True, text=True, timeout=60)
    check("it is replaced by the clean proof from the spool, not read as present", n.stdout.split()[0] == "ATTACHED" and note_blob() == first, n.stdout)
    git("notes", f"--ref={notes.REF}", "add", "-f", "-C", blob, "HEAD")
    shutil.rmtree(SPOOL, ignore_errors=True)
    n = subprocess.run([SIGN, "note"], cwd=REPO, env=env(), capture_output=True, text=True, timeout=60)
    check("with nothing waiting it is STALE, never accepted", n.stdout.split()[0] == "STALE", n.stdout)

    print("an unsigned commit")
    fresh_repo()
    with open(f"{REPO}/u", "w") as f:
        f.write("u\n")
    git("add", "u")
    git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "u")
    n = subprocess.run([SIGN, "note"], cwd=REPO, env=env(), capture_output=True, text=True, timeout=60)
    check("`note` says UNSIGNED and exits 0", n.stdout.split()[0] == "UNSIGNED" and n.returncode == 0, n.stdout + n.stderr)

    print("the key helper")
    for fmt, want in (("openpgp", SUB + "!"), ("ssh", "key::ssh-ed25519 ")):
        p = subprocess.run([SIGN, "key", fmt, PRIMARY], env=env(), capture_output=True, text=True, timeout=60)
        check(f"`key {fmt}` prints the subkey's value for user.signingkey", p.returncode == 0 and p.stdout.strip().startswith(want.upper() if fmt == "openpgp" else want) , p.stdout + p.stderr)
    p = subprocess.run([SIGN, "key", "x509"], env=env(), capture_output=True, text=True, timeout=60)
    check("an unknown format is a usage error", p.returncode == 2, p.stderr)

    print("the spool")
    sp = proof.Spool(f"{T}/spool2")
    sp.put("a" * 64, b"p")
    old = time.time() - proof.SPOOL_MAX_AGE_S - 10
    os.utime(f"{T}/spool2/{'a' * 64}.ots", (old, old))
    sp.put("b" * 64, b"q")
    sp.prune()
    check("a proof older than the bound is pruned, a fresh one kept", sp.get("a" * 64) is None and sp.get("b" * 64) == b"q")
    check("proof_digest refuses what is not a proof", not proof.matches(b"x", b"not a proof") and not proof.matches(b"x", proof.MAGIC))
    check("the key is the digest of the signature without its surrounding whitespace",
          proof.key_of(b"\nsig\n") == hashlib.sha256(b"sig").hexdigest())


try:
    run()
finally:
    drop_key(GNUPG)
    shutil.rmtree(T, ignore_errors=True)
print(f"{fails} failed" if fails else "all passed")
sys.exit(1 if fails else 0)
