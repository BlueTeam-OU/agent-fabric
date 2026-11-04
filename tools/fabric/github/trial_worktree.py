"""tools/fabric/github/trial_worktree.py — the scratch worktree of a
trial-merge run: made under the scratch directory, the branches merged into
it, and everything it left removed however the run ended (a killed run's
leftovers swept by the next one). Split out of trial_merge.py (8d26c88a);
its contract is that module's header."""
from __future__ import annotations

import glob
import os
import random
import select
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

# How many times each of cleanup's signal passes scans for the check's
# processes (signal_all).
SWEEP_PASSES = 20
# How long the check's processes have to end on TERM before they are
# killed, and how long a KILL is waited for: a process that ignores TERM
# must not outlive the worktree it runs in (audit F15).
TERM_GRACE_S = 5.0
KILL_WAIT_S = 5.0


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
    mine = os.getpid()
    return [int(name) for name in os.listdir("/proc")
            if name.isdigit() and int(name) != mine and owned(int(name), wt, cpid)]


def owned(pid: int, wt: str, cpid: int | None) -> bool:
    """Is pid, as it is now, one of the trial's (worktree_procs' rule)?"""
    p = f"/proc/{pid}"
    try:
        if os.stat(p).st_uid != os.getuid():
            return False
        if cpid is not None:
            with open(f"{p}/stat", encoding="utf-8", errors="replace") as fh:
                # comm may hold ") ": the fields start after the last one.
                if int(fh.read().rsplit(") ", 1)[1].split()[3]) == cpid:
                    return True
        cwd = os.readlink(f"{p}/cwd")
    except (OSError, ValueError, IndexError):
        return False
    return cwd == wt or cwd.startswith(wt + "/")


def claim(pid: int, wt: str, cpid: int | None) -> int | None:
    """A pidfd on pid, kept only if the process it holds is the trial's once
    it is open. A pid is a name the kernel hands out again; the pidfd is the
    process: one taken after a listing that named a since-reused pid holds
    the stranger, and the ownership test after opening refuses it; one held
    past its process's end signals nothing, never the pid's next holder."""
    try:
        fd = os.pidfd_open(pid)
    except OSError:
        return None
    if owned(pid, wt, cpid):
        return fd
    os.close(fd)
    return None


def send(fd: int, sig: int) -> None:
    try:
        signal.pidfd_send_signal(fd, sig)
    except OSError:
        pass


def ended(fd: int) -> bool:
    """A pidfd reads ready once its process has exited, child or not."""
    return bool(select.select([fd], [], [], 0)[0])


def wait_ended(fds: list[int], seconds: float) -> bool:
    """Until every process has exited, or seconds pass; True if all did."""
    deadline = time.monotonic() + seconds
    left = [fd for fd in fds if not ended(fd)]
    while left:
        wait = deadline - time.monotonic()
        if wait <= 0:
            return False
        ready = select.select(left, [], [], min(wait, 0.5))[0]
        left = [fd for fd in left if fd not in ready]
    return True


def signal_all(claimed: dict[int, int], wt: str, cpid: int | None, sig: int) -> None:
    """sig to every live process claimed so far, then to each the scans find.
    Unlike killpg, a /proc scan is not atomic against fork: a member
    signalled just after it forked leaves a child the listing missed (sh's
    `cd / && sleep &` subshell forking its sleep, under load). So scan again
    until a pass finds no member not yet signalled; a process with a fatal
    signal pending cannot complete a fork, so this ends. The bound is for a
    member that catches TERM and keeps forking; a KILL pass cannot meet one.
    A claimed pid whose process has ended is fresh again: the pid may name a
    new member now."""
    for fd in claimed.values():
        if not ended(fd):
            send(fd, sig)
    for _ in range(SWEEP_PASSES):
        fresh = [pid for pid in worktree_procs(wt, cpid) if pid not in claimed or ended(claimed[pid])]
        if not fresh:
            break
        for pid in fresh:
            fd = claim(pid, wt, cpid)
            if fd is None:
                continue
            if pid in claimed:
                os.close(claimed[pid])
            claimed[pid] = fd
            send(fd, sig)


def terminate(pid: int, group: bool = False) -> None:
    try:
        (os.killpg if group else os.kill)(pid, signal.SIGTERM)
    except OSError:
        pass


def unreaped(pid: int) -> bool:
    """Is pid this process's child, not yet waited for? Then the number is
    still its, and so is the group it leads: no one else can be given it."""
    try:
        os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except ChildProcessError:
        return False
    return True


def cleanup(top: str, wt: str, cpid: int | None) -> None:
    # The check runs in its own process group so that a killed run takes the
    # whole check with it; an orphaned build would outlive the worktree.
    # The group is killed at the end even when the check exited on its own:
    # whatever it started in the background (a server, a build daemon) would
    # otherwise outlive the worktree it runs in. TERM first, so that a
    # member can end cleanly; what is still there after the grace is killed,
    # and the KILL is waited for, so that nothing of the check is running
    # once this returns (audit F15: a member that ignored TERM outlived it).
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, signal.SIG_IGN)
    # killpg is atomic against fork, but a group id names a group only
    # while its leader's pid is held: once the runner is reaped and its
    # group empty, the number can be a stranger's. So the group is signalled
    # only while the runner is an unwaited child (a signal ended the run
    # during its wait); the session's members are found by the scans below
    # in either case.
    if cpid is not None and unreaped(cpid):
        terminate(cpid, group=True)
    # A /proc that cannot be listed (EMFILE) ends the signalling, never the
    # removals below.
    claimed: dict[int, int] = {}
    try:
        signal_all(claimed, wt, cpid, signal.SIGTERM)
        wait_ended(list(claimed.values()), TERM_GRACE_S)
        # Every time, not only after a grace that ran out: a member that
        # handled TERM may have forked before it ended, and the KILL pass's
        # scans find that child too.
        signal_all(claimed, wt, cpid, signal.SIGKILL)
        wait_ended(list(claimed.values()), KILL_WAIT_S)
    except OSError:
        pass
    finally:
        for fd in claimed.values():
            os.close(fd)
    # The check's runner is this process's child, unreaped when a signal
    # ended the run during its wait; every other member is reaped by its own
    # parent or by init.
    if cpid is not None:
        try:
            os.waitpid(cpid, os.WNOHANG)
        except ChildProcessError:
            pass
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
