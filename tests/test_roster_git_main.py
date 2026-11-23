#!/usr/bin/env python3
"""The carrier's roster reads the committed keys (GitMainKeys) from a git object of the fabric's origin/main at the
path tools/fabric/roots.py names for them: operator/identities/keys/... since step B. A symlink shim at the old
path is no file to `git show`, which is why the path is asked for. Same fixtures as test_trust_main_show.py."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from gzcoord.carrier import roster as R  # noqa: E402

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
            nested = repo(tmp, "nested", "operator/identities/keys", env)
            keys = R.GitMainKeys(nested)
            check("the lineage is read at operator/identities/keys/ on origin/main", keys.lineage().get(ID, {}).get("fingerprint") == FPR)
            check("...and so is an agent's public key", keys.public_key(ID) == KEY)
            check("...an agent with no key file has none", keys.public_key("0192aaaa-0000-7000-8000-00000000ffff") is None)
            # The carrier's callers hand it the operator's directory, a subdirectory of the repository.
            sub = R.GitMainKeys(os.path.join(nested, "operator"))
            check("a root that is the operator directory inside the repository reads the same keys", sub.public_key(ID) == KEY)

            flat = repo(tmp, "flat", "identities/keys", env)
            try:
                R.GitMainKeys(flat).lineage()
                check("control: a main still holding the keys at identities/keys/ is not read", False)
            except R.RosterError as e:
                check("control: a main still holding the keys at identities/keys/ is not read", "missing or not JSON" in str(e), e)
            check("...and its key files read as absent", R.GitMainKeys(flat).public_key(ID) is None)

            shim = repo(tmp, "shim", "operator/identities/keys", env)
            os.symlink("operator/identities", os.path.join(shim, "identities"))
            g = ["git", "-C", shim, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
            for args in (["add", "-A"], ["commit", "-q", "-m", "shim"], ["update-ref", "refs/remotes/origin/main", "HEAD"]):
                subprocess.run(g + args, check=True, env=env, capture_output=True)
            old = subprocess.run(["git", "-C", shim, "show", "origin/main:identities/keys/lineage.json"], env=env, capture_output=True)
            check("control: through the shim at the old path git finds no key", old.returncode != 0, old.stdout)
            check("...and the roster, asking for the stored path, finds it", R.GitMainKeys(shim).public_key(ID) == KEY)

            os.environ["AGENT_FABRIC_OPERATOR"] = os.path.join(tmp, "elsewhere")
            try:
                R.GitMainKeys(flat).lineage()
                check("an operator outside the repository is a RosterError, not a guess", False)
            except R.RosterError as e:
                check("an operator outside the repository is a RosterError, not a guess", "not under" in str(e), e)
            finally:
                del os.environ["AGENT_FABRIC_OPERATOR"]

            plain = os.path.join(tmp, "plain")
            os.makedirs(plain)
            try:
                R.GitMainKeys(plain).lineage()
                check("a directory that is no git working tree is a RosterError", False)
            except R.RosterError as e:
                check("a directory that is no git working tree is a RosterError", True, e)
    finally:
        os.environ.update(saved)
    print(f"\n{'FAILED' if fails else 'passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
