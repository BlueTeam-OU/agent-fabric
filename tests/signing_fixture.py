"""tests/signing_fixture.py -- a throwaway gpg key so a fixture repository can
hold signed commits, in a GNUPGHOME of its own (never the account's keyring).

    home, key = make_key(parent_dir)       # parent_dir short: gpg-agent's socket lives under it
    home, primary, sub = make_agent_key(parent_dir)   # as an agent's key is: a certify-only primary and one signing subkey
    env["GNUPGHOME"] = home                # the git calls that sign or verify
    git -c user.signingkey=<key> -c commit.gpgsign=true commit ...
    drop_key(home)                         # stops the agent it started
"""
from __future__ import annotations

import os
import subprocess


def make_key(parent: str) -> tuple[str, str]:
    home = os.path.join(parent, "gnupg")
    os.makedirs(home, mode=0o700, exist_ok=True)
    env = {**os.environ, "GNUPGHOME": home}
    subprocess.run(["gpg", "--batch", "--quiet", "--passphrase", "", "--quick-gen-key",
                    "fixture <fixture@example.invalid>", "ed25519", "sign", "never"],
                   env=env, check=True, capture_output=True, timeout=60)
    listing = subprocess.run(["gpg", "--batch", "--list-secret-keys", "--with-colons"], env=env,
                             check=True, capture_output=True, text=True, timeout=30).stdout
    fpr = next(l.split(":")[9] for l in listing.splitlines() if l.startswith("fpr:"))
    return home, fpr


def make_agent_key(parent: str) -> tuple[str, str, str]:
    """(GNUPGHOME, primary fingerprint, signing subkey fingerprint) of a key shaped like an agent's (ADR-038)."""
    home = os.path.join(parent, "gnupg")
    os.makedirs(home, mode=0o700, exist_ok=True)
    env = {**os.environ, "GNUPGHOME": home}
    subprocess.run(["gpg", "--batch", "--quiet", "--passphrase", "", "--quick-gen-key",
                    "agent <00000000-0000-7000-8000-000000000000@agents.agent-fabric>", "ed25519", "cert", "never"],
                   env=env, check=True, capture_output=True, timeout=60)
    listing = subprocess.run(["gpg", "--batch", "--list-keys", "--with-colons"], env=env, check=True,
                             capture_output=True, text=True, timeout=30).stdout
    primary = next(l.split(":")[9] for l in listing.splitlines() if l.startswith("fpr:"))
    subprocess.run(["gpg", "--batch", "--quiet", "--passphrase", "", "--quick-add-key", primary, "ed25519", "sign", "never"],
                   env=env, check=True, capture_output=True, timeout=60)
    listing = subprocess.run(["gpg", "--batch", "--list-keys", "--with-colons"], env=env, check=True,
                             capture_output=True, text=True, timeout=30).stdout.splitlines()
    sub = next(listing[i + 1].split(":")[9] for i, l in enumerate(listing) if l.startswith("sub:"))
    return home, primary, sub


def drop_key(home: str) -> None:
    env = {**os.environ, "GNUPGHOME": home}
    sockets = subprocess.run(["gpgconf", "--list-dirs", "socketdir"], env=env, capture_output=True, text=True, timeout=30).stdout.strip()
    subprocess.run(["gpgconf", "--kill", "all"], env=env, capture_output=True, timeout=30)
    # gpg makes a directory per home under /run/user/<uid>/gnupg/ for its sockets and never removes it.
    if os.path.basename(sockets).startswith("d."):
        try:
            os.rmdir(sockets)
        except OSError:
            pass
