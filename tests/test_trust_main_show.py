#!/usr/bin/env python3
"""trust.writers() reads the writers' keys from a git object of the fabric's
origin/main, at the path tools/fabric/roots.py names for it (move-plan §2
item 5): today identities/keys/…, operator/identities/keys/… once the
operator's tree is a directory of the repository. A symlink shim at the
old path would not serve `git show`, which is why the path is asked for."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from secretstore import trust  # noqa: E402
from secretstore.core import StoreError  # noqa: E402

ID, FPR, KEY = "0192aaaa-0000-7000-8000-000000000001", "A" * 40, b"-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n"


def repo(tmp: str, name: str, keys_at: str, env: dict) -> str:
    path = os.path.join(tmp, name)
    keys = os.path.join(path, keys_at)
    os.makedirs(keys)
    with open(os.path.join(keys, "lineage.json"), "w") as f:
        json.dump({ID: {"login": "kid", "fingerprint": FPR}}, f)
    with open(os.path.join(keys, f"{ID}.asc"), "wb") as f:
        f.write(KEY)
    g = ["git", "-C", path, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "k"],
                 ["update-ref", "refs/remotes/origin/main", "HEAD"]):
        subprocess.run(g + args, check=True, env=env, capture_output=True)
    return path


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "AGENT_FABRIC_"))}
    env.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
    saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("AGENT_FABRIC_")}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            flat = repo(tmp, "flat", "identities/keys", env)
            check("today: the key is read at identities/keys/", trust.writers(ID, flat) == {FPR: KEY})

            nested = repo(tmp, "nested", "operator/identities/keys", env)
            os.environ["AGENT_FABRIC_OPERATOR"] = os.path.join(nested, "operator")
            try:
                check("with the operator a directory of the repository, operator/identities/keys/ is read",
                      trust.writers(ID, nested) == {FPR: KEY})
                try:
                    trust.writers(ID, flat)
                    check("…and a repository with the keys at the old path is not read through the prefix", False)
                except StoreError as e:
                    check("…and a repository with the keys at the old path is not read through the prefix",
                          "not yet on the fabric's main" in str(e) or "outside" in str(e) or "not under" in str(e), e)
            finally:
                del os.environ["AGENT_FABRIC_OPERATOR"]

            # The reason the path is asked for: a link at the old path is no file to git.
            shim = repo(tmp, "shim", "operator/identities/keys", env)
            os.symlink("operator/identities", os.path.join(shim, "identities"))
            g = ["git", "-C", shim, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
            for args in (["add", "-A"], ["commit", "-q", "-m", "shim"], ["update-ref", "refs/remotes/origin/main", "HEAD"]):
                subprocess.run(g + args, check=True, env=env, capture_output=True)
            try:
                trust.writers(ID, shim)
                check("control: through the shim at the old path the key is not found", False)
            except StoreError as e:
                check("control: through the shim at the old path the key is not found", "not yet on the fabric's main" in str(e), e)
            os.environ["AGENT_FABRIC_OPERATOR"] = os.path.join(shim, "operator")
            try:
                check("…and through the operator path it is", trust.writers(ID, shim) == {FPR: KEY})
            finally:
                del os.environ["AGENT_FABRIC_OPERATOR"]

            os.environ["AGENT_FABRIC_OPERATOR"] = os.path.join(tmp, "elsewhere")
            try:
                trust.writers(ID, flat)
                check("an operator outside the repository is refused, not guessed", False)
            except StoreError as e:
                check("an operator outside the repository is refused, not guessed", "not under" in str(e), e)
            finally:
                del os.environ["AGENT_FABRIC_OPERATOR"]
    finally:
        os.environ.update(saved)
    print(f"\n{'FAILED' if fails else 'passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
