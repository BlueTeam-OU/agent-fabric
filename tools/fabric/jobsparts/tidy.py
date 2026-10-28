"""tools/fabric/jobsparts/tidy.py — `fabric-jobs tidy [--dry-run]`: the build output of every checkout of this login that no open
job holds (the owner, 2026-10-27: /home reached 97%, about 380 GB of Rust `target` directories in four accounts, mostly the
worktrees `switch` never left). A part of tools/fabric/jobs.py, whose docstring is the contract; run daily by a user timer
as the account.

Contract. The trees are the directories directly under ~/projects that have a `.git` (a working copy, a linked worktree, a
session checkout); a link, a tree another uid owns and a tree on another filesystem than ~/projects are kept, said. A tree
that is, holds or lies in the `worktree` or `working copy` of a job that is active, queued, paused or blocked is left alone
whole. In every other tree, leave_targets' rules apply to a `target` beside a Cargo.toml and to a `node_modules` beside a
package.json, at the same depth: kept, with the reason, when a process of this uid stands in it, when its `.cargo-lock` is
held, when a cargo configuration points the target elsewhere, a link, another filesystem, git tracks a file under it or cannot be asked, or
anything in it belongs to another uid;
whatever cannot be told is kept. A delivered job is not open here: its work is on a branch, and a build is cheaper than a full
disk. The first line names the job list that decides (its path), so a timer's journal says which one was read. A job list that is
absent while ~/projects holds any tree refuses: nothing removed, exit 1, the path said — read_jobs reads a missing file as "no
jobs", which under a state directory the sessions do not use would free the worktrees of every active job; an empty list that is
there is a new account's and stays valid. One line per directory, then the total. Exit 0 unless the job list is absent (with trees) or cannot be read, or ~/projects cannot be read: then nothing is
removed and the reason is said; a missing ~/projects is a fact, not an unreadable one (an account that has no checkouts).
--dry-run says what would go and removes nothing."""
from __future__ import annotations

import os
import sys
from fabric_jobs.base import OPEN, STATES, identity
from fabric_jobs import leave_targets as lt

HOLDING = tuple(s for s in OPEN if s != "delivered")


class Unreadable(Exception):
    """The job list or ~/projects could not be read: nothing is removed."""


def held_paths() -> dict[str, str] | None:
    """{real path: job id} of every worktree and working copy an open job names; None when there is no job list at all."""
    try:
        os.stat(identity.jobs_path())      # follows a link: a dangling one is absent
    except FileNotFoundError:      # not read_jobs' empty list: absent is unknown, an empty list that is there is a fact
        return None
    except OSError as e:
        raise Unreadable(f"the job list cannot be read ({e.strerror or e})") from None
    try:
        doc = identity.read_jobs()
    except (SystemExit, OSError) as e:      # read_jobs refuses a corrupt list or another host's with SystemExit
        raise Unreadable(f"the job list cannot be read ({e})") from None
    held: dict[str, str] = {}
    for job in doc["jobs"]:
        if not isinstance(job, dict) or not isinstance(job.get("id"), str):
            raise Unreadable("the job list holds an entry that is not a job")
        if job.get("state") not in STATES:
            raise Unreadable(f"{job['id']} has a state this tool does not know")      # unknown is not "closed"
        if job.get("state") not in HOLDING:
            continue
        for field in ("worktree", "working_copy"):
            path = job.get(field)
            if path is None:
                continue
            if not isinstance(path, str):
                raise Unreadable(f"{job['id']} has a {field} that is not a path")
            if path:
                held[os.path.realpath(path)] = job["id"]
    return held


def trees(projects: str) -> list[str]:
    try:
        names = sorted(os.listdir(projects))
    except OSError as e:
        raise Unreadable(f"{projects} cannot be read ({e.strerror or e})") from None
    return [os.path.join(projects, n) for n in names if os.path.lexists(os.path.join(projects, n, ".git"))]


def tidy_tree(tree: str, projects_dev: int, held: dict[str, str], cwds: list[str], why_blind: str, dry_run: bool) -> tuple[list[str], int]:
    if os.path.islink(tree):
        return [f"kept {tree}: a link, not followed"], 0
    real = os.path.realpath(tree)
    for path, job in held.items():
        if lt.overlaps(real, path):
            return [f"kept {tree}: it is, holds or lies in a checkout of open job {job}"], 0
    st = os.lstat(real)
    if st.st_uid != os.getuid():
        return [f"kept {tree}: owned by another account"], 0
    if st.st_dev != projects_dev:
        return [f"kept {tree}: on another filesystem"], 0
    found, links = lt.find_targets(real, lt.BUILD_OUTPUT)
    lines = [f"kept {t}: a link, not followed" for t in links]
    freed = 0
    for t in found:
        try:
            line, n = lt.judge(t, real, st.st_dev, cwds, why_blind, dry_run)
        except Exception as e:      # one directory's failure is its own line: the others are still judged
            line, n = f"warning: {t} not removed: {type(e).__name__}: {e}", 0
        lines.append(line)
        freed += n
    return lines, freed


def tidy(args) -> int:
    projects = os.path.join(os.path.realpath(os.path.expanduser("~")), "projects")
    print(f"job list: {identity.jobs_path()}")
    try:
        held = held_paths()
        if not os.path.lexists(projects):
            print(f"nothing to tidy: {projects} does not exist")
            return 0
        found = trees(projects)
        projects_dev = os.stat(projects).st_dev
        if held is None and found:
            raise Unreadable(f"the job list {identity.jobs_path()} does not exist, so no open job's worktree can be told from a closed one")
    except (Unreadable, OSError) as e:
        print(f"fabric-jobs: tidy: {e}; nothing was removed", file=sys.stderr)
        return 1
    try:
        cwds, why_blind = lt.live_cwds(), ""
    except lt.Unknown as e:
        cwds, why_blind = [], str(e)
    total = 0
    for tree in found:
        try:
            lines, freed = tidy_tree(tree, projects_dev, held, cwds, why_blind, args.dry_run)
        except Exception as e:      # one tree's failure is its own line
            lines, freed = [f"warning: {tree} not tidied: {type(e).__name__}: {e}"], 0
        for line in lines:
            print(line)
        total += freed
    print(f"{'would free' if args.dry_run else 'freed'}: {lt.human(total)}")
    return 0
