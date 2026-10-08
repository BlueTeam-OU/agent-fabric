"""tools/fabric/secretstore/backup.py — Proton Drive: the stores' backup and its verification, the recovery key's public half, and recovery copies.
A part of secret_store.py, which re-exports it; its docstring is the contract."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile

import roots  # noqa: E402
from .core import (
    UID_DOMAIN,
    StoreError,
    login,
    AGENT_ID_RE,
    REPO_PREFIX,
    own_agent_id,
    store_dir,
    children_dir,
    _run,
    gpg,
    git,
)
from .keys import fingerprints, key_of_store, _key_file_fingerprint
from .trust import _commit
from .entries import _require_clean, _before_write, _push_if_ahead, _after_commit
from .mirrors import lineage
from .accounts import _sheet_text
from .lock import write_lock


# ── Proton Drive: the stores' backup and the keys' recovery copies ─────
# The owner's decision (ADR-038 §7): a dedicated Proton account holds, in
# /my-files/agent-fabric/, every store as a git bundle (ciphertext only)
# with a manifest, and each key's recovery copy. The CLI's session is an
# entry of the running login's own store (PROTON_DRIVE_CREDENTIALS_STORE=
# pass over this store), so it is readable by this login alone; `auth
# login` is the owner's, in a terminal. Nothing here prints a value.
PROTON_ROOT = "/my-files/agent-fabric"


def _proton(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {**os.environ, "PASSWORD_STORE_DIR": store_dir(), "PROTON_DRIVE_CREDENTIALS_STORE": "pass"}
    exe = os.environ.get("PROTON_DRIVE_BIN") or shutil.which("proton-drive")
    if not exe:
        raise StoreError("the Proton Drive CLI is not installed (proton-drive in ~/.local/bin)")
    r = _run([exe, *args], env=env, timeout=600, check=False, label=f"proton-drive {' '.join(args[:2])}")
    if check and r.returncode != 0:
        lines = [l for l in (r.stderr or r.stdout).decode(errors="replace").splitlines() if l.strip()]
        why = (lines or [f"exit {r.returncode}"])[-1]
        # The sign-in hint only when the CLI's own words are about signing
        # in: on any other error it would send the owner the wrong way.
        hint = (" (the session has lapsed: the owner runs `proton-drive auth login` with PASSWORD_STORE_DIR "
                "set to this store and PROTON_DRIVE_CREDENTIALS_STORE=pass)"
                if re.search(r"auth|session|log ?in|401|unauthori", why, re.I) else "")
        raise StoreError(f"proton-drive {args[0]} {args[1] if len(args) > 1 else ''}: {why}{hint}")
    return r


def _proton_folder(path: str) -> str:
    """The folder at path, made (with its parents) when absent. Asked with
    `info`, whose exit status says whether the node exists: `list` prints
    a decorated table, not paths, and reading it as paths made every run
    after the first try to create a folder that was there."""
    if path in ("", "/my-files"):
        # The drive's root always exists: failing on it is the session or
        # the network, said in the CLI's own words (and _proton's sign-in
        # hint), never a recursion past the root.
        _proton("filesystem", "info", "/my-files")
        return "/my-files"
    if _proton("filesystem", "info", path, check=False).returncode == 0:
        return path
    parent, name = path.rsplit("/", 1)
    _proton_folder(parent)
    _proton("filesystem", "create-folder", parent, name)
    return path


def _upload(local: str, folder: str) -> None:
    # A new revision, never a replacement: Proton keeps what was there.
    _proton("filesystem", "upload", "-f", "create-new-revision", "-t", local, folder)


def _sha256_file(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


RECOVERY_UID = f"agent-fabric recovery <recovery@{UID_DOMAIN}>"


def recovery_pub(fabric: str | None = None) -> str:
    return roots.recovery_key(fabric or None)


def _make_recovery_key(homedir: str, passphrase: str) -> tuple[str, str, str]:
    """The recovery key in homedir, every secret part protected by the
    passphrase (checked, not assumed); returns its fingerprint, its public
    half and its protected private half, both armoured."""
    base = ["gpg", "--homedir", homedir, "--batch", "--pinentry-mode", "loopback", "--passphrase-fd", "0"]
    def run(*a: str) -> bytes:
        # Through the store's one boundary: a failure, or a gpg that cannot
        # start, is a StoreError naming the operation, never a traceback.
        return _run([*base, *a], stdin=passphrase.encode(), env={**os.environ, "GNUPGHOME": homedir},
                    label=f"gpg {a[0]}").stdout
    run("--quick-gen-key", RECOVERY_UID, "ed25519", "cert", "never")
    fpr = fingerprints(homedir=homedir, secret=True)[0]
    run("--quick-add-key", fpr, "cv25519", "encr", "never")
    info = _run(["gpg-connect-agent", "--homedir", homedir, "KEYINFO --list", "/bye"],
                label="gpg-connect-agent KEYINFO").stdout.decode().split("\n")
    # KEYINFO: S KEYINFO <grip> <type> <serial> <idstr> <cached> <protection> …; P is protected.
    marks = [l.split()[7] for l in info if l.startswith("S KEYINFO")]
    if len(marks) != 2 or set(marks) != {"P"}:
        raise StoreError("the recovery key is not protected by the passphrase; nothing was published")
    public = gpg("--armor", "--export", fpr, homedir=homedir).stdout.decode()
    private = run("--armor", "--export-secret-keys", fpr).decode()
    if "BEGIN PGP PRIVATE KEY BLOCK" not in private:
        raise StoreError("the recovery key's private half did not export; nothing was published")
    return fpr, public, private


def _recovery_key_name(fpr: str) -> str:
    return f"recovery-key-{fpr[-16:]}.asc"


def recovery_copy(force: bool = False) -> dict:
    """This login's key recovery copy, encrypted to the owner's recovery
    key, committed into its own store as recovery/<agent id>.key.gpg and
    pushed; the parent's backup carries it to Proton. Nothing is printed
    but a path and a hash, and once written not even this login can read
    it back: only the owner, with the recovery passphrase."""
    pub = recovery_pub()
    if not os.path.exists(pub):
        raise StoreError("no recovery key yet (identities/recovery.asc): the owner runs `fabric-secrets store recovery-key init`")
    rfpr = _key_file_fingerprint(pub)
    store = store_dir()
    with write_lock(store):
        key_of_store(store)
        _require_clean(store)
        _before_write(store)
        aid = own_agent_id(store)
        if not aid:
            raise StoreError("this store has no agent id yet (store-enroll.sh)")
        path = os.path.join(store, "recovery", f"{aid}.key.gpg")
        note = os.path.join(store, "recovery", f"{aid}.recipient")
        if os.path.exists(path) and not force and open(note, encoding="utf-8").read().strip() == rfpr:
            _push_if_ahead(store)
            return {"path": path, "changed": False, "recipient": rfpr}
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        gpg("--trust-model", "always", "--no-encrypt-to", "--encrypt", "--recipient-file", pub,
            "--output", path + ".tmp", stdin=_sheet_text().encode())
        os.replace(path + ".tmp", path)
        with open(note, "w", encoding="utf-8") as fh:
            fh.write(rfpr + "\n")
        git(store, "add", os.path.relpath(path, store), os.path.relpath(note, store))
        _commit(store, f"agent {login()}: recovery copy, encrypted to the recovery key {rfpr[-16:]}")
        _after_commit(store)
        return {"path": path, "changed": True, "recipient": rfpr}


def _stores() -> dict[str, str]:
    """This agent's own store and every child mirror it holds: agent id -> dir."""
    mine = own_agent_id()
    if not mine:
        raise StoreError("this store has no agent id yet (store-enroll.sh --self)")
    out = {mine: store_dir()}
    try:
        for child in sorted(os.listdir(children_dir())):
            d = os.path.join(children_dir(), child)
            if os.path.isdir(os.path.join(d, ".git")) and AGENT_ID_RE.match(child):
                out[child] = d
    except FileNotFoundError:
        pass
    return out


