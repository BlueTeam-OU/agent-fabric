"""tools/fabric/jobsparts/tidy.py — `fabric-jobs tidy [--dry-run]`: the build output of every checkout of this login that no open
job holds (the owner, 2026-10-27: /home reached 97%, about 380 GB of Rust `target` directories in four accounts, mostly the
worktrees `switch` never left). A part of tools/fabric/jobs.py, whose docstring is the contract; run daily by a user timer
as the account.

Contract. The trees are the directories directly under ~/projects that have a `.git` (a working copy, a linked worktree, a
session checkout); a link, a tree another uid owns and a tree on another filesystem than ~/projects are kept, said. A tree
that is, holds or lies in the `worktree` or `working copy` of a job that is active, queued, paused or blocked is left alone
whole. In every other tree, leave_targets' rules apply to a `target` beside a Cargo.toml and to a `node_modules` beside a
package.json, at any depth, where switch stops at 4 levels: kept, with the reason, when a process of this uid stands in it, when its `.cargo-lock` is
held, when a cargo configuration points the target elsewhere, a link, another filesystem, git tracks a file under it or cannot be asked, or
anything in it belongs to another uid;
whatever cannot be told is kept. A delivered job is not open here: its work is on a branch, and a build is cheaper than a full
disk. The first line names the job list that decides (its path), so a timer's journal says which one was read. A job list that is
absent while ~/projects holds any tree refuses: nothing removed, exit 1, the path said — read_jobs reads a missing file as "no
jobs", which under a state directory the sessions do not use would free the worktrees of every active job; an empty list that is
there is a new account's and stays valid. One line per directory, then the total. Exit 0 unless the job list is absent (with trees) or cannot be read, or ~/projects cannot be read: then nothing is
removed and the reason is said; a missing ~/projects is a fact, not an unreadable one (an account that has no checkouts).
A tree kept because an open job holds it says how much build output it keeps (measured, never removed; unknown said as unknown). The last
line is a warning when the filesystem under ~/projects is 85% full or more. --dry-run says what would go and removes nothing."""
from __future__ import annotations

import os
import shutil
import sys
from fabric_jobs.base import OPEN, STATES, identity
from fabric_jobs import leave_targets as lt

HOLDING = tuple(s for s in OPEN if s != "delivered")
# The filesystem under ~/projects warns from here: a disk that is full stops every agent of the host at once (it filled twice, 2026-10-20
# and 2026-11-13, with targets that open jobs held, which tidy rightly keeps), and 85 % leaves a day to act on the line.
WARN_USED_PERCENT = 85


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


def held_output(real: str) -> str:
    """What a tree an open job holds keeps on disk: its build output, measured and not removed. A tree kept whole was never
    measured, so the targets that filled /home were invisible to the sweep that was kept from touching them. A size that cannot
    be read is said as unknown, never as zero."""
    # os.walk says nothing of a directory it cannot list: both walks collect what they could not see, and any of it makes the
    # size unmeasurable, said so, never a smaller number or none.
    errors: list[OSError] = []
    try:
        found, _ = lt.find_targets(real, lt.BUILD_OUTPUT, errors, max_depth=None)
        seen: set[tuple[int, int]] = set()
        total = 0
        for target in found:
            for dirpath, _dirs, files in os.walk(target, followlinks=False, onerror=errors.append):
                for name in files:
                    st = os.lstat(os.path.join(dirpath, name))
                    if (st.st_dev, st.st_ino) not in seen:
                        seen.add((st.st_dev, st.st_ino))
                        total += st.st_blocks * 512
    except OSError as e:
        return f"; its build output could not be measured ({e.strerror or e})"
    if errors:
        e = errors[0]
        return f"; its build output could not be measured ({e.strerror or e}: {e.filename})"
    return f"; its build output is {lt.human(total)}" if found else ""


def disk_line(path: str) -> str | None:
    """A warning line when the filesystem holding `path` is WARN_USED_PERCENT full, None when it is not or cannot be asked."""
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    used = 100 * (usage.total - usage.free) // usage.total if usage.total else 0
    if used < WARN_USED_PERCENT:
        return None
    return f"warning: the filesystem under {path} is {used}% full, {lt.human(usage.free)} free"


def tidy_tree(tree: str, projects_dev: int, held: dict[str, str], cwds: list[str], why_blind: str, dry_run: bool) -> tuple[list[str], int]:
    if os.path.islink(tree):
        return [f"kept {tree}: a link, not followed"], 0
    real = os.path.realpath(tree)
    for path, job in held.items():
        if lt.overlaps(real, path):
            return [f"kept {tree}: it is, holds or lies in a checkout of open job {job}{held_output(real)}"], 0
    st = os.lstat(real)
    if st.st_uid != os.getuid():
        return [f"kept {tree}: owned by another account"], 0
    if st.st_dev != projects_dev:
        return [f"kept {tree}: on another filesystem"], 0
    found, links = lt.find_targets(real, lt.BUILD_OUTPUT, max_depth=None)
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
    warning = disk_line(projects)
    if warning:
        print(warning)
    return 0
