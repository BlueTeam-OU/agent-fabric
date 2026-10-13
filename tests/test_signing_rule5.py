#!/usr/bin/env python3
"""tools/fabric/guards/ban_unsigned_commits.py, rule 5 of agent-fabric ADR-057:
each line of the checker's threat model, as a fixture commit the CI entry
point refuses, beside the positive controls that pass.

The fixture is a whole small fleet in a temporary directory: a root key and
agent keys shaped as ADR-038 makes them (certify-only primary; sign, encrypt
and authenticate subkeys), each child certified by the root, their public
halves and lineage.json under an operator root of its own (AGENT_FABRIC_OPERATOR),
a stand-in for the shared owner key that is in no lineage, a revoked agent, an
agent its parent never certified; commits signed through the real
bin/fabric-sign (both formats) against a fake `ots`, their proofs attached as
notes by `fabric-sign note`. No case reads this checkout's instance data.

Exit codes: 0 all checks passed, 1 one or more failed."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric", "guards"))
from git_env import scrub_process_env  # noqa: E402
scrub_process_env()
from signing_fixture import drop_key  # noqa: E402
from signing import proof as proof_mod  # noqa: E402
from secretstore import lineage as lineage_mod  # noqa: E402
import ban_unsigned_commits as guard_mod  # noqa: E402

GUARD = os.path.join(HERE, "tools", "fabric", "guards", "ban_unsigned_commits.py")
SIGN = os.path.join(HERE, "bin", "fabric-sign")
CI = os.path.join(HERE, ".github", "workflows", "ci.yml")
T = tempfile.mkdtemp(prefix="r5.")
GNUPG = os.path.join(T, "g")
FABRIC = os.path.join(T, "fabric")
REPO = os.path.join(T, "repo")
SPOOL = os.path.join(T, "spool")
FAKE_OTS = os.path.join(T, "ots")
SLUG = "acme/widget"
fails = 0

with open(FAKE_OTS, "w", encoding="utf-8") as f:
    f.write(f'''#!{sys.executable}
import hashlib, sys
path = sys.argv[-1]
digest = hashlib.sha256(open(path, "rb").read()).digest()
open(path + ".ots", "wb").write({proof_mod.MAGIC!r} + b"\\x01\\x08" + digest + b"\\x00calendar")
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
    e = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": f"{T}/home", "LANG": "C.UTF-8", "GNUPGHOME": GNUPG,
         "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
         "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
         "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
         "AGENT_FABRIC_PYTHON": sys.executable, "FABRIC_SIGN_OTS": FAKE_OTS, "FABRIC_SIGN_SPOOL": SPOOL,
         "PYTHONDONTWRITEBYTECODE": "1"}
    if os.environ.get("TMPDIR"):
        e["TMPDIR"] = os.environ["TMPDIR"]
    e.update(extra)
    return e


def gpg(*args: str, home: str = GNUPG) -> str:
    return subprocess.run(["gpg", "--homedir", home, "--batch", "--quiet", "--pinentry-mode", "loopback",
                           "--passphrase", "", *args], env=env(), check=True, capture_output=True, timeout=60).stdout.decode()


def git(*args: str, repo: str = REPO, check_ok: bool = True, **extra: str) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", "-C", repo, *args], env=env(**extra), capture_output=True, text=True, timeout=120)
    if check_ok and r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr}")
    return r


# --- the fleet --------------------------------------------------------------

_ms = int(time.time() * 1000) - 10_000


def new_id() -> str:
    global _ms
    _ms += 7
    h = f"{_ms:012x}"
    rand = hashlib.sha256(str(_ms).encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-7{rand[:3]}-8{rand[3:6]}-{rand[6:18]}"


def make_key(login: str, aid: str) -> tuple[str, str]:
    """(primary fingerprint, signing subkey fingerprint), in GNUPG."""
    gpg("--quick-gen-key", f"{login} <{aid}@{lineage_mod.UID_DOMAIN}>", "ed25519", "cert", "never")
    listing = gpg("--with-colons", "--list-keys", f"<{aid}@{lineage_mod.UID_DOMAIN}>")
    primary = next(l.split(":")[9] for l in listing.splitlines() if l.startswith("fpr:"))
    for algo, use in (("ed25519", "sign"), ("cv25519", "encr"), ("ed25519", "auth")):
        gpg("--quick-add-key", primary, algo, use, "never")
    lines = gpg("--with-colons", "--list-keys", primary).splitlines()
    sub = next(lines[i + 1].split(":")[9] for i, l in enumerate(lines) if l.startswith("sub:") and "s" in l.split(":")[11])
    return primary, sub


AGENTS: dict[str, dict] = {}


def agent(login: str, parent: str | None, certify: bool = True) -> None:
    aid = new_id()
    primary, sub = make_key(login, aid)
    if parent is not None and certify:
        gpg("-u", AGENTS[parent]["primary"], "--quick-sign-key", primary)
    AGENTS[login] = {"id": aid, "primary": primary, "sub": sub, "parent": parent}


def write_fleet(revoked: tuple[str, ...] = ()) -> None:
    keys = os.path.join(FABRIC, "identities", "keys")
    os.makedirs(keys, exist_ok=True)
    doc = {}
    for login, a in AGENTS.items():
        if login == "owner":
            continue
        armored = gpg("--armor", "--export", a["primary"])
        if login in revoked:
            # Revoked in a keyring of its own, so the signer's keeps signing
            # with it (a commit made before the revocation is the case).
            side = os.path.join(T, "rev")
            shutil.rmtree(side, ignore_errors=True)
            os.makedirs(side, mode=0o700)
            p = subprocess.run(["gpg", "--homedir", side, "--batch", "--quiet", "--import"], input=armored.encode(),
                               capture_output=True, timeout=60, env=env())
            assert p.returncode == 0, p.stderr
            with open(os.path.join(GNUPG, "openpgp-revocs.d", f"{a['primary']}.rev"), encoding="utf-8") as f:
                cert = f.read().replace(":-----BEGIN PGP PUBLIC KEY BLOCK-----", "-----BEGIN PGP PUBLIC KEY BLOCK-----")
            subprocess.run(["gpg", "--homedir", side, "--batch", "--quiet", "--import"], input=cert.encode(),
                           capture_output=True, timeout=60, env=env(), check=True)
            armored = gpg("--armor", "--export", a["primary"], home=side)
            drop_key(side)
        with open(os.path.join(keys, f"{a['id']}.asc"), "w", encoding="utf-8") as f:
            f.write(armored)
        doc[a["id"]] = {"born": lineage_mod.born_of(a["id"]), "fingerprint": a["primary"], "login": login,
                        "parent": AGENTS[a["parent"]]["id"] if a["parent"] else None}
    with open(os.path.join(keys, "lineage.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)


def write_operator(since: str | None, fmt: str = "ssh") -> None:
    pol = os.path.join(FABRIC, "policies")
    os.makedirs(pol, exist_ok=True)
    with open(os.path.join(pol, "signing.json"), "w", encoding="utf-8") as f:
        json.dump({"default": {"format": "ssh", "since": None},
                   "repositories": {SLUG: {"format": fmt, "since": since}}}, f)
    with open(os.path.join(pol, "authority.json"), "w", encoding="utf-8") as f:
        json.dump({"role_definitions": {"role": "fabric-coordinator", "holders": ["user"]}}, f)
    for role in ("fabric-coordinator", "python-dev", "web-dev", "devex-tooling", "language-culture/locale/en"):
        os.makedirs(os.path.join(FABRIC, "identities", "roles", role), exist_ok=True)
    os.makedirs(os.path.join(FABRIC, "projects"), exist_ok=True)
    with open(os.path.join(FABRIC, "projects", "registry.json"), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "projects": {"widget": {"remotes": [f"git@github.com:{SLUG}.git"],
                                                          "default_branch": "main"}}}, f)


# --- commits ----------------------------------------------------------------

def sign_cfg(login: str, fmt: str) -> list[str]:
    a = AGENTS[login]
    if fmt == "openpgp":
        return ["-c", "gpg.format=openpgp", "-c", f"gpg.program={SIGN}", "-c", f"user.signingkey={a['sub']}!",
                "-c", "commit.gpgsign=true"]
    if "ssh" not in a:
        a["ssh"] = subprocess.run([SIGN, "key", "ssh", a["primary"]], env=env(), capture_output=True, text=True,
                                  timeout=60, check=True).stdout.strip()
    return ["-c", "gpg.format=ssh", "-c", f"gpg.ssh.program={SIGN}", "-c", f"user.signingkey={a['ssh']}",
            "-c", "commit.gpgsign=true"]


_n = 0


def commit(login: str | None, role: str | None, fmt: str = "ssh", note: bool = True) -> str:
    """A commit on the current branch; login None = unsigned."""
    global _n
    _n += 1
    name = f"f{_n}"
    with open(os.path.join(REPO, name), "w", encoding="utf-8") as f:
        f.write(name + "\n")
    git("add", name)
    msg = f"change {name}" + (f"\n\nFabric-Role: {role}\n" if role else "")
    cfg = sign_cfg(login, fmt) if login else ["-c", "commit.gpgsign=false"]
    git(*cfg, "commit", "-q", "-m", msg)
    sha = git("rev-parse", "HEAD").stdout.strip()
    if login and note:
        subprocess.run([SIGN, "note", sha], cwd=REPO, env=env(), capture_output=True, timeout=60, check=True)
    return sha


def branch(name: str) -> None:
    git("checkout", "-q", "-B", name, "main")


def guard(cwd: str = REPO, base: str = "main", **extra: str) -> subprocess.CompletedProcess:
    e = env(AGENT_FABRIC_OPERATOR=FABRIC, AGENT_FABRIC_SIGNATURES_BASE=base, **extra)
    return subprocess.run([sys.executable, GUARD], cwd=cwd, env=e, capture_output=True, text=True, timeout=300)


def refused(r: subprocess.CompletedProcess, words: str) -> bool:
    return r.returncode == 1 and words in r.stderr


def passed(r: subprocess.CompletedProcess) -> bool:
    return r.returncode == 0 and "OK" in r.stdout


def run() -> None:
    os.makedirs(f"{T}/home")
    os.makedirs(GNUPG, mode=0o700)
    agent("user", None)
    for login in ("python-dev-04", "web-dev-01", "language-culture-en", "devex-tooling"):
        agent(login, "user")
    agent("orphan-dev", "user", certify=False)
    agent("owner", None)     # the shared key's stand-in: signs, in no lineage
    write_fleet(revoked=("devex-tooling",))
    os.makedirs(os.path.join(FABRIC, "identities", "roles", "orphan-dev"), exist_ok=True)

    os.makedirs(REPO)
    git("init", "-q", "-b", "main")
    git("remote", "add", "origin", f"git@github.com:{SLUG}.git")
    old = commit("owner", "fabric-coordinator", fmt="openpgp", note=False)
    write_operator(since=old)

    print("the positive controls")
    branch("ok-ssh")
    commit("python-dev-04", "python-dev")
    r = guard()
    check("an agent's own SSH signature, a role its login holds (-<n>), its proof: passes", passed(r), r.stdout + r.stderr)
    branch("ok-holder")
    commit("user", "fabric-coordinator")
    r = guard()
    check("a holder named in role_definitions: passes", passed(r), r.stdout + r.stderr)
    branch("ok-locale")
    commit("language-culture-en", "language-culture")
    r = guard()
    check("a locale's holder (<role>-<suffix>): passes", passed(r), r.stdout + r.stderr)
    branch("ok-merge")
    commit("python-dev-04", "python-dev")
    git("checkout", "-q", "-b", "side", "main")
    commit("web-dev-01", "web-dev")
    git("checkout", "-q", "ok-merge")
    git(*sign_cfg("python-dev-04", "ssh"), "merge", "-q", "--no-ff", "-m", "merge side\n\nFabric-Role: python-dev", "side")
    subprocess.run([SIGN, "note", "HEAD"], cwd=REPO, env=env(), capture_output=True, timeout=60, check=True)
    git("branch", "-q", "-D", "side")
    r = guard()
    check("a merge the agent signed, over two agents' commits: passes", passed(r), r.stdout + r.stderr)

    print("threat model: the signer")
    branch("other-key")
    commit("web-dev-01", "python-dev")
    r = guard()
    check("another account's key, claiming this account's role: refused", refused(r, "may not hold the role"), r.stderr)
    branch("owner-ssh")
    commit("owner", "python-dev", fmt="ssh")
    r = guard()
    check("the shared owner key (a key in no lineage), SSH form: refused", refused(r, "not signed by the SSH form"), r.stderr)
    write_operator(since=old, fmt="openpgp")
    branch("owner-pgp")
    commit("owner", "python-dev", fmt="openpgp")
    r = guard()
    check("the shared owner key (a key in no lineage), OpenPGP: refused",
          refused(r, "not signed by an agent's signing subkey"), r.stderr)
    branch("ok-pgp")
    commit("python-dev-04", "python-dev", fmt="openpgp")
    r = guard()
    check("(control) an agent's own OpenPGP signature where the policy says openpgp: passes", passed(r), r.stdout + r.stderr)
    branch("primary-pgp")
    git("checkout", "-q", "primary-pgp")
    with open(os.path.join(REPO, "p"), "w", encoding="utf-8") as f:
        f.write("p\n")
    git("add", "p")
    # A primary that only certifies cannot sign; forced with `!`, gpg uses it anyway.
    pr = git(*sign_cfg("python-dev-04", "openpgp")[:4], "-c", f"user.signingkey={AGENTS['python-dev-04']['primary']}!",
             "commit", "-q", "-S", "-m", "p\n\nFabric-Role: python-dev", check_ok=False)
    if pr.returncode == 0:
        subprocess.run([SIGN, "note", "HEAD"], cwd=REPO, env=env(), capture_output=True, timeout=60)
        r = guard()
        check("a signature by the primary key, not the signing subkey: refused",
              refused(r, "not signed by an agent's signing subkey"), r.stderr)
    else:
        check("(premise) a certify-only primary does not sign", "sign" in pr.stderr.lower() or pr.returncode != 0)
    write_operator(since=old, fmt="ssh")
    branch("format")
    commit("python-dev-04", "python-dev", fmt="openpgp")
    r = guard()
    check("a format the policy does not admit (OpenPGP where it says ssh): refused", refused(r, "the policy admits ssh"), r.stderr)
    branch("revoked")
    commit("devex-tooling", "devex-tooling")
    r = guard()
    check("a revoked key: refused", refused(r, "devex-tooling") or refused(r, AGENTS["devex-tooling"]["id"]), r.stderr)
    check("  ... and the refusal says it is revoked", "is revoked" in r.stderr, r.stderr)
    branch("uncertified")
    commit("orphan-dev", "orphan-dev")
    r = guard()
    check("a key its parent never certified (the chain does not verify): refused",
          refused(r, "lineage does not certify"), r.stderr)

    print("threat model: the role")
    branch("coord")
    commit("python-dev-04", "fabric-coordinator")
    r = guard()
    check("a role the signer may not hold (fabric-coordinator by python-dev-04): refused",
          refused(r, "may not hold the role"), r.stderr)
    branch("no-role")
    commit("python-dev-04", None)
    r = guard()
    check("no Fabric-Role trailer: refused", refused(r, "names no Fabric-Role"), r.stderr)
    branch("ghost")
    commit("python-dev-04", "ghost")
    r = guard()
    check("a role no definition has: refused", refused(r, "no role defined"), r.stderr)

    print("threat model: the signature and its proof")
    branch("unsigned")
    commit(None, "python-dev")
    r = guard()
    check("a commit with no signature: refused", r.returncode == 1 and "1 unsigned commit(s)" in r.stderr, r.stderr)
    j = guard_mod.Judge(env(AGENT_FABRIC_OPERATOR=FABRIC), "ssh")
    try:
        why = j.refusals(REPO, [git("rev-parse", "HEAD").stdout.strip()])
    finally:
        j.close()
    check("  ... and rule 5 alone refuses it too", len(why) == 1 and "no signature" in why[0], str(why))
    branch("no-note")
    commit("python-dev-04", "python-dev", note=False)
    r = guard()
    check("a missing proof note: refused", refused(r, "no timestamp proof"), r.stderr)
    branch("forged")
    first = commit("python-dev-04", "python-dev")
    second = commit("python-dev-04", "python-dev", note=False)
    blob = git("notes", "--ref=refs/notes/fabric-ots", "list", first).stdout.strip()
    git("notes", "--ref=refs/notes/fabric-ots", "add", "-f", "-C", blob, second)
    r = guard()
    check("a note holding another signature's proof (forged for a different signature): refused",
          refused(r, "is not the timestamp proof"), r.stderr)
    branch("doubled")
    sha = commit("python-dev-04", "python-dev")
    held = subprocess.run(["git", "-C", REPO, "notes", "--ref=refs/notes/fabric-ots", "show", sha],
                          capture_output=True, env=env(), check=True).stdout
    new = subprocess.run(["git", "-C", REPO, "hash-object", "-w", "--stdin"], input=held + held, capture_output=True,
                         env=env(), check=True).stdout.decode().strip()
    git("notes", "--ref=refs/notes/fabric-ots", "add", "-f", "-C", new, sha)
    r = guard()
    check("a note of two proofs (git's carry-over shape): refused", refused(r, "is not the timestamp proof"), r.stderr)

    print("threat model: the range")
    branch("shallow-src")
    commit("python-dev-04", "python-dev")
    shallow = os.path.join(T, "shallow")
    subprocess.run(["git", "clone", "-q", "--depth", "1", "--branch", "shallow-src", f"file://{REPO}", shallow],
                   env=env(), capture_output=True, check=True, timeout=60)
    r = guard(cwd=shallow, base="origin/main", AGENT_FABRIC_SIGNING_REPOSITORY=SLUG)
    check("a shallow clone with no base, the repository cut over: refused", refused(r, "cannot be resolved"), r.stdout + r.stderr)
    write_operator(since="0" * 40)
    r = guard()
    check("a since this clone does not have: refused", refused(r, "not in this clone"), r.stderr)

    print("before and at the cut-over")
    write_operator(since=None)
    r = guard(cwd=shallow, base="origin/main", AGENT_FABRIC_SIGNING_REPOSITORY=SLUG)
    check("since null: an unresolvable range is NOT ENFORCED, as it was", r.returncode == 0 and "NOT ENFORCED" in r.stdout,
          r.stdout + r.stderr)
    branch("pre-cut")
    commit("owner", "python-dev", fmt="openpgp", note=False)
    commit("web-dev-01", "fabric-coordinator", note=False)
    r = guard()
    check("since null: a commit rule 5 would refuse passes", passed(r) and "rule 5 not applied" in r.stdout, r.stdout + r.stderr)
    branch("pre-cut-unsigned")
    commit(None, "python-dev")
    r = guard()
    check("since null: an unsigned commit is still refused, as it always was",
          r.returncode == 1 and "1 unsigned commit(s)" in r.stderr, r.stdout + r.stderr)
    branch("pre-cut-ssh")
    commit("web-dev-01", "web-dev")
    r = guard()
    check("since null: an SSH-signed commit is a signed one (git's %G? reads N without allowed signers)",
          passed(r), r.stdout + r.stderr)
    git("checkout", "-q", "pre-cut")
    write_operator(since=old)
    check("(control) the same commits once since is set: refused", guard().returncode == 1)
    branch("reach")
    reached = commit("owner", "python-dev", fmt="openpgp", note=False)
    commit("python-dev-04", "python-dev")
    write_operator(since=reached)
    r = guard()
    check("a commit since reaches (since itself, by the shared key, no proof) passes as it was; the one after is judged",
          passed(r) and "1 judged" in r.stdout, r.stdout + r.stderr)

    print("the policy and the checker's own pieces")
    with open(os.path.join(FABRIC, "policies", "signing.json"), "w", encoding="utf-8") as f:
        f.write("{not json")
    r = guard()
    check("a policy that cannot be read: refused, never read as absent", refused(r, "signing policy cannot be read"), r.stderr)
    write_operator(since=old)
    sig = b"-----BEGIN SSH SIGNATURE-----\nabc\n-----END SSH SIGNATURE-----"
    good = proof_mod.MAGIC + b"\x01\x08" + hashlib.sha256(sig).digest() + b"\x00tail"
    for label, blob in (("the proof of this signature", good), ("another signature's", proof_mod.MAGIC + b"\x01\x08" + hashlib.sha256(sig + b"x").digest()),
                        ("two proofs", good + good), ("not a proof", b"junk"),
                        ("another digest", proof_mod.MAGIC + b"\x01\x08" + b"\x00" * 32)):
        check(f"the checker's proof match agrees with signing/proof.py: {label}",
              guard_mod.proof_matches(sig, blob) == proof_mod.matches(sig, blob))
    check("may_hold: -<n>, a locale suffix, a holder; not another role's -<word>",
          guard_mod.may_hold("python-dev-04", "python-dev", [], []) and guard_mod.may_hold("lc-en", "lc", [], ["en"])
          and guard_mod.may_hold("user", "fabric-coordinator", ["user"], [])
          and not guard_mod.may_hold("python-dev-evil", "python-dev", [], ["en"])
          and not guard_mod.may_hold("web-dev-01", "python-dev", [], []))
    with open(CI, encoding="utf-8") as f:
        ci = f.read()
    check("CI fetches refs/notes/fabric-ots before the checker runs",
          "refs/notes/fabric-ots" in ci and ci.index("refs/notes/fabric-ots") < ci.index("ban_unsigned_commits.py"))


try:
    run()
finally:
    drop_key(GNUPG)
    shutil.rmtree(T, ignore_errors=True)
print("all passed" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
