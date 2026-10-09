"""tools/fabric/github/trial_worktree.py — the scratch worktree of a
trial-merge run: made under the scratch directory, the branches merged into
it, and everything it left removed however the run ended (a killed run's
leftovers swept by the next one). Split out of trial_merge.py, unchanged;
its contract is that module's header."""
from __future__ import annotations

import glob
import os
import random
import shutil
import signal
import string
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import git  # noqa: E402


class Refused(Exception):
    pass


# A fresh worktree of a large base is a checkout; a merge rewrites files.
WORKTREE_TIMEOUT_S = 600


# No hook of the clone runs on anything the trial does to its worktree.
# --no-verify skips only pre-merge-commit and commit-msg; measured, the add
# ran post-checkout and reference-transaction, the merge post-merge, and an
# abort reference-transaction (git-lfs and husky install such hooks;
# reviews of #71 and #73). The removals carry it too as a guard: none was
# seen to run a hook there.
NO_HOOKS = ("-c", "core.hooksPath=/dev/null")


# Two runs at once in one repository can make an add fail for a moment
# (another run's prune, git's config lock): one add lost that race in CI.
# A few tries, each clearing only its own half-made entry, then git's own
# last line if it still fails.
ADD_PAUSES = (0.2, 0.5, 1, 2)


def pid_alive(pid_file: str) -> bool:
    try:
        with open(pid_file, encoding="ascii", errors="replace") as fh:
            pid = int(fh.read().strip())
        if pid <= 0:
            return False
        os.kill(pid, 0)
    except PermissionError:
        return True
    except (OSError, ValueError):
        return False
    return True


def sweep(top: str, scratch: str) -> None:
    """A worktree of a run that died is this tool's to clear, and only when
    its owner is gone: a concurrent run's is left alone.
    A run writes its pid right after making its worktree, so a worktree
    with none is from a run killed in that gap: dead within seconds. The
    hour is a generous margin, not a bound on how long a check may run."""
    for d in sorted(glob.glob(os.path.join(scratch, "trial-merge.*"))):
        if not os.path.isdir(d):
            continue
        if os.path.isfile(d + ".pid"):
            if pid_alive(d + ".pid"):
                continue
        else:
            try:
                if time.time() - os.stat(d).st_mtime <= 3600:
                    continue
            except OSError:
                continue
        git.run(top, *NO_HOOKS, "worktree", "remove", "--force", d, check=False)
        remove_tree(d)
        for suffix in (".pid", ".pid.tmp", ".out"):
            remove_file(d + suffix)


def remove_file(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def remove_tree(path: str) -> None:
    if os.path.islink(path):
        remove_file(path)
    else:
        shutil.rmtree(path, ignore_errors=True)


def make_worktree_dir(scratch: str) -> str:
    alphabet = string.ascii_letters + string.digits
    for _ in range(100):
        path = os.path.join(scratch, "trial-merge." + "".join(random.choices(alphabet, k=6)))
        try:
            os.mkdir(path, 0o700)
            return path
        except FileExistsError:
            continue
        except OSError:
            break
    raise Refused(f"cannot make a worktree directory under {scratch}")


def worktree_procs(wt: str, cpid: int | None) -> list[int]:
    """The group is not always the whole check: a declared lease runs it in a
    process group of its own (fabric-lease's set -m). It stays in the
    SESSION the check was given, though, wherever it moves, so every
    process of that session is the check's and is ended with it; anything
    of this login still working inside the worktree is too, as a backstop
    (a process can leave the session only by making its own, as a daemon
    does on purpose)."""
    me, mine = os.getuid(), os.getpid()
    found = []
    for name in os.listdir("/proc"):
        if not name.isdigit() or int(name) == mine:
            continue
        p = f"/proc/{name}"
        try:
            if os.stat(p).st_uid != me:
                continue
            if cpid is not None:
                with open(f"{p}/stat", encoding="utf-8", errors="replace") as fh:
                    # comm may hold ") ": the fields start after the last one.
                    if int(fh.read().rsplit(") ", 1)[1].split()[3]) == cpid:
                        found.append(int(name))
                        continue
            cwd = os.readlink(f"{p}/cwd")
        except (OSError, ValueError, IndexError):
            continue
        if cwd == wt or cwd.startswith(wt + "/"):
            found.append(int(name))
    return found


def terminate(pid: int, group: bool = False) -> None:
    try:
        (os.killpg if group else os.kill)(pid, signal.SIGTERM)
    except OSError:
        pass


def cleanup(top: str, wt: str, cpid: int | None) -> None:
    # The check runs in its own process group so that a killed run takes the
    # whole check with it; an orphaned build would outlive the worktree.
    # The group is killed at the end even when the check exited on its own:
    # whatever it started in the background (a server, a build daemon) would
    # otherwise outlive the worktree it runs in.
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, signal.SIG_IGN)
    if cpid is not None:
        terminate(cpid, group=True)
    for pid in worktree_procs(wt, cpid):
        terminate(pid)
    # Each step on its own: a git that times out (git.py's bound) must not
    # keep the scratch tree and the pid file from going (review of #71).
    for step in (lambda: git.run(top, *NO_HOOKS, "worktree", "remove", "--force", wt, check=False),
                 lambda: remove_tree(wt), lambda: remove_file(wt + ".pid"), lambda: remove_file(wt + ".out"),
                 lambda: git.run(top, "worktree", "prune", check=False)):
        try:
            step()
        except (git.GitError, OSError):
            pass


def add_worktree(top: str, wt: str, base_sha: str) -> None:
    err = ""
    for pause in ADD_PAUSES:
        r = git.run(top, *NO_HOOKS, "worktree", "add", "-q", "--detach", wt, base_sha, check=False, timeout=WORKTREE_TIMEOUT_S)
        if r.returncode == 0:
            return
        err = (r.stderr or r.stdout).strip()
        git.run(top, *NO_HOOKS, "worktree", "remove", "--force", wt, check=False)
        os.makedirs(wt, exist_ok=True)
        time.sleep(pause)
    raise Refused(f"git worktree add failed ({err.split(chr(10))[-1]}); nothing tried")


def merge_all(wt: str, shas: list[str], names: list[str]) -> tuple[str, str, list[str], str, str]:
    """(result, failed_ref, conflicted, tree, merge_err). The clone's hooks
    are not run: this merge is never committed anywhere (NO_HOOKS)."""
    for name, sha in zip(names, shas):
        r = git.run(wt, "-c", "user.name=trial-merge", "-c", "user.email=trial-merge@invalid",
                    "-c", "commit.gpgsign=false", *NO_HOOKS,
                    "merge", "-q", "--no-ff", "--no-edit", "--no-verify", sha,
                    check=False, timeout=WORKTREE_TIMEOUT_S)
        if r.returncode != 0:
            d = git.run(wt, "diff", "--name-only", "--diff-filter=U", check=False).stdout
            conflicted = [p for p in d.split("\n") if p]
            git.run(wt, *NO_HOOKS, "merge", "--abort", check=False)
            return ("conflicts" if conflicted else "could not merge"), name, conflicted, "", r.stderr.rstrip("\n")
    return "combines", "", [], git.run(wt, "rev-parse", "HEAD^{tree}", check=False).stdout.strip(), ""
