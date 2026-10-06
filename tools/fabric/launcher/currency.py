"""tools/fabric/launcher/currency.py — the checkouts kept current: git's answers and the working copy's fast-forward.
A part of tools/fabric/launch.py, whose docstring is the contract."""
from __future__ import annotations

import os
from fabric_launcher.base import git, FETCH_TIMEOUT_S, say


# ── the fabric itself must be current ───────────────────────────────
# A session is fixed at exec: it runs on the launcher, hooks, prompt
# sections and routing of the checkout it was launched from. "Pull, then
# relaunch" was the rule, and moveto pulls on entry — but an account
# that keeps its moveto shell open for a day relaunches from it without
# a pull, and on 2026-09-16 two accounts came back on the previous
# launcher (no GOODBYE, two HELLOs) after a DECISION told everyone to
# pull. So the launcher checks: a fetch, and a checkout behind
# origin/main is PULLED — fast-forward only; every role but the
# coordinator is read-only here, so there is nothing local to lose, and
# --ff-only refuses on its own if the checkout ever diverged — and the
# launcher re-executes itself so the session runs on what was pulled
# (the code under a running launcher must not change).
# It was a refusal naming the pull command until the CEO asked, the same
# day, why the person had to type what the launcher already knew. A pull
# that cannot fast-forward is refused with the reason; offline (the fetch
# fails) it launches on what is checked out and says so.
# AGENT_FABRIC_ALLOW_STALE=1 overrides, loudly, for the case where the
# push itself is what a session is about to do.
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
# a managed project's PR). The same fetch as above, but this checkout is the
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
