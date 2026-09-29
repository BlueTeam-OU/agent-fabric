#!/usr/bin/env python3
"""tools/fabric/secret_store.py — an agent's own encrypted secrets
(agent-fabric ADR-038), behind `fabric-secrets store …`.

    fabric-secrets store init [--remote URL]     in the account: its key and its store
    fabric-secrets store set NAME                the agent writes an entry (value on stdin)
    fabric-secrets store export-key              the agent's PUBLIC key, armored (for its parent)
    fabric-secrets store push                    the store to its remote
    fabric-secrets store names [--json]          the entries, by name
    fabric-secrets store put LOGIN NAME [--store DIR]
                                                 the parent writes into a child's store
                                                 (value on stdin; the child's committed key)
    fabric-secrets store certify LOGIN KEYFILE | --root
                                                 the parent attests a child's key
    fabric-secrets store verify                  every committed key against its lineage
    fabric-secrets store paper [--out FILE]      the key and its revocation, for the owner
    fabric-secrets store import-doppler          this login's Doppler config into its store
                                                 (the migration, ADR-038 §5 rule 8)
    fabric-secrets store template-set SLUG       a Claude account's setup-token into this
                                                 (the coordinator's) store (value on stdin)
    fabric-secrets store templates [--json]      the templates, by fingerprint
    fabric-secrets store assign SLUG LOGIN...    each login's store gets the template's token
                                                 (ADR-031, through its parent)

The store is a git repository in the layout pass(1) reads, so QtPass and
browserpass open it: `.gpg-id` names the key, and each secret is
`env/<NAME>.gpg`, its value on the first line. It is encrypted to the
agent's key alone. Anyone holding the committed public key can add an
entry, and only the agent can read one: the parent writes and never reads.

A key is an agent's when its public half is committed at
`identities/keys/<login>.asc` with its parent's certification, and
`identities/keys/lineage.json` records that parent. Placement is not
part of it: no host is named anywhere, and nothing here needs the
parent and the child on one machine. They meet only through git.

No function here prints a secret value. `values()` returns them to the
caller in-process (fabric-secrets sync); everything else deals in names,
fingerprints and paths.
"""
from __future__ import annotations

import argparse
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FABRIC_ROOT = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(os.path.dirname(HERE))
NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
LOGIN_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
UID_DOMAIN = "agents.agent-fabric"


class StoreError(Exception):
    """A refusal or a failure; the message is the whole answer and never a value."""


def login() -> str:
    return pwd.getpwuid(os.getuid()).pw_name


def home() -> str:
    return os.environ.get("HOME") or pwd.getpwuid(os.getuid()).pw_dir


def store_dir() -> str:
    return os.environ.get("AGENT_FABRIC_SECRET_STORE") or os.path.join(home(), ".local", "share", "agent-fabric", "secrets")


def children_dir() -> str:
    return os.path.join(home(), ".local", "share", "agent-fabric", "children")


def keys_dir(fabric: str | None = None) -> str:
    return os.path.join(fabric or FABRIC_ROOT, "identities", "keys")


def _run(cmd: list[str], *, stdin: bytes | None = None, cwd: str | None = None,
         env: dict | None = None, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, input=stdin, capture_output=True, cwd=cwd, env=env)
    if check and r.returncode != 0:
        # The last line of stderr that is not git's advice ("hint:"), which
        # gpg and git keep free of values; the error, not the suggestion.
        lines = [l for l in r.stderr.decode(errors="replace").strip().splitlines() if not l.startswith("hint:")]
        why = (lines or [f"exit {r.returncode}"])[-1]
        raise StoreError(f"{os.path.basename(cmd[0])} {cmd[1] if len(cmd) > 1 else ''}: {why}")
    return r


def gpg(*args: str, stdin: bytes | None = None, homedir: str | None = None, check: bool = True):
    cmd = ["gpg", "--batch", "--yes", "--no-tty", "--pinentry-mode", "loopback", "--passphrase", ""]
    if homedir:
        cmd += ["--homedir", homedir]
    return _run(cmd + list(args), stdin=stdin, check=check)


def git(store: str, *args: str, check: bool = True):
    return _run(["git", "-C", store, *args], check=check)


