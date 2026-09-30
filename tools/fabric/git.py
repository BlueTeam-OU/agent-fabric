"""tools/fabric/git.py — the fabric's Python calls to git (ADR-040 §5 rule 6).

    import git
    git.out(repo, "rev-parse", "HEAD")                 # stdout, stripped
    git.run(repo, "push", "-q", "origin", "HEAD:main") # the CompletedProcess
    git.ok(repo, "diff", "--cached", "--quiet")        # True on exit 0, False on 1

Every call is bounded, runs as `git -C <repo>`, and fails as a GitError
naming the operation and git's last line of stderr that is not advice
("hint:") — the shape secret_store._run found for its own calls, now in
one place. `ok` is for git's question-commands, whose exit 1 is an
answer, not a failure; anything else from them still raises.
"""
from __future__ import annotations

import subprocess

TIMEOUT_S = 120


class GitError(Exception):
    def __init__(self, what: str, reason: str, code: int | None = None):
        super().__init__(f"{what}: {reason}")
        self.what, self.reason, self.code = what, reason, code


def run(repo: str, *args: str, check: bool = True, input: str | None = None, env: dict | None = None,
        timeout: float = TIMEOUT_S, what: str | None = None) -> subprocess.CompletedProcess:
    what = what or "git " + (args[0] if args else "")
    try:
        stdin = {"input": input} if input is not None else {"stdin": subprocess.DEVNULL}
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                           env=env, timeout=timeout, **stdin)
    except FileNotFoundError:
        raise GitError(what, "git is not installed") from None
    except subprocess.TimeoutExpired:
        raise GitError(what, f"no answer within {timeout:g} s") from None
    if check and r.returncode != 0:
        lines = [l for l in r.stderr.strip().splitlines() if l.strip() and not l.startswith("hint:")]
        raise GitError(what, (lines or [f"exit {r.returncode}"])[-1], r.returncode)
    return r


def out(repo: str, *args: str, **kw) -> str:
    return run(repo, *args, **kw).stdout.strip()


def ok(repo: str, *args: str, **kw) -> bool:
    """A question git answers with its exit status: 0 yes, 1 no. Any other
    status is a failure, raised."""
    r = run(repo, *args, check=False, **kw)
    if r.returncode in (0, 1):
        return r.returncode == 0
    lines = [l for l in r.stderr.strip().splitlines() if l.strip() and not l.startswith("hint:")]
    raise GitError(kw.get("what") or "git " + (args[0] if args else ""), (lines or [f"exit {r.returncode}"])[-1], r.returncode)


def toplevel(path: str) -> str | None:
    r = run(path, "rev-parse", "--show-toplevel", check=False)
    return r.stdout.strip() or None if r.returncode == 0 else None


def branch(repo: str) -> str:
    return out(repo, "rev-parse", "--abbrev-ref", "HEAD")
