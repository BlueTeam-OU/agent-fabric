"""tools/fabric/launcher/currency.py — the checkouts kept current: git's answers and the working copy's fast-forward.
A part of tools/fabric/launch.py, whose docstring is the contract."""
from __future__ import annotations

import os
from fabric_launcher.base import git, FETCH_TIMEOUT_S, say


# git's answers for the currency checks; why the fabric must be current
# is said above keep_fabric_current, in launch.py.
def git_status_ok(repo: str, *args: str, timeout: float = git.TIMEOUT_S) -> bool:
    try:
        return git.run(repo, *args, check=False, timeout=timeout).returncode == 0
    except git.GitError:
        return False


def git_text(repo: str, *args: str) -> str | None:
    try:
        r = git.run(repo, *args, check=False)
    except git.GitError:
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def behind_count(repo: str, rng: str) -> int:
    try:
        return int(git_text(repo, "rev-list", "--count", rng) or 0)
    except ValueError:
        return 0


def pull_ff(repo: str) -> str:
    """"ok", "failed" (it could not fast-forward) or "timeout": a pull the
    bound ended is a different cause, said differently."""
    try:
        r = git.run(repo, "pull", "-q", "--ff-only", "origin", "main", check=False)
    except git.GitError as exc:
        return "timeout" if "no answer within" in exc.reason else "failed"
    return "ok" if r.returncode == 0 else "failed"


# ── the working copy the session starts in ──────────────────────────
# Its CLAUDE.md and rules are binding the moment the session loads them,
# and a clone left on a week-old main gave a session instructions its
# project had already replaced (a retired review flow, followed live on
# a managed project's PR). The same fetch as keep_fabric_current's (launch.py), but this checkout is the
# session's own work, never the launcher's to refuse: on the default
# branch with nothing uncommitted it is fast-forwarded; on any other
# branch, or with changes, it is left alone and the gap is said, here
# and again to the session by the SessionStart hook.
def keep_working_copy_current(wc: str, fabric_root: str) -> None:
    if not wc or os.path.realpath(wc) == os.path.realpath(fabric_root):
        return
    if not git_status_ok(wc, "remote", "get-url", "origin"):
        return
    default = git_text(wc, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD") or "origin/main"
    default = default[len("origin/"):] if default.startswith("origin/") else default
    if not git_status_ok(wc, "fetch", "-q", "origin", default, timeout=FETCH_TIMEOUT_S):
        say(f"launch: could not fetch origin/{default} for {wc} (offline?); its CLAUDE.md is what is checked out.")
        return
    behind = behind_count(wc, f"HEAD..origin/{default}")
    if behind <= 0:
        return
    branch = git_text(wc, "symbolic-ref", "-q", "--short", "HEAD") or "(detached)"
    if (branch == default and git_status_ok(wc, "diff", "--quiet")
            and git_status_ok(wc, "diff", "--cached", "--quiet")
            and git_status_ok(wc, "merge", "-q", "--ff-only", f"origin/{default}")):
        head = git_text(wc, "rev-parse", "--short", "HEAD") or ""
        say(f"launch: {wc} was {behind} commit(s) behind origin/{default}; fast-forwarded to {head}.")
    else:
        say(f"launch: WARNING — {wc} ({branch}) lacks {behind} commit(s) of origin/{default}; "
            "its CLAUDE.md and rules may be older than the project's. Nothing was changed.")


def toplevel(cwd: str) -> str:
    """The launch directory's repository, or "" when it is in none."""
    try:
        return git.toplevel(cwd) or ""
    except git.GitError:
        return ""