def backup() -> dict:
    """Every store this login holds — its own and its children's mirrors,
    each brought up to its remote first — as a git bundle (the whole
    history, ciphertext only), with a manifest of each bundle's sha256
    and head, uploaded to Proton Drive as new revisions."""
    folder = _proton_folder(f"{PROTON_ROOT}/secrets")
    import datetime
    manifest = {"written_by": login(), "stores": {}}
    manifest["at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with tempfile.TemporaryDirectory() as tmp:
        for who, d in _stores().items():
            # Locked through the bundle: a write between the pull and the
            # bundle would make the manifest's head not the bundle's.
            with write_lock(d):
                _before_write(d)
                bundle = os.path.join(tmp, f"{REPO_PREFIX}{who}.bundle")
                git(d, "bundle", "create", bundle, "--all")
                head = git(d, "rev-parse", "HEAD").stdout.decode().strip()
            name = ((lineage().get(who) or {}).get("login")) or (login() if d == store_dir() else None)
            manifest["stores"][who] = {"bundle": os.path.basename(bundle), "sha256": _sha256_file(bundle), "login": name,
                                       "head": head}
            # Each store's recovery copy, already encrypted to the owner's
            # recovery key, also stands alone in keys/ for a restore.
            rdir = os.path.join(d, "recovery")
            for f in sorted(os.listdir(rdir)) if os.path.isdir(rdir) else []:
                if f.endswith(".key.gpg"):
                    manifest.setdefault("recovery_copies", {})[f] = _sha256_file(os.path.join(rdir, f))
                    _upload(os.path.join(rdir, f), _proton_folder(f"{PROTON_ROOT}/keys"))
        mpath = os.path.join(tmp, "manifest.json")
        with open(mpath, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        for name in sorted(os.listdir(tmp)):
            _upload(os.path.join(tmp, name), folder)
    return manifest


def verify_backup() -> list[str]:
    """Download the manifest, every bundle and every recovery copy it
    names, and check each against its sha256 (and a bundle with `git
    bundle verify`). Findings; [] is clean."""
    folder = f"{PROTON_ROOT}/secrets"
    findings = []
    with tempfile.TemporaryDirectory() as tmp:
        # `git bundle verify` needs a repository around it: run from one
        # that is not, it failed every good bundle. An empty one of its own,
        # never the caller's cwd, which could be any repository or none.
        empty = os.path.join(tmp, ".verify-repo")
        os.makedirs(empty)
        git(empty, "init", "-q")
        _proton("filesystem", "download", "-f", "remove", f"{folder}/manifest.json", tmp)
        manifest = json.load(open(os.path.join(tmp, "manifest.json"), encoding="utf-8"))
        for who, rec in sorted(manifest.get("stores", {}).items()):
            _proton("filesystem", "download", "-f", "remove", f"{folder}/{rec['bundle']}", tmp)
            local = os.path.join(tmp, rec["bundle"])
            if _sha256_file(local) != rec["sha256"]:
                findings.append(f"{rec['bundle']}: its sha256 is not the manifest's")
                continue
            if _run(["git", "bundle", "verify", local], cwd=empty, check=False).returncode != 0:
                findings.append(f"{rec['bundle']}: git bundle verify fails")
        # The recovery copies stand alone in keys/ for a restore: each is
        # checked against the hash the manifest took when it went up.
        for f, sha in sorted((manifest.get("recovery_copies") or {}).items()):
            got = _proton("filesystem", "download", "-f", "remove", f"{PROTON_ROOT}/keys/{f}", tmp, check=False)
            local = os.path.join(tmp, f)
            if got.returncode != 0 or not os.path.exists(local):
                findings.append(f"keys/{f}: could not be downloaded")
            elif _sha256_file(local) != sha:
                findings.append(f"keys/{f}: its sha256 is not the manifest's")
    return findings
