"""tools/fabric/github/landed.py — has a pull request's head reached its
base branch, asked of git rather than of the PR API.

The PR API can lag the merge by minutes. On agent-fabric #237 a merge
call failed while GitHub merged the PR, and the API then read OPEN, then
"merge already in progress", then CONFLICTING/DIRTY, while the merge
commit was already on origin/main. arm's read-back and wait-merged both
judged from the API and called it not merged. A head that is an ancestor
of the freshly fetched base has been merged, whatever the API says."""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402
import git  # noqa: E402

FETCH_TIMEOUT_S = 60
_SHA = re.compile(r"[0-9a-f]{40}")


def head_in_base(repo: str, head: str, base: str, cwd: str = ".") -> bool | None:
    """True when `head` is an ancestor of `repo`'s `base` branch, just fetched into the clone at `cwd`. False when
    git says it is not. None when git could not be asked: the clone's origin is not `repo` (GH_REPO may name another
    repository), the fetch failed, or the input is not a full sha and a branch name. Only True is a fact a caller
    acts on: False is not a refusal, since the base may have moved past an unmerged head in either answer."""
    if not (_SHA.fullmatch(head or "") and base) or base.startswith("-"):
        return None
    try:
        # The configured URL, not `git remote get-url`: that one applies url.<x>.insteadOf, and the question is
        # which repository this clone says origin is, not where the bytes come from.
        url = git.run(cwd, "config", "--get", "remote.origin.url", check=False, timeout=30).stdout.strip()
        m = gh._ORIGIN.fullmatch(url)
        if not m or m.group("repo").lower() != repo.lower():
            return None
        # An explicit refspec: the clone's fetch configuration may not map this branch (a single-branch clone), and
        # FETCH_HEAD is left alone, since another fetch in the same clone may be reading it.
        if git.run(cwd, "fetch", "-q", "--no-write-fetch-head", "origin",
                   f"+refs/heads/{base}:refs/remotes/origin/{base}", check=False,
                   timeout=FETCH_TIMEOUT_S).returncode != 0:
            return None
        # A head not in the clone is not in the base just fetched. git says so with 128, which merge-base shares
        # with real failures, so it is asked first.
        if git.run(cwd, "cat-file", "-e", f"{head}^{{commit}}", check=False, timeout=30).returncode != 0:
            return False
        return git.ok(cwd, "merge-base", "--is-ancestor", head, f"refs/remotes/origin/{base}")
    except git.GitError:
        return None