def fingerprints(homedir: str | None = None, *, secret: bool = False, query: str | None = None) -> list[str]:
    args = ["--with-colons", "--list-secret-keys" if secret else "--list-keys"] + ([query] if query else [])
    r = gpg(*args, homedir=homedir, check=False)
    out, prev = [], None
    for line in r.stdout.decode().splitlines():
        f = line.split(":")
        if f[0] in ("pub", "sec"):
            prev = f[0]
        elif f[0] == "fpr" and prev:
            out.append(f[9])
            prev = None
    return out


def key_of_store(store: str | None = None) -> str:
    try:
        with open(os.path.join(store or store_dir(), ".gpg-id"), encoding="utf-8") as fh:
            fpr = fh.read().split()[0]
    except (OSError, IndexError):
        raise StoreError(f"no store at {store or store_dir()} (fabric-secrets store init)")
    return fpr


# ── the agent, in its own account ─────────────────────────────────────
def init(remote: str | None = None) -> dict:
    """The agent's key (made here, with no passphrase: agents decrypt
    unattended) and its store. Idempotent: an existing key or store is
    kept, never replaced."""
    me, store = login(), store_dir()
    uid = f"{me} <{me}@{UID_DOMAIN}>"
    fpr = next(iter(fingerprints(secret=True, query=f"={uid}")), None)
    made = False
    if not fpr:
        gpg("--quick-gen-key", uid, "ed25519", "cert,sign", "never")
        fpr = fingerprints(secret=True, query=f"={uid}")[0]
        gpg("--quick-add-key", fpr, "cv25519", "encr", "never")
        made = True
    os.makedirs(os.path.join(store, "env"), mode=0o700, exist_ok=True)
    if not os.path.isdir(os.path.join(store, ".git")):
        git(store, "init", "-q", "-b", "main")
    gpg_id = os.path.join(store, ".gpg-id")
    if os.path.exists(gpg_id) and key_of_store(store) != fpr:
        raise StoreError(f"{gpg_id} names another key; re-keying is a rotation, not an init")
    with open(gpg_id, "w", encoding="utf-8") as fh:
        fh.write(fpr + "\n")
    git(store, "add", ".gpg-id")
    if git(store, "diff", "--cached", "--quiet", check=False).returncode:
        _commit(store, f"agent {me}: the store is encrypted to {fpr}")
    if remote:
        if git(store, "remote", check=False).stdout.strip():
            git(store, "remote", "set-url", "origin", remote)
        else:
            git(store, "remote", "add", "origin", remote)
    return {"login": me, "fingerprint": fpr, "key_made": made, "store": store}


def export_key(fpr: str | None = None, homedir: str | None = None) -> str:
    return gpg("--armor", "--export", fpr or key_of_store(), homedir=homedir).stdout.decode()


def _git_env() -> dict:
    """The store's own identity for every commit it makes, a rebase's
    included: the writing login, whatever the account's git config says
    (a new account may have none yet)."""
    return {**os.environ, "GIT_AUTHOR_NAME": login(), "GIT_AUTHOR_EMAIL": f"{login()}@{UID_DOMAIN}",
            "GIT_COMMITTER_NAME": login(), "GIT_COMMITTER_EMAIL": f"{login()}@{UID_DOMAIN}"}


def _commit(store: str, message: str) -> None:
    # The store's commits are its own history, attributed by message:
    # the writer ("agent <login>" or "parent <login>") and what changed,
    # never a value.
    _run(["git", "-C", store, "-c", "commit.gpgsign=false", "commit", "-q", "-m", message], env=_git_env())


def _check_name(name: str) -> None:
    if not NAME_RE.match(name):
        raise StoreError(f"{name!r} is not a secret name (UPPER_SNAKE, as an environment variable)")


def _one_line_off(value: bytes) -> bytes:
    """A value typed or piped on stdin: one trailing newline is the
    terminal's, not the secret's."""
    return value[:-1] if value.endswith(b"\n") else value


