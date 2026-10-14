"""tools/fabric/jobsparts/vcs.py — git and gh as `switch` asks them: a working copy's state, the default branch, a branch on the remote.
A part of tools/fabric/jobs.py, whose docstring is the contract.

Every call is bounded and an argument list. A call that fails is a VcsError saying what was asked: the callers turn it into
"could not tell", never into clean, pushed or merged."""
from __future__ import annotations

import os
from fabric_jobs.base import FABRIC_ROOT, _load

git = _load("fabric_git", os.path.join(FABRIC_ROOT, "tools", "fabric", "git.py"))
gh = _load("fabric_gh", os.path.join(FABRIC_ROOT, "tools", "fabric", "gh.py"))

FETCH_TIMEOUT_S = 120
# The variables that aim git at a repository other than the one -C names: a session that inherited one would otherwise
# answer for the wrong tree (tests/git_env.py is the same list).
_AIMING = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY", "GIT_PREFIX")


class VcsError(Exception):
    """git or gh did not answer; the message is the whole reason."""


def run(repo: str, *args: str, check: bool = True, timeout: float = 60):
    env = {k: v for k, v in os.environ.items() if k not in _AIMING}
    try:
        return git.run(repo, *args, check=check, timeout=timeout, env=env)
    except git.GitError as e:
        raise VcsError(str(e)) from None


def text(repo: str, *args: str, timeout: float = 60) -> str:
    return run(repo, *args, timeout=timeout).stdout.strip()


def question(repo: str, *args: str) -> bool:
    """A question git answers with exit 0 or 1; any other status is an error, not a no."""
    r = run(repo, *args, check=False)
    if r.returncode in (0, 1):
        return r.returncode == 0
    raise VcsError(f"git {args[0]}: exit {r.returncode}: {(r.stderr.strip().splitlines() or [''])[-1]}")


def toplevel(path: str) -> str | None:
    if not path or not os.path.isdir(path):
        return None
    r = run(path, "rev-parse", "--show-toplevel", check=False)
    return r.stdout.strip() or None if r.returncode == 0 else None


def dirty(repo: str) -> list[str]:
    """`git status --porcelain` lines: tracked changes and untracked files alike, as fabric-fresh counts them."""
    return [l for l in text(repo, "status", "--porcelain").splitlines() if l.strip()]


def fetch(repo: str) -> None:
    run(repo, "fetch", "-q", "origin", timeout=FETCH_TIMEOUT_S)


def default_branch(repo: str) -> str:
    """The remote's default branch: origin/HEAD, else what the remote itself says. Never guessed as main."""
    r = run(repo, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD", check=False)
    name = r.stdout.strip()
    if r.returncode == 0 and name.startswith("origin/"):
        return name[len("origin/"):]
    for line in text(repo, "ls-remote", "--symref", "origin", "HEAD", timeout=FETCH_TIMEOUT_S).splitlines():
        if line.startswith("ref: refs/heads/"):
            return line.split("\t")[0][len("ref: refs/heads/"):]
    raise VcsError(f"the default branch of origin is unknown for {repo}: origin/HEAD is unset and the remote names none")


def remote_tip(repo: str, branch: str) -> str | None:
    """The sha `branch` has on origin now, asked of the remote itself; None when it has no such branch."""
    out = text(repo, "ls-remote", "--heads", "origin", f"refs/heads/{branch}", timeout=FETCH_TIMEOUT_S)
    return out.split()[0] if out else None


def local_branch_exists(repo: str, branch: str) -> bool:
    return question(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}")


def worktree_of(repo: str, branch: str) -> str | None:
    """The worktree that has `branch` checked out, or None."""
    path = None
    for line in text(repo, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):]
        elif line == f"branch refs/heads/{branch}":
            return path
    return None
