"""tools/fabric/control/branches_op.py — each account's local branches and worktrees, on the control plane
(ADR-029; ADR-022; owner's request 2026-10-10: the weekly sweep stopped because the session-start nudge was the
only trigger).

  `branches`        a read op: per working copy of this account, the last sweep, how many local branches and
                    linked worktrees there are, and how many are wholly on the default branch. No fetch and
                    no change: the counts are as fresh as the last fetch (`fetched_age_s` says how old).
  `branches-sweep`  an ACTION (sign ACTION_OPS): in each working copy with no uncommitted change and no build
                    or suite running in it, the sweep fabric-branches runs (tools/fabric/branches.py --sweep),
                    which records itself as fabric-branches does. It takes no arguments.

A working copy is a directory one level under ~/projects whose `.git` is a directory: a linked worktree has
a `.git` file and is reached through its main copy. The work is branches.py, run as this login by argv in
the copy: no field of a request reaches it. What leaves the account is the copy's directory name, branch
names, counts and times: no path, no commit, no process id.

WHAT A SWEEP LEAVES ALONE, beyond what branches.py keeps (a branch with a commit off the default branch, a
dirty or locked or ignored-file worktree, the current branch):
  - a copy with uncommitted changes (`skipped`, "uncommitted changes"): branches.py would refuse it too, but
    the account says so without a fetch;
  - a copy where a build or suite of this login runs (`skipped`, "busy: cargo"): a process whose working
    directory is inside the copy or one of its worktrees and which is a RUNNERS entry or a test script. An
    agent's own shell or harness is not busy: it is the thing a sweep is for;
  - a linked worktree a process of this login stands in (any process, a shell included): handed to branches.py
    as AGENT_FABRIC_BRANCHES_KEEP, so a session sitting in a merged worktree keeps its directory.
A copy whose process table cannot be read is skipped as "busy: unknown", never swept.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from typing import Any, Callable

from control.ops import util

READ_TIMEOUT_S = 60
# branches.py's fetch alone may take 600 s: one copy's bound; the op's budget is for all of them.
SWEEP_TIMEOUT_S = 1500
BRANCHES_SWEEP_BUDGET_S = 3600
NAME_MAX = 200
LIST_MAX = 50
# A build or suite by the name it runs under. Closed: a process outside it is not a reason to skip a sweep.
RUNNERS = frozenset({"cargo", "rustc", "pytest", "npm", "npx", "pnpm", "yarn", "make", "gradle", "mvn", "flutter", "dart",
                     "tox", "go", "ninja", "cmake", "tsc", "dotnet", "jest", "vitest", "mocha", "rake", "bundle"})
# A script by what it is for: the suites (tests/run.sh, tests/test_*.py), the static checks (tools/checks/*.sh).
TEST_SCRIPT = re.compile(r"(?:^|/)tests?/(?:run\.sh|test_[^/]*\.py)$|(?:^|/)test_[^/]*\.(?:py|sh)$|(?:^|/)checks/[^/]*\.sh$"
                         r"|(?:^|/)static\.sh$")
# `python -m unittest` and `python -m pytest`: the module is the runner.
MODULE_RUNNERS = frozenset({"unittest", "pytest"})
DELETED = re.compile(r"deleted (\S+) \([0-9a-f]+\)")
# The line a sweep says last about what it left: names separated by spaces (a branch name has none).
OWED = re.compile(r"kept, with commits off \S+: (.*) — work still owed, or the person's decision")
REMOVED_WORKTREE = re.compile(r"removed worktree (.+)")
KEPT_BRANCH = re.compile(r"KEPT (?!worktree )(\S+)(?: — .*)?")


def _tool(root: str) -> str:
    return os.path.join(root, "tools", "fabric", "branches.py")


def _default_root(home: str) -> str:
    env = os.environ.get("AGENT_FABRIC_ROOT")
    return os.path.join(home, "projects", "agent-fabric") if env is None else env


def working_copies(home: str) -> list[tuple[str, str]]:
    """(name, path) of every working copy one level under ~/projects: a real directory (a symlink is never
    followed) with a `.git` directory. Sorted by name."""
    root = os.path.join(home, "projects")
    try:
        entries = sorted(e.name for e in os.scandir(root) if e.is_dir(follow_symlinks=False) and not e.name.startswith("."))
    except OSError:
        return []
    return [(n, os.path.join(root, n)) for n in entries
            if os.path.isdir(os.path.join(root, n, ".git")) and not os.path.islink(os.path.join(root, n, ".git"))]


def processes(proc: str = "/proc", me: int | None = None) -> list[dict] | None:
    """Every process of this login the process table lets be read: {pid, cwd, argv}. A process that ends
    while it is read is left out (it is gone); None when /proc itself cannot be listed, which is not an empty
    table."""
    me = os.getpid() if me is None else me
    try:
        names = [n for n in os.listdir(proc) if n.isdigit()]
    except OSError:
        return None
    found = []
    for n in names:
        if int(n) == me:
            continue
        try:
            if os.stat(os.path.join(proc, n)).st_uid != os.getuid():
                continue
            cwd = os.readlink(os.path.join(proc, n, "cwd"))
            with open(os.path.join(proc, n, "cmdline"), "rb") as fh:
                argv = [a.decode("utf-8", "replace") for a in fh.read().split(b"\0") if a]
        except OSError:
            continue
        found.append({"pid": int(n), "cwd": cwd, "argv": argv})
    return found


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def runner_of(argv: list[str]) -> str | None:
    """The name of the build or suite an argv is, or None. The command and, behind an interpreter, the script
    are looked at; nothing else of the line is."""
    if not argv:
        return None
    words = [os.path.basename(argv[0])]
    if words[0] in ("bash", "sh", "python", "python3", "fabric-python", "node") or words[0].startswith("python"):
        if "-m" in argv[1:-1] and argv[argv.index("-m") + 1] in MODULE_RUNNERS:
            return argv[argv.index("-m") + 1]
        script = next((a for a in argv[1:] if not a.startswith("-")), "")
        words.append(script)
    for w in words:
        if os.path.basename(w) in RUNNERS:
            return os.path.basename(w)
        if TEST_SCRIPT.search(w):
            return os.path.basename(w)
    return None


def busy_runner(procs: list[dict], roots: list[str]) -> str | None:
    """The first build or suite running inside any of the roots (a copy and its linked worktrees)."""
    for p in procs:
        if any(_inside(p["cwd"], r) for r in roots):
            name = runner_of(p["argv"])
            if name:
                return name
    return None


def in_use(procs: list[dict], worktrees: list[str]) -> list[str]:
    """The linked worktrees a process of this login has as, or under, its working directory."""
    return [w for w in worktrees if any(_inside(p["cwd"], w) for p in procs)]


def _child(copy: str, args: list[str], timeout: float, keep: list[str], root: str, run: Callable[..., Any]) -> Any:
    # GIT_OPTIONAL_LOCKS=0: a read must not take the index lock an agent's concurrent `git add` wants.
    env = {**os.environ, "AGENT_FABRIC_BRANCHES_KEEP": "\n".join(keep), "GIT_OPTIONAL_LOCKS": "0"}
    return run([sys.executable, _tool(root), *args], cwd=copy, capture_output=True, text=True, errors="replace",
               timeout=timeout, check=False, stdin=subprocess.DEVNULL, env=env)


def _name(v: Any) -> str:
    return str(v)[:NAME_MAX]


def _report_one(name: str, copy: str, procs: list[dict] | None, root: str, run: Callable[..., Any], now: float) -> dict:
    try:
        r = _child(copy, ["--json"], READ_TIMEOUT_S, [], root, run)
    except subprocess.TimeoutExpired:
        return {"working_copy": name, "status": "failed", "why": f"no answer in {READ_TIMEOUT_S} s"}
    except OSError as e:
        return {"working_copy": name, "status": "failed", "why": f"cannot run: {type(e).__name__}"}
    if r.returncode != 0:
        return {"working_copy": name, "status": "failed", "why": "not countable: " + _exit_words(r.returncode)
                if r.returncode != 2 else "not countable: no origin, or no default branch known"}
    try:
        d = util.loads(r.stdout)
        branches, wts = d["branches"], d["worktrees"]
        if not (isinstance(branches, list) and isinstance(wts, list)):
            raise ValueError("lists")
        merged = sum(1 for b in branches if b["ahead"] == 0)
        unknown = sum(1 for b in branches if b["ahead"] is None) + sum(1 for w in wts if w["ahead"] is None)
        used = set(in_use(procs, [os.path.realpath(w["path"]) for w in wts])) if procs is not None else set()
        removable = (sum(1 for w in wts if w["ahead"] == 0 and not w["kept_because"] and os.path.realpath(w["path"]) not in used)
                     if procs is not None else None)
        fetched = d["fetched_at"]
        return {"working_copy": name, "status": "ok", "default": _name(d["default"]), "dirty": d["dirty"] > 0,
                "last_sweep": d["last_sweep"] if isinstance(d["last_sweep"], str) else None,
                "fetched_age_s": max(0, int(now - fetched)) if isinstance(fetched, (int, float)) else None,
                "branches": len(branches), "merged": merged, "worktrees": len(wts), "removable_worktrees": removable,
                "unknown": unknown}
    except (ValueError, KeyError, TypeError) as e:
        return {"working_copy": name, "status": "failed", "why": f"unreadable answer ({type(e).__name__})"}


def branches(home: str | None = None, root: str | None = None, run: Callable[..., Any] = subprocess.run,
             proc: str = "/proc", now: float | None = None) -> dict:
    """The read: one row per working copy. A copy that cannot be read is a failed row, never a missing one."""
    home = os.path.expanduser("~") if home is None else home
    root = _default_root(home) if root is None else root
    now = time.time() if now is None else now
    procs = processes(proc)
    return {"status": "ok", "working_copies": [_report_one(n, p, procs, root, run, now) for n, p in working_copies(home)]}


def _parse_sweep(out: str) -> dict:
    deleted, kept, removed = [], [], []
    for line in out.splitlines():
        if m := DELETED.fullmatch(line):
            deleted.append(_name(m[1]))
        elif m := REMOVED_WORKTREE.fullmatch(line):
            removed.append(_name(os.path.basename(m[1])))
        elif m := OWED.fullmatch(line):
            kept.extend(_name(n) for n in m[1].split(" ") if n)
        elif m := KEPT_BRANCH.fullmatch(line):
            kept.append(_name(m[1]))
    return {"deleted": deleted[:LIST_MAX], "kept": kept[:LIST_MAX], "worktrees_removed": removed[:LIST_MAX],
            "deleted_total": len(deleted), "kept_total": len(kept)}


def _worktrees_left(copy: str, keep: list[str], root: str, run: Callable[..., Any]) -> list[str] | None:
    """The linked worktrees still there after a sweep, by directory name; None when they cannot be listed
    (unknown, never "none")."""
    try:
        r = _child(copy, ["--json"], READ_TIMEOUT_S, keep, root, run)
        left = util.loads(r.stdout)["worktrees"] if r.returncode == 0 else None
        return [_name(os.path.basename(w["path"])) for w in left][:LIST_MAX] if isinstance(left, list) else None
    except (subprocess.TimeoutExpired, OSError, ValueError, KeyError, TypeError):
        return None


def _sweep_one(name: str, copy: str, proc: str, root: str, run: Callable[..., Any]) -> dict:
    row = {"working_copy": name}
    # Read again for each copy and once more just before its sweep: an earlier copy may have taken minutes.
    procs = processes(proc)
    if procs is None:
        return {**row, "status": "skipped", "why": "busy: unknown (the process table cannot be read)"}
    try:
        r = _child(copy, ["--json"], READ_TIMEOUT_S, [], root, run)
        state = util.loads(r.stdout) if r.returncode == 0 else None
    except (subprocess.TimeoutExpired, OSError, ValueError):
        r, state = None, None
    if r is not None and r.returncode == 2:
        # The tool refuses what is not a sweepable copy (no origin, no default branch): said, and the sweep goes on.
        return {**row, "status": "refused", "why": "not sweepable: no origin, or no default branch known"}
    if not isinstance(state, dict) or not isinstance(state.get("worktrees"), list) or not isinstance(state.get("dirty"), int):
        # The working copy's state could not be read: nothing to judge dirty or busy by, so nothing deleted.
        return {**row, "status": "failed", "why": "its state could not be read; nothing deleted"}
    if state["dirty"] > 0:
        return {**row, "status": "skipped", "why": "uncommitted changes"}
    worktrees = [w["path"] for w in state["worktrees"] if isinstance(w, dict) and isinstance(w.get("path"), str)]
    roots = [os.path.realpath(copy), *[os.path.realpath(w) for w in worktrees]]
    runner = busy_runner(procs, roots)
    if runner:
        return {**row, "status": "skipped", "why": f"busy: {runner}"}
    procs = processes(proc)
    if procs is None:
        return {**row, "status": "skipped", "why": "busy: unknown (the process table cannot be read)"}
    runner = busy_runner(procs, roots)
    if runner:
        return {**row, "status": "skipped", "why": f"busy: {runner}"}
    standing = set(in_use(procs, [os.path.realpath(w) for w in worktrees]))
    try:
        r = _child(copy, ["--sweep"], SWEEP_TIMEOUT_S, [w for w in worktrees if os.path.realpath(w) in standing], root, run)
    except subprocess.TimeoutExpired:
        return {**row, "status": "failed", "why": f"no end in {SWEEP_TIMEOUT_S} s; what it deleted is deleted"}
    except OSError as e:
        return {**row, "status": "failed", "why": f"cannot run: {type(e).__name__}"}
    keep = [w for w in worktrees if os.path.realpath(w) in standing]
    out = {**row, **_parse_sweep(r.stdout), "worktrees_kept": _worktrees_left(copy, keep, root, run)}
    if r.returncode == 0:
        return {**out, "status": "swept"}
    # Only a clean exit is a sweep. The precheck above already told a copy the tool refuses from one it does not,
    # so a 2 here is a git call or a fetch that failed or timed out inside the tool; 1 is a sweep it could not
    # record; a negative code is a kill. What was deleted before it is still reported. The words are fixed:
    # the tool's stderr names paths, and no path leaves the account.
    return {**out, "status": "failed", "why": _exit_words(r.returncode)}


def _exit_words(code: int) -> str:
    if code < 0:
        return f"killed by signal {-code}"
    return {1: "swept but the sweep could not be recorded", 2: "a git call or the fetch failed or timed out"}.get(code, f"exit {code}")


def takes_no_arguments(request: Any) -> bool:
    """`args` absent, or an empty object — nothing else, null included."""
    if not isinstance(request, dict) or "args" not in request:
        return True
    a = request["args"]
    return isinstance(a, dict) and not a


def branches_sweep(request: Any, home: str | None = None, root: str | None = None,
                   run: Callable[..., Any] = subprocess.run, proc: str = "/proc") -> dict:
    """The sweep, per working copy. The reply's status is `swept` when every copy was judged (a skipped or
    refused copy is a row that says so), `failed` when one could not be, and `refused` for a request that
    carries arguments."""
    if not takes_no_arguments(request):
        return {"status": "refused", "reason": "branches-sweep takes no arguments"}
    home = os.path.expanduser("~") if home is None else home
    root = _default_root(home) if root is None else root
    rows = [_sweep_one(n, p, proc, root, run) for n, p in working_copies(home)]
    return {"status": "failed" if any(r["status"] == "failed" for r in rows) else "swept", "working_copies": rows}
