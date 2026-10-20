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
notes by `fabric-sign note`. A forge key made here (never GitHub's own) stands
in for web-flow: listed in the operator's forge_keys with its file, it signs
the commits rule 8 judges, as git and gpg sign them on the forge. No case
reads this checkout's instance data.

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
SCRATCH = os.path.join(T, "tmp")
os.makedirs(SCRATCH)
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
    # Its own, removed with T: git (2.47, Debian stable) leaves a
    # .git_signing_key_tmp* in $TMPDIR for every commit it signs with a literal
    # SSH key through gpg.ssh.program, which the runner's leak check reports.
    e["TMPDIR"] = SCRATCH
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


FORGE: dict[str, str] = {}   # "fpr": the stand-in forge key's primary, which signs


def make_forge_key() -> None:
    # As web-flow's is: one primary that signs, no subkey.
    gpg("--quick-gen-key", "Forge <forge@example.invalid>", "ed25519", "sign", "never")
    listing = gpg("--with-colons", "--list-keys", "<forge@example.invalid>")
    FORGE["fpr"] = next(l.split(":")[9] for l in listing.splitlines() if l.startswith("fpr:"))


def forge_key_file() -> str:
    return os.path.join(FABRIC, "policies", "forge-keys", f"{FORGE['fpr']}.asc")


def write_operator(since: str | None, fmt: str = "ssh") -> None:
    pol = os.path.join(FABRIC, "policies")
    os.makedirs(os.path.join(pol, "forge-keys"), exist_ok=True)
    with open(os.path.join(pol, "signing.json"), "w", encoding="utf-8") as f:
        json.dump({"default": {"format": "ssh", "since": None},
                   "repositories": {SLUG: {"format": fmt, "since": since}},
                   "forge_keys": {FORGE["fpr"]: "the test's forge"}}, f)
    with open(forge_key_file(), "w", encoding="utf-8") as f:
        f.write(gpg("--armor", "--export", FORGE["fpr"]))
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


def put(name: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.join(REPO, name)), exist_ok=True)
    with open(os.path.join(REPO, name), "w", encoding="utf-8") as f:
        f.write(text)
    git("add", name)


def commit(login: str | None, role: str | None, fmt: str = "ssh", note: bool = True, name: str = "", text: str = "") -> str:
    """A commit on the current branch; login None = unsigned. It adds a file
    of its own unless `name` says which file to write."""
    global _n
    _n += 1
    name = name or f"f{_n}"
    put(name, text or name + "\n")
    msg = f"change {name}" + (f"\n\nFabric-Role: {role}\n" if role else "")
    cfg = sign_cfg(login, fmt) if login else ["-c", "commit.gpgsign=false"]
    git(*cfg, "commit", "-q", "-m", msg)
    sha = git("rev-parse", "HEAD").stdout.strip()
    if login and note:
        subprocess.run([SIGN, "note", sha], cwd=REPO, env=env(), capture_output=True, timeout=60, check=True)
    return sha


def branch(name: str) -> None:
    git("checkout", "-q", "-B", name, "main")


def forge_cfg(key: str = "") -> list[str]:
    """git signing as the forge does: OpenPGP, plain gpg, no fabric-sign, no proof."""
    return ["-c", "gpg.format=openpgp", "-c", "gpg.program=gpg", "-c", f"user.signingkey={key or FORGE['fpr']}!",
            "-c", "commit.gpgsign=true"]


def advance_main(**files: str) -> None:
    """main moves on under a branch, as it does before "Update branch"."""
    here = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    git("checkout", "-q", "main")
    if files:
        for name, text in files.items():
            put(name, text)
        git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "main moves")
    else:
        commit(None, None)
    git("checkout", "-q", here)