def _write_entry(store: str, name: str, value: bytes, recipient_args: list[str]) -> str:
    """The value EXACTLY as given, multi-line and empty included: sync
    must apply from the store what it applied from Doppler (a PEM key is
    many lines). A single-line value is pass's shape as it is: the
    secret on the first line. --no-encrypt-to: a gpg.conf naming an extra
    recipient never adds one."""
    _check_name(name)
    path = os.path.join(store, "env", f"{name}.gpg")
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    gpg("--trust-model", "always", "--no-encrypt-to", "--encrypt", *recipient_args, "--output", path + ".tmp",
        stdin=value)
    os.replace(path + ".tmp", path)
    git(store, "add", os.path.relpath(path, store))
    return path


def _decrypt(path: str) -> str | None:
    r = gpg("--decrypt", path, check=False)
    return r.stdout.decode() if r.returncode == 0 else None


def _remote(store: str) -> bool:
    return bool(git(store, "remote", check=False).stdout.strip())


def _branch(store: str) -> str:
    return git(store, "rev-parse", "--abbrev-ref", "HEAD", check=False).stdout.decode().strip() or "main"


def _before_write(store: str) -> None:
    """The store is brought up to its remote before anything is written:
    the agent and its parent both write, and a write on a stale copy is a
    divergence. One file per entry, so a rebase never conflicts on two
    different names. A failure stops the write, loudly."""
    if not _remote(store):
        return
    r = _run(["git", "-C", store, "-c", "commit.gpgsign=false", "pull", "-q", "--rebase", "origin", _branch(store)],
             env=_git_env(), check=False)
    if r.returncode != 0:
        lines = [l for l in r.stderr.decode(errors="replace").splitlines() if l.strip() and not l.startswith("hint:")]
        raise StoreError("the store could not be brought up to its remote; nothing written: " + (lines or ["?"])[-1])


def _after_commit(store: str) -> None:
    """Every commit reaches the remote: it is the backup and the channel
    between the agent and its parent."""
    if _remote(store):
        git(store, "push", "-q", "origin", f"HEAD:{_branch(store)}")


def set_entry(name: str, value: bytes, *, exact: bool = False) -> dict:
    """The agent writes its own entry. From stdin one trailing newline is
    dropped (exact=False); an in-process caller passes the value as it
    is. GPG encryption is randomised, so "unchanged" is decided on the
    decrypted value, which the agent can read (a parent cannot: see assign)."""
    store = store_dir()
    fpr = key_of_store(store)
    _check_name(name)
    value = value if exact else _one_line_off(value)
    _before_write(store)
    path = os.path.join(store, "env", f"{name}.gpg")
    if os.path.exists(path) and _decrypt(path) == value.decode(errors="replace"):
        return {"name": name, "changed": False}
    _write_entry(store, name, value, ["--recipient", fpr])
    changed = git(store, "diff", "--cached", "--quiet", check=False).returncode != 0
    if changed:
        _commit(store, f"agent {login()}: set {name}")
        _after_commit(store)
    return {"name": name, "changed": changed}


def names(store: str | None = None) -> list[str]:
    d = os.path.join(store or store_dir(), "env")
    try:
        return sorted(f[:-4] for f in os.listdir(d) if f.endswith(".gpg") and NAME_RE.match(f[:-4]))
    except FileNotFoundError:
        return []


def pull(store: str | None = None) -> None:
    """The store brought up to its remote, when it has one; a failure is
    an error (StoreError), never a note: a sync that read a stale copy
    would apply less than the store holds and still say applied."""
    _before_write(store or store_dir())


def values(store: str | None = None) -> dict[str, str]:
    """Every entry, decrypted, for fabric-secrets sync. In-process only:
    nothing here prints or logs a value."""
    store = store or store_dir()
    key_of_store(store)
    out = {}
    for name in names(store):
        r = gpg("--decrypt", os.path.join(store, "env", f"{name}.gpg"))
        out[name] = r.stdout.decode()   # exactly as written: many lines, or none
    return out


