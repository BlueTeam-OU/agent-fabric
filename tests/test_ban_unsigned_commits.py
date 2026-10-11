#!/usr/bin/env python3
"""tools/fabric/guards/ban_unsigned_commits.py and the pre-push hook's use of
it: a fixture repository with a signed and an unsigned commit (a throwaway
key in a temporary GNUPGHOME), the CI entry point over base..HEAD, and a real
`git push` through policies/githooks/pre-push to a bare remote. The unsigned
commit is made with commit.gpgsign=false, the shape a plumbing rewrite takes.

Exit codes: 0 all checks passed, 1 one or more failed."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
from signing_fixture import drop_key, make_key  # noqa: E402

GUARD = os.path.join(HERE, "tools", "fabric", "guards", "ban_unsigned_commits.py")
HOOKS = os.path.join(HERE, "policies", "githooks")
T = tempfile.mkdtemp(prefix="test_unsigned.")
REPO, REMOTE = f"{T}/repo", f"{T}/remote.git"
fails = 0


def check(label: str, good: bool, detail: str = "") -> None:
    global fails
    if good:
        print(f"  ok   {label}")
        return
    fails += 1
    print(f"  FAIL {label}: {detail}")


def env(extra: dict | None = None) -> dict:
    e = {k: v for k, v in os.environ.items()
         if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "CLAUDE_", "GIT_", "XDG_"))}
    e.update(HOME=f"{T}/home", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GNUPGHOME=GNUPG,
             AGENT_FABRIC_STATE_DIR=f"{T}/state", **(extra or {}))
    return e


def git(*args: str, sign: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", REPO, "-c", f"commit.gpgsign={'true' if sign else 'false'}",
                           "-c", f"user.signingkey={KEY}", "-c", f"core.hooksPath={HOOKS if args[0] == 'push' else os.devnull}", "-c", "user.name=t", "-c", "user.email=t@e", *args],
                          env=env(), capture_output=True, text=True)


def commit(name: str, sign: bool) -> str:
    with open(f"{REPO}/{name}", "w", encoding="utf-8") as f:
        f.write(name)
    git("add", name)
    r = git("commit", "-qm", f"add {name}", sign=sign)
    assert r.returncode == 0, r.stderr
    return git("rev-parse", "--short=10", "HEAD").stdout.strip()


def guard(base: str, cwd: str = REPO) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, GUARD], cwd=cwd, env=env({"AGENT_FABRIC_SIGNATURES_BASE": base}),
                          capture_output=True, text=True)


def run() -> None:
    os.makedirs(f"{T}/home")
    subprocess.run(["git", "init", "-q", "-b", "main", "--bare", REMOTE], env=env(), check=True)
    subprocess.run(["git", "init", "-q", "-b", "main", REPO], env=env(), check=True)
    git("remote", "add", "origin", REMOTE)
    commit("base", sign=True)
    git("push", "-q", "origin", "main")

    print("the CI entry point, over the commits a branch adds")
    git("checkout", "-q", "-b", "feat")
    commit("signed", sign=True)
    r = guard("origin/main")
    check("a signed commit passes", r.returncode == 0 and "OK" in r.stdout, r.stdout + r.stderr)
    bad = commit("unsigned", sign=False)
    r = guard("origin/main")
    check("an unsigned commit fails", r.returncode == 1, r.stdout + r.stderr)
    check("…naming it and how to re-sign, in one line",
          bad in r.stderr and "re-sign" in r.stderr and len(r.stderr.strip().splitlines()) == 1, r.stderr)
    r = guard("", cwd=f"{T}/home")
    check("no repository to show a range: NOT ENFORCED, never OK",
          r.returncode == 0 and "NOT ENFORCED" in r.stdout and "OK" not in r.stdout, r.stdout)

    print("the pre-push hook")
    r = git("push", "-q", "origin", "feat")
    check("a new branch with an unsigned commit is refused, naming it", r.returncode != 0 and bad in r.stderr, r.stderr)
    check("…and nothing reached the remote", git("ls-remote", "origin", "feat").stdout.strip() == "", "feat arrived")
    git("reset", "-q", "--hard", "HEAD~1")
    r = git("push", "-q", "origin", "feat")
    check("a new branch of signed commits passes", r.returncode == 0, r.stderr)
    bad = commit("unsigned2", sign=False)
    r = git("push", "-q", "origin", "feat")
    check("an update adding an unsigned commit is refused", r.returncode != 0 and bad in r.stderr, r.stderr)
    git("reset", "-q", "--hard", "HEAD~1")
    commit("signed2", sign=True)
    check("an update of signed commits passes", git("push", "-q", "origin", "feat").returncode == 0)
    check("deleting a branch passes", git("push", "-q", "origin", ":feat").returncode == 0)
    git("checkout", "-q", "-b", "other", "main")
    commit("side", sign=True)
    git("merge", "--no-ff", "--no-edit", "-m", "unsigned-merge", "feat", sign=False)
    r = git("push", "-q", "origin", "other")
    check("an unsigned merge commit is refused too", r.returncode != 0 and "unsigned-merge" in r.stderr, r.stderr)


GNUPG, KEY = make_key(T)
try:
    run()
finally:
    drop_key(GNUPG)
    shutil.rmtree(T, ignore_errors=True)
print(f"{fails} failed" if fails else "all passed")
sys.exit(1 if fails else 0)