def forge_merge(*heads: str, key: str = "", **extra: str) -> str:
    git(*forge_cfg(key), "merge", "-q", "--no-ff", "-m", f"Merge {' '.join(heads)}", *heads, **extra)
    return git("rev-parse", "HEAD").stdout.strip()


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
    agent("devex-child", "devex-tooling")    # certified by its parent before the parent was revoked
    agent("owner", None)     # the shared key's stand-in: signs, in no lineage
    make_forge_key()
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

    branch("revoked-parent")
    commit("devex-child", "devex-tooling")
    r = guard()
    check("a good key under a revoked ancestor: refused", refused(r, "devex-child") or refused(r, AGENTS["devex-child"]["id"]), r.stderr)
    check("  ... and the refusal names the revoked ancestor",
          f"ancestor {AGENTS['devex-tooling']['id']} is revoked" in r.stderr, r.stderr)

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
    git("checkout", "-q", "main")
    reached = commit("owner", "python-dev", fmt="openpgp", note=False)
    branch("reach")
    commit("python-dev-04", "python-dev")
    write_operator(since=reached)
    r = guard()
    check("a commit since reaches (since itself, by the shared key, no proof) passes as it was; the one after is judged",
          passed(r) and "1 judged" in r.stdout, r.stdout + r.stderr)
    branch("side-since")
    stray = commit("owner", "python-dev", fmt="openpgp", note=False)
    commit("python-dev-04", "python-dev")
    write_operator(since=stray)
    r = guard()
    check("a since on a side branch, not on the default branch: refused, naming the sha",
          refused(r, "not an ancestor") and stray in r.stderr and "fetch the remote first" in r.stderr, r.stdout + r.stderr)
    write_operator(since=old)

    print("log.showSignature=true in the clone")
    write_operator(since=old, fmt="openpgp")
    git("config", "log.showSignature", "true")
    try:
        branch("show-sig")
        good_sha = commit("python-dev-04", "python-dev", fmt="openpgp")
        bad_sha = commit(None, "python-dev")
        found = guard_mod.unsigned(REPO, "main..HEAD")
        check("unsigned lists exactly the unsigned commit, no verification line in the way",
              [s for s, _ in found] == [bad_sha[:10]], found)
        j = guard_mod.Judge(env(AGENT_FABRIC_OPERATOR=FABRIC), "openpgp")
        try:
            why = j.refusals(REPO, [good_sha, bad_sha])
        finally:
            j.close()
        check("  ... and rule 5 passes the signed one, refuses the other for having no signature",
              len(why) == 1 and why[0].startswith(bad_sha[:10]) and "no signature" in why[0], why)
        branch("show-sig-ok")
        commit("python-dev-04", "python-dev", fmt="openpgp")
        r = guard()
        check("  ... and the entry point passes a good branch", passed(r), r.stdout + r.stderr)
    finally:
        git("config", "--unset", "log.showSignature")
        write_operator(since=old)

    print("rule 8: a commit the forge makes (the repository signs ssh; the forge signs OpenPGP)")
    write_operator(since=old)
    branch("forge-update")
    commit("python-dev-04", "python-dev")
    advance_main()
    forge_merge("main")
    r = guard()
    check("a forge-signed clean merge of two parents (Update branch), no trailer, no proof: passes",
          passed(r) and "2 judged" in r.stdout, r.stdout + r.stderr)

    branch("forge-own")
    commit("python-dev-04", "python-dev")
    advance_main()
    git("merge", "-q", "--no-ff", "--no-commit", "main")
    put("own-change", "slipped in\n")
    git(*forge_cfg(), "commit", "-q", "-m", "Merge branch 'main'")
    r = guard()
    check("a forge merge that changes something itself: refused", refused(r, "changes something itself"), r.stdout + r.stderr)

    branch("forge-conflict")
    commit("python-dev-04", "python-dev", name="contested", text="branch\n")
    advance_main(contested="main\n")
    git("merge", "-q", "--no-ff", "main", check_ok=False)
    put("contested", "resolved on the web\n")
    git(*forge_cfg(), "commit", "-q", "-m", "Merge branch 'main'")
    r = guard()
    check("a forge merge of parents that conflict (resolved in the web editor): refused",
          refused(r, "do not merge cleanly"), r.stdout + r.stderr)

    branch("forge-octopus")
    commit("python-dev-04", "python-dev")
    for side in ("oct-a", "oct-b"):
        git("checkout", "-q", "-B", side, "main")
        commit("python-dev-04", "python-dev")
    git("checkout", "-q", "forge-octopus")
    forge_merge("oct-a", "oct-b")
    r = guard()
    check("a forge-signed octopus merge, clean: refused", refused(r, "octopus"), r.stdout + r.stderr)

    git("checkout", "-q", "--orphan", "forge-root")
    git("rm", "-q", "-r", "-f", ".")
    put("root", "root\n")
    git(*forge_cfg(), "commit", "-q", "-m", "Initial commit")
    r = guard()
    check("a forge-signed root commit: refused", refused(r, "root commit"), r.stdout + r.stderr)

    bot = {"GIT_AUTHOR_NAME": "dependabot[bot]", "GIT_AUTHOR_EMAIL": "49699333+dependabot[bot]@users.noreply.github.com"}
    branch("dependabot")
    put(".github/workflows/ci.yml", "uses: actions/checkout@" + "1" * 40 + "\n")
    git(*forge_cfg(), "commit", "-q", "-m", "Bump actions/checkout", **bot)
    r = guard()
    check("a forge-signed Dependabot commit changing only .github/workflows/: passes", passed(r), r.stdout + r.stderr)
    branch("dependabot-wide")
    put(".github/workflows/ci.yml", "uses: actions/checkout@" + "2" * 40 + "\n")
    put("README", "and this\n")
    git(*forge_cfg(), "commit", "-q", "-m", "Bump actions/checkout", **bot)
    r = guard()
    check("a forge-signed Dependabot commit touching a path outside .github/workflows/: refused",
          refused(r, "README") and "outside .github/workflows/" in r.stderr, r.stdout + r.stderr)
    branch("dependabot-empty")
    git(*forge_cfg(), "commit", "-q", "--allow-empty", "-m", "Bump nothing", **bot)
    r = guard()
    check("a forge-signed Dependabot commit that changes nothing: refused", refused(r, "changing nothing"),
          r.stdout + r.stderr)
    branch("dependabot-merge")
    commit("python-dev-04", "python-dev")
    advance_main()
    git("merge", "-q", "--no-ff", "--no-commit", "main")
    put(".github/workflows/ci.yml", "uses: actions/checkout@" + "3" * 40 + "\n")
    git(*forge_cfg(), "commit", "-q", "-m", "Merge branch 'main'", **bot)
    r = guard()
    check("a forge-signed merge authored by Dependabot, changing only workflows itself: refused",
          refused(r, "changes something itself") and "not a merge" in r.stderr, r.stdout + r.stderr)

    branch("forge-edit")
    put("edited-on-the-web", "x\n")
    git(*forge_cfg(), "commit", "-q", "-m", "Update edited-on-the-web")
    r = guard()
    check("a forge-signed plain commit by the shared author (a web edit, a squash): refused",
          refused(r, "made on the forge"), r.stdout + r.stderr)

    branch("forge-unlisted")
    commit("python-dev-04", "python-dev")
    advance_main()
    sha = forge_merge("main", key=AGENTS["owner"]["sub"])
    r = guard()
    check("a clean merge signed by an OpenPGP key forge_keys does not list: refused",
          r.returncode == 1 and sha[:10] in r.stderr and "1 of 2" in r.stderr, r.stdout + r.stderr)
    write_operator(since=old, fmt="openpgp")
    r = guard()
    check("  ... and where the repository signs OpenPGP too",
          refused(r, "not signed by an agent's signing subkey") and sha[:10] in r.stderr, r.stdout + r.stderr)
    write_operator(since=old)
    # A key the checker's keyring holds and verifies (G/U), so only the
    # forge_keys list stands between it and rule 8's clean-merge pass.
    branch("forge-unlisted-known")
    commit("python-dev-04", "python-dev")
    advance_main()
    sha = forge_merge("main", key=AGENTS["python-dev-04"]["sub"])
    r = guard()
    check("a clean merge signed by a key the checker verifies but forge_keys does not list (an agent's): refused",
          r.returncode == 1 and sha[:10] in r.stderr and "1 of 2" in r.stderr, r.stdout + r.stderr)

    branch("forge-absent")
    commit("python-dev-04", "python-dev")
    advance_main()
    sha = forge_merge("main")
    os.remove(forge_key_file())
    r = guard()
    check("a listed forge key whose file is absent: its clean merge refused, the agent's commit still passes",
          refused(r, "listed in forge_keys but not loaded") and sha[:10] in r.stderr and "1 of 2" in r.stderr,
          r.stdout + r.stderr)
    with open(forge_key_file(), "w", encoding="utf-8") as f:
        f.write(gpg("--armor", "--export", AGENTS["owner"]["primary"]))
    r = guard()
    check("a listed forge key whose file is another key: its clean merge refused, the agent's commit still passes",
          refused(r, "not that key alone") and "1 of 2" in r.stderr, r.stdout + r.stderr)
    write_operator(since=old)
    git("checkout", "-q", "main")

    print("the policy and the checker's own pieces")
    with open(os.path.join(FABRIC, "policies", "signing.json"), "w", encoding="utf-8") as f:
        f.write("{not json")
    r = guard()
    check("a policy that cannot be read: refused, never read as absent", refused(r, "signing policy cannot be read"), r.stderr)
    write_operator(since=old)
    os.remove(os.path.join(FABRIC, "policies", "authority.json"))
    j = guard_mod.Judge(env(AGENT_FABRIC_OPERATOR=FABRIC), "ssh")
    try:
        check("a missing authority.json refuses, naming why (no holder is read as none listed)",
              "policies/authority.json cannot be read" in j.global_problem, j.global_problem)
    finally:
        j.close()
    write_operator(since=old)
    # A parsed file that lists no usable owner definition must not drop the
    # owner role to the name convention (fabric-coordinator-2 would hold it).
    for label, body in (("absent", {}), ("null", {"role_definitions": None}), ("an empty list", {"role_definitions": []}),
                        ("no role", {"role_definitions": {"holders": ["user"]}}),
                        ("an empty role", {"role_definitions": {"role": "", "holders": ["user"]}}),
                        ("a list entry with no role", {"role_definitions": [{"holders": ["user"]}]})):
        with open(os.path.join(FABRIC, "policies", "authority.json"), "w", encoding="utf-8") as f:
            json.dump(body, f)
        j = guard_mod.Judge(env(AGENT_FABRIC_OPERATOR=FABRIC), "ssh")
        try:
            listed = j.holders.get("fabric-coordinator")
            by_list = listed is not None and "fabric-coordinator-2" not in listed
            decides = bool(j.global_problem) or ("user" in listed and by_list if label.startswith(("no role", "an empty role", "a list")) else False)
            check(f"role_definitions {label}: refuses or decides by the list, never by the name",
                  by_list and decides and not guard_mod.may_hold("fabric-coordinator-2", "fabric-coordinator", listed, []),
                  (listed, j.global_problem))
        finally:
            j.close()
    # A role named with no usable holders list is listed and held by nobody.
    for label, extra in (("no holders", {"role": "python-dev"}), ("holders a string", {"role": "python-dev", "holders": "user"})):
        with open(os.path.join(FABRIC, "policies", "authority.json"), "w", encoding="utf-8") as f:
            json.dump({"role_definitions": [{"role": "fabric-coordinator", "holders": ["user"]}, extra]}, f)
        j = guard_mod.Judge(env(AGENT_FABRIC_OPERATOR=FABRIC), "ssh")
        try:
            listed = j.holders.get("python-dev")
            check(f"a named role with {label}: listed, held by nobody", listed == [] and not guard_mod.may_hold("python-dev-3", "python-dev", listed, []), listed)
        finally:
            j.close()
    write_operator(since=old)
    sig = b"-----BEGIN SSH SIGNATURE-----\nabc\n-----END SSH SIGNATURE-----"
    good = proof_mod.MAGIC + b"\x01\x08" + hashlib.sha256(sig).digest() + b"\x00tail"
    for label, blob in (("the proof of this signature", good), ("another signature's", proof_mod.MAGIC + b"\x01\x08" + hashlib.sha256(sig + b"x").digest()),
                        ("two proofs", good + good), ("not a proof", b"junk"),
                        ("another digest", proof_mod.MAGIC + b"\x01\x08" + b"\x00" * 32)):
        check(f"the checker's proof match agrees with signing/proof.py: {label}",
              guard_mod.proof_matches(sig, blob) == proof_mod.matches(sig, blob))
    check("may_hold: -<n>, a locale suffix, a holder; not another role's -<word>",
          guard_mod.may_hold("python-dev-04", "python-dev", None, []) and guard_mod.may_hold("lc-en", "lc", None, ["en"])
          and guard_mod.may_hold("user", "fabric-coordinator", ["user"], [])
          and not guard_mod.may_hold("fabric-coordinator-2", "fabric-coordinator", ["user"], [])
          and not guard_mod.may_hold("fabric-coordinator", "fabric-coordinator", ["user"], [])
          and not guard_mod.may_hold("fabric-coordinator-en", "fabric-coordinator", ["user"], ["en"])
          and not guard_mod.may_hold("python-dev-evil", "python-dev", None, ["en"])
          and not guard_mod.may_hold("web-dev-01", "python-dev", None, []))
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
