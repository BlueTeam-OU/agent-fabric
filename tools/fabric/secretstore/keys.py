"""tools/fabric/secretstore/keys.py — the agent's key: fingerprints, its use subkeys, its user ids, and the signing arguments.
A part of secret_store.py, which re-exports it; its docstring is the contract."""
from __future__ import annotations

import os
import re
import tempfile

from .core import UID_DOMAIN, StoreError, AGENT_ID_RE, store_dir, _run, gpg


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
# One key per use (ADR-038 rule 1): the primary certifies only, and each
# use is its own subkey, so a leaked signing key never opens the store and
# each can be rotated alone. The authentication subkey is the one an SSH
# client can use through gpg-agent.
KEY_USES = (("e", "cv25519", "encr", "encryption"), ("s", "ed25519", "sign", "signing"),
            ("a", "ed25519", "auth", "authentication"))


def _key_caps(colons: str) -> tuple[str, set[str]]:
    """From `gpg --with-colons` output for one key: the primary's own
    capabilities and those of its valid subkeys (revoked or expired ones
    excluded)."""
    primary, subs = "", set()
    for l in colons.splitlines():
        f = l.split(":")
        if f[0] == "pub":
            primary = "".join(c for c in f[11] if c.islower())
        elif f[0] == "sub" and f[1] not in ("r", "e", "i"):
            subs |= {c for c in f[11] if c.islower()}
    return primary, subs


def _ensure_use_subkeys(fpr: str) -> list[str]:
    """Adds the subkey of each use the key lacks; returns the uses added."""
    _, subs = _key_caps(gpg("--with-colons", "--list-keys", fpr).stdout.decode())
    added = []
    for cap, algo, usage, name in KEY_USES:
        if cap not in subs:
            gpg("--quick-add-key", fpr, algo, usage, "never")
            added.append(name)
    return added


def uid_of(agent_id: str, name: str) -> str:
    # The address is the id, which a rename keeps; the name part is the
    # login at birth, a label only.
    return f"{name} <{agent_id}@{UID_DOMAIN}>"


def export_key(fpr: str | None = None, homedir: str | None = None) -> str:
    return gpg("--armor", "--export", fpr or key_of_store(), homedir=homedir).stdout.decode()


def _signing_args(signer: str | None = None) -> list[str]:
    """git -c options that sign every commit made, a rebase's included, with
    the writer's key: gpg chooses that key's signing subkey."""
    return ["-c", "commit.gpgsign=true", "-c", f"user.signingkey={signer or key_of_store(store_dir())}",
            "-c", "gpg.program=gpg", "-c", "gpg.format=openpgp"]


def _signing_subkeys(homedir: str) -> dict[str, str]:
    """{signing key fingerprint: its primary's} in a keyring: each valid
    subkey with the sign capability, and a primary that itself signs."""
    out, primary, last = {}, None, None
    for line in gpg("--with-colons", "--fixed-list-mode", "--list-keys", homedir=homedir).stdout.decode().splitlines():
        f = line.split(":")
        if f[0] in ("pub", "sub"):
            last = f
        elif f[0] == "fpr" and last is not None:
            if last[0] == "pub":
                primary = f[9]
            if "s" in last[11] and last[1] not in ("r", "e", "i", "d"):
                out[f[9]] = primary
            last = None
    return out


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


def _key_agent_ids(key_file: str) -> list[str]:
    """The agent ids a key file's valid user ids carry, read in a
    throwaway keyring."""
    with tempfile.TemporaryDirectory() as tmp:
        os.chmod(tmp, 0o700)
        try:
            gpg("--import", key_file, homedir=tmp)
            out = gpg("--with-colons", "--list-keys", homedir=tmp).stdout.decode()
        finally:
            _run(["gpgconf", "--homedir", tmp, "--kill", "all"], check=False)
    ids = []
    for l in out.splitlines():
        f = l.split(":")
        if f[0] == "uid" and f[1] not in ("r", "e", "i"):
            m = re.search(r"<([0-9a-f-]{36})@" + re.escape(UID_DOMAIN) + ">", f[9])
            if m and AGENT_ID_RE.match(m.group(1)):
                ids.append(m.group(1))
    return ids
