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


# ── the fabric checkout's verdict ───────────────────────────────────
# One judgement for the launcher (which acts on it, keep_fabric_current in
# launch.py) and for fabric-fresh (which only asks): a session ended by
# fabric-fresh is relaunched by this same launcher, and a launcher that
# dies on a checkout it cannot bring current leaves the agent with no
# session at all (devex-tooling, 2026-10-11). The question is read-only
# but for the fetch.
class Verdict:
    """kind: "skip" (not a git checkout with an origin), "offline",
    "current", "behind" (a pull may mend it), or "blocked" (a fast-forward
    cannot succeed; `reason` says why)."""
    def __init__(self, kind: str, behind: int = 0, reason: str = "") -> None:
        self.kind, self.behind, self.reason = kind, behind, reason


def pull_blocker(repo: str) -> str | None:
    """Why `pull --ff-only origin main` is predicted to fail, or None. A
    prediction, for the message and for fabric-fresh (which ends a session
    only on None); the launcher still lets git decide, since a file staged
    with exactly the incoming content is "blocked" here and pulls fine. A pull ended by the bound is not predictable and not here."""
    anc = git_status_ok(repo, "merge-base", "--is-ancestor", "HEAD", "origin/main")
    if not anc:
        return "it has local commits that origin/main does not contain"
    try:
        # --no-renames: a rename's old path is a change the pull makes too.
        # --untracked-files=all: the default folds a new directory into one
        # `?? dir/` entry, which names none of the files a pull would write.
        incoming = git.run(repo, "diff", "--name-only", "--no-renames", "-z", "HEAD", "origin/main", check=False)
        status = git.run(repo, "status", "--porcelain", "-z", "--untracked-files=all", check=False)
    except git.GitError:
        return None
    if incoming.returncode != 0 or status.returncode != 0:
        return None
    touched = set(filter(None, incoming.stdout.split("\0")))
    # A -z status entry is "XY path"; a rename or copy is followed by its
    # source as a field of its own, with no status prefix: also a dirty path.
    fields = iter(f for f in status.stdout.split("\0") if f)
    dirty: set[str] = set()
    for entry in fields:
        dirty.add(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:
            dirty.add(next(fields, ""))
    hit = sorted(touched & dirty)
    return f"uncommitted changes would be overwritten ({', '.join(hit[:3])})" if hit else None


def fabric_verdict(fabric_root: str) -> Verdict:
    if not (git_status_ok(fabric_root, "rev-parse", "--is-inside-work-tree")
            and git_status_ok(fabric_root, "remote", "get-url", "origin")):
        return Verdict("skip")
    if not git_status_ok(fabric_root, "fetch", "-q", "origin", "main", timeout=FETCH_TIMEOUT_S):
        return Verdict("offline")
    behind = behind_count(fabric_root, "HEAD..origin/main")
    if behind <= 0:
        return Verdict("current")
    why = pull_blocker(fabric_root)
    return Verdict("blocked", behind, why) if why else Verdict("behind", behind)


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