def import_doppler() -> dict:
    """Every name of this login's own Doppler config into its store, in
    one commit, for the migration. The config is found exactly as
    fabric-secrets finds it (AGENT_FABRIC_SECRETS_CONFIG, else the one
    recorded at scope /). Values stay in this process."""
    store = store_dir()
    fpr = key_of_store(store)
    project = os.environ.get("AGENT_FABRIC_SECRETS_PROJECT", "agent-fabric")
    config = os.environ.get("AGENT_FABRIC_SECRETS_CONFIG")
    if not config:
        r = _run(["doppler", "configure", "get", "enclave.config", "--plain", "--scope", "/"], check=False)
        config = r.stdout.decode().strip() if r.returncode == 0 else ""
    if not config:
        raise StoreError("no Doppler config recorded for this login; nothing to import")
    r = _run(["doppler", "secrets", "download", "--no-file", "--format", "json",
              "--project", project, "--config", config])
    try:
        data = json.loads(r.stdout)
    except ValueError:
        raise StoreError("doppler returned no JSON")
    _before_write(store)
    imported, skipped = [], []
    for name, value in sorted(data.items()):
        if name.startswith("DOPPLER_"):
            continue   # Doppler's own, never the login's
        if not isinstance(value, str) or not NAME_RE.match(name):
            skipped.append(name)   # said, never dropped silently
            continue
        _write_entry(store, name, value.encode(), ["--recipient", fpr])
        imported.append(name)
    if git(store, "diff", "--cached", "--quiet", check=False).returncode:
        _commit(store, f"agent {login()}: imported {len(imported)} name(s) from Doppler {project}/{config}")
    _after_commit(store)
    return {"imported": imported, "skipped": skipped, "config": config}


