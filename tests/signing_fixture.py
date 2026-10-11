"""tests/signing_fixture.py -- a throwaway gpg key so a fixture repository can
hold signed commits, in a GNUPGHOME of its own (never the account's keyring).

    home, key = make_key(parent_dir)       # parent_dir short: gpg-agent's socket lives under it
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


def drop_key(home: str) -> None:
    subprocess.run(["gpgconf", "--kill", "all"], env={**os.environ, "GNUPGHOME": home}, capture_output=True, timeout=30)