# ── the parent ────────────────────────────────────────────────────────
def lineage(fabric: str | None = None) -> dict:
    try:
        with open(os.path.join(keys_dir(fabric), "lineage.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}


def _write_lineage(doc: dict, fabric: str | None = None) -> None:
    path = os.path.join(keys_dir(fabric), "lineage.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    os.replace(path + ".tmp", path)


def _key_file_fingerprint(path: str) -> str:
    """The primary fingerprint of an armored public key file, read in a
    throwaway keyring: nothing is imported into the caller's."""
    with tempfile.TemporaryDirectory() as tmp:
        os.chmod(tmp, 0o700)
        try:
            gpg("--import", path, homedir=tmp)
            fprs = fingerprints(homedir=tmp)
        finally:
            _run(["gpgconf", "--homedir", tmp, "--kill", "all"], check=False)
    if len(fprs) != 1:
        raise StoreError(f"{path}: {len(fprs)} keys, not one")
    return fprs[0]


def put(child: str, name: str, value: bytes, store: str | None = None, fabric: str | None = None,
        *, exact: bool = False) -> dict:
    """The parent writes an entry into a child's store: encrypted to the
    child's COMMITTED key (never imported), which must be the key the
    store says it is encrypted to. The parent cannot read what it wrote."""
    if not LOGIN_RE.match(child):
        raise StoreError(f"{child!r} is not a login")
    key_file = os.path.join(keys_dir(fabric), f"{child}.asc")
    if not os.path.exists(key_file):
        raise StoreError(f"no committed key for {child} ({key_file})")
    store = store or os.path.join(children_dir(), child)
    _check_name(name)
    # Brought up to date FIRST: a mirror still naming the old key must not
    # pass the check and then receive a re-keyed .gpg-id with the pull.
    _before_write(store)
    committed = _key_file_fingerprint(key_file)
    if key_of_store(store) != committed:
        raise StoreError(f"{child}'s store is encrypted to another key than the committed one; "
                         "a store and its key must agree before anything is written")
    _write_entry(store, name, value if exact else _one_line_off(value), ["--recipient-file", key_file])
    changed = git(store, "diff", "--cached", "--quiet", check=False).returncode != 0
    if changed:
        _commit(store, f"parent {login()}: put {name}")
        _after_commit(store)
    return {"child": child, "name": name, "changed": changed}


def certify(child: str | None, key_file: str | None, fabric: str | None = None) -> dict:
    """The parent attests a child's key with its own (the birth
    certificate), and commits the certified public half and the lineage.
    --root: the coordinator records its own key, with no parent."""
    me, doc = login(), lineage(fabric)
    my_fpr = key_of_store()
    kd = keys_dir(fabric)
    os.makedirs(kd, exist_ok=True)
    if child is None:
        with open(os.path.join(kd, f"{me}.asc"), "w", encoding="utf-8") as fh:
            fh.write(export_key(my_fpr))
        doc[me] = {"fingerprint": my_fpr, "parent": None}
        _write_lineage(doc, fabric)
        return {"login": me, "fingerprint": my_fpr, "parent": None}
    if not LOGIN_RE.match(child) or child == me:
        raise StoreError(f"{child!r} is not another login")
    fpr = _key_file_fingerprint(key_file)
    # The key's user id is not checked against the login: what makes the
    # key the login's is this certification and the committed file under
    # its name (ADR-038 §5 rule 2), and a test cannot make a second Unix
    # user to name one — a hook that set the login would be the very thing
    # the identity invariant forbids.
    gpg("--import", key_file)
    gpg("--default-key", my_fpr, "--quick-sign-key", fpr)
    with open(os.path.join(kd, f"{child}.asc"), "w", encoding="utf-8") as fh:
        fh.write(export_key(fpr))
    doc[child] = {"fingerprint": fpr, "parent": me}
    _write_lineage(doc, fabric)
    return {"login": child, "fingerprint": fpr, "parent": me}


def verify(fabric: str | None = None) -> list[str]:
    """Every committed key against lineage.json, each on its own:
    - lineage: exactly one root (parent null), nobody its own parent,
      and every chain reaching that root without a cycle;
    - `<login>.asc` holds exactly one primary key, the recorded one;
    - a child's key carries a valid certification by its PARENT's
      recorded key, read in a keyring holding only the child's file and
      the parent's, so a certification found in another file, or a
      swapped or doubled file, never passes.
    Findings, one line each; [] is clean."""
    doc, kd, findings = lineage(fabric), keys_dir(fabric), []
    if not os.path.isdir(kd):
        return []
    files = {f[:-4] for f in os.listdir(kd) if f.endswith(".asc")}
    for extra in sorted(files - set(doc)):
        findings.append(f"identities/keys/{extra}.asc: no lineage.json entry")
    roots = sorted(w for w, r in doc.items() if (r or {}).get("parent") is None)
    if doc and len(roots) != 1:
        findings.append(f"identities/keys/lineage.json: {len(roots)} roots ({', '.join(roots) or 'none'}); "
                        "the chain has exactly one, the coordinator's key")
    for who, rec in sorted(doc.items()):
        parent = (rec or {}).get("parent")
        if parent == who:
            findings.append(f"identities/keys/lineage.json: {who} is its own parent")
            continue
        seen, at = {who}, parent
        while at is not None:
            if at in seen or at not in doc:
                findings.append(f"identities/keys/lineage.json: {who}'s chain "
                                + ("loops" if at in seen else f"names {at}, who has no entry") + "; it must reach the root")
                break
            seen.add(at)
            at = (doc.get(at) or {}).get("parent")

    def keyring_check(who: str, fpr: str, parent: str | None) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.chmod(tmp, 0o700)
            try:
                gpg("--import", os.path.join(kd, f"{who}.asc"), homedir=tmp, check=False)
                held = fingerprints(homedir=tmp)
                if held != [fpr]:
                    findings.append(f"identities/keys/{who}.asc: holds {len(held)} key(s), "
                                    f"{'not the recorded ' + fpr if fpr not in held else 'not only the recorded one'}")
                    return
                if parent is None:
                    return
                pfpr = (doc.get(parent) or {}).get("fingerprint")
                if not pfpr or parent not in files:
                    findings.append(f"identities/keys/{who}.asc: parent {parent} has no recorded, committed key")
                    return
                gpg("--import", os.path.join(kd, f"{parent}.asc"), homedir=tmp, check=False)
                if pfpr not in fingerprints(homedir=tmp):
                    findings.append(f"identities/keys/{parent}.asc: does not hold its recorded key")
                    return
                r = gpg("--with-colons", "--check-sigs", fpr, homedir=tmp, check=False)
                good = any(l.startswith("sig:!:") and l.split(":")[4] == pfpr[-16:] for l in r.stdout.decode().splitlines())
                if not good:
                    findings.append(f"identities/keys/{who}.asc: not certified by its parent {parent}'s key")
            finally:
                _run(["gpgconf", "--homedir", tmp, "--kill", "all"], check=False)

    for who, rec in sorted(doc.items()):
        if who not in files:
            findings.append(f"identities/keys/lineage.json: {who} has no committed key")
            continue
        if (rec or {}).get("parent") == who:
            continue
        keyring_check(who, (rec or {}).get("fingerprint"), (rec or {}).get("parent"))
    return findings


# ── the Claude-account templates (ADR-031), in the coordinator's store ─
TEMPLATE_PREFIX = "CLAUDE_ACCOUNT_"
ASSIGNED_PREFIX = "CLAUDE_ASSIGNED_"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def _slug_name(slug: str) -> str:
    if not SLUG_RE.match(slug):
        raise StoreError(f"{slug!r} is not an account slug (lowercase, digits, dashes)")
    return TEMPLATE_PREFIX + slug.upper().replace("-", "_")


def _login_name(who: str) -> str:
    if not LOGIN_RE.match(who) or "_" in who:
        raise StoreError(f"{who!r} is not a login this store can record (no underscores)")
    return ASSIGNED_PREFIX + who.upper().replace("-", "_")


def _sha12(v: str) -> str:
    import hashlib
    return hashlib.sha256(v.encode()).hexdigest()[:12]


def template_set(slug: str, value: bytes) -> dict:
    return set_entry(_slug_name(slug), value)


def templates() -> list[dict]:
    """Each template by its account and its token's fingerprint: the
    value goes into a hash and nowhere else."""
    vals = values()
    return [{"account": n[len(TEMPLATE_PREFIX):].lower().replace("_", "-"), "token_sha256_12": _sha12(v) if v else None}
            for n, v in sorted(vals.items()) if n.startswith(TEMPLATE_PREFIX)]


def assign(slug: str, logins: list[str], *, force: bool = False) -> list[dict]:
    """The template's token into each login's store, as its
    CLAUDE_CODE_OAUTH_TOKEN, written by the parent (which cannot read it
    back); the assignment is recorded in the parent's own store, since
    the parent cannot read the child's."""
    vals = values()
    name = _slug_name(slug)
    if not vals.get(name):
        raise StoreError(f"{slug} is not a template in this store (fabric-secrets store templates)")
    rows = []
    fp = _sha12(vals[name])
    for who in logins:
        rec = _login_name(who)
        # The parent's record is "<slug> <fingerprint>": the parent cannot
        # read the child's entry, so whether the child already holds this
        # token is decided here, by what the parent last wrote.
        was, _, was_fp = (vals.get(rec) or "none").partition(" ")
        if was == slug and was_fp == fp and not force:
            rows.append({"login": who, "from": was, "to": slug, "status": "unchanged", "token_sha256_12": fp})
            continue
        try:
            put(who, "CLAUDE_CODE_OAUTH_TOKEN", vals[name].encode(), exact=True)
            set_entry(rec, f"{slug} {fp}".encode(), exact=True)
            rows.append({"login": who, "from": was, "to": slug, "status": "written", "token_sha256_12": fp})
        except StoreError as e:
            rows.append({"login": who, "from": was, "status": "failed", "reason": str(e)[:160]})
    return rows


# ── the owner's sheet ─────────────────────────────────────────────────
def paper(out: str | None = None) -> None:
    """The agent's secret key as paperkey text, and its revocation
    certificate, for the owner to print once. Refused inside a model
    session: a secret is never shown to a model."""
    if os.environ.get("CLAUDECODE"):
        raise StoreError("refused inside a model session (CLAUDECODE is set): the owner runs this in a terminal")
    if out is None and not sys.stdout.isatty():
        raise StoreError("stdout is not a terminal: pass --out FILE (written 0600) to print it from there")
    if not shutil.which("paperkey"):
        raise StoreError("paperkey is not installed (runtime/provisioning/platform installs it)")
    fpr = key_of_store()
    secret = gpg("--export-secret-keys", fpr).stdout
    sheet = _run(["paperkey", "--output-type", "base16"], stdin=secret).stdout.decode()
    rev_path = os.path.join(os.environ.get("GNUPGHOME") or os.path.join(home(), ".gnupg"), "openpgp-revocs.d", f"{fpr}.rev")
    try:
        with open(rev_path, encoding="utf-8") as fh:
            revocation = fh.read()
    except OSError:
        revocation = "(no revocation certificate found; make one: gpg --gen-revoke " + fpr + ")\n"
    text = (f"agent-fabric — the key of {login()}\nfingerprint {fpr}\n\n"
            "Restore: paperkey --pubring <the committed identities/keys/"
            f"{login()}.asc> --secrets <this sheet> | gpg --import\n\n{sheet}\n{revocation}")
    if out:
        # O_NOFOLLOW: never through a symlink; fchmod: an existing file's
        # old mode never carries the key.
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fabric-secrets store", description="this agent's encrypted secrets (ADR-038)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("--remote")
    s = sub.add_parser("set")
    s.add_argument("name")
    n = sub.add_parser("names")
    n.add_argument("--json", action="store_true")
    p = sub.add_parser("put")
    p.add_argument("login")
    p.add_argument("name")
    p.add_argument("--store")
    c = sub.add_parser("certify")
    c.add_argument("login", nargs="?")
    c.add_argument("key_file", nargs="?")
    c.add_argument("--root", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("export-key")
    sub.add_parser("push")
    pa = sub.add_parser("paper")
    pa.add_argument("--out")
    sub.add_parser("import-doppler")
    ts = sub.add_parser("template-set")
    ts.add_argument("slug")
    tl = sub.add_parser("templates")
    tl.add_argument("--json", action="store_true")
    asg = sub.add_parser("assign")
    asg.add_argument("slug")
    asg.add_argument("logins", nargs="+")
    asg.add_argument("--json", action="store_true")
    asg.add_argument("--force", action="store_true", help="write even when this store's record says unchanged")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "init":
            r = init(args.remote)
            print(f"store: {r['store']}  key: {r['fingerprint']}{' (made)' if r['key_made'] else ''}")
        elif args.cmd == "set":
            r = set_entry(args.name, sys.stdin.buffer.read())
            print(f"{args.name}: {'set' if r['changed'] else 'unchanged'}")
        elif args.cmd == "names":
            ns = names()
            print(json.dumps(ns) if args.json else "\n".join(ns) or "(no entries)")
        elif args.cmd == "put":
            r = put(args.login, args.name, sys.stdin.buffer.read(), store=args.store)
            print(f"{args.login} {args.name}: {'written' if r['changed'] else 'unchanged'}")
        elif args.cmd == "certify":
            if args.root == bool(args.login):
                raise StoreError("certify takes LOGIN KEYFILE, or --root for this login's own key")
            if args.login and not args.key_file:
                raise StoreError("certify LOGIN needs the child's exported public key file")
            r = certify(None if args.root else args.login, args.key_file)
            print(f"{r['login']}: {r['fingerprint']}, parent {r['parent'] or '(root)'}")
        elif args.cmd == "export-key":
            sys.stdout.write(export_key())
        elif args.cmd == "push":
            store = store_dir()
            key_of_store(store)
            if not git(store, "remote", check=False).stdout.strip():
                raise StoreError("the store has no remote (fabric-secrets store init --remote URL)")
            git(store, "push", "-q", "-u", "origin", "HEAD:main")
            print("pushed")
        elif args.cmd == "verify":
            f = verify()
            print("\n".join(f) if f else "keys: clean")
            return 1 if f else 0
        elif args.cmd == "paper":
            paper(args.out)
        elif args.cmd == "template-set":
            r = template_set(args.slug, sys.stdin.buffer.read())
            print(f"template {args.slug}: {'set' if r['changed'] else 'unchanged'}")
        elif args.cmd == "templates":
            t = templates()
            if args.json:
                print(json.dumps(t))
            else:
                print("\n".join(f"{x['account']:<34} setup-token {x['token_sha256_12']}" for x in t) or "(no templates)")
        elif args.cmd == "assign":
            rows = assign(args.slug, args.logins, force=args.force)
            if args.json:
                print(json.dumps(rows))
            else:
                for r in rows:
                    print(f"{r['login']:<22} {r['from']:<30} -> {r.get('to', '-'):<30} {r['status']}{('  ' + r['reason']) if r.get('reason') else ''}")
            return 0 if all(r["status"] != "failed" for r in rows) else 1
        elif args.cmd == "import-doppler":
            r = import_doppler()
            print(f"imported {len(r['imported'])} name(s) from {r['config']}: {', '.join(r['imported'])}")
            if r["skipped"]:
                print(f"skipped (not a secret name, or not a string): {', '.join(r['skipped'])}", file=sys.stderr)
    except StoreError as e:
        print(f"fabric-secrets store: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
