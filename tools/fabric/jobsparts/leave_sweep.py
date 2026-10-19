"""tools/fabric/jobsparts/leave_sweep.py — the sweep `switch` runs for the job it leaves (j301, the owner 2026-10-19).
A part of tools/fabric/jobs.py, whose docstring is the contract.

A finished job leaves a worktree behind (and a session leaves its scratch); `fabric-branches --sweep --worktrees` (no branch is
deleted: a queued job's branch may sit at the default branch's tip) removes what is provably on a remote and says what it keeps and why. It is run as the command it is, in the job's working copy, so its
fetch, its refusals and its report are the command's own. Whatever it does or fails to do, `switch` goes on: a sweep that
cannot run is said, never a refusal to leave the job."""
from __future__ import annotations

import os
import subprocess
import sys

from fabric_jobs.base import FABRIC_ROOT

BRANCHES = os.path.join(FABRIC_ROOT, "tools", "fabric", "branches.py")
# A fetch of a large remote is the long call (branches.FETCH_TIMEOUT_S is 600): the whole sweep is bounded a little past it.
TIMEOUT_S = 900
# The lines of the report that say what was removed or kept; the listing of branches and worktrees before them is the
# command's own and stays in it.
SAID = ("removed ", "kept session scratch", "KEPT worktree", "  freed ", "  because ", "deleted ", "kept, with commits")


def after_leaving(working_copy: str | None, here: str | None) -> list[str]:
    """The report of the sweep in the left job's working copy, or the one line saying why there is none. `here` (the checkout
    this session stands in, often a linked worktree of that copy) is named in use: it is never removed from under the session."""
    where = next((p for p in (working_copy, here) if p and os.path.isdir(p)), None)
    if not where:
        return ["sweep skipped: no working copy of the job is a directory"]
    env = dict(os.environ)
    env["AGENT_FABRIC_BRANCHES_KEEP"] = "\n".join(p for p in (here, env.get("AGENT_FABRIC_BRANCHES_KEEP")) if p)
    try:
        r = subprocess.run([sys.executable, BRANCHES, "--sweep", "--worktrees"], cwd=where, env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, errors="replace", timeout=TIMEOUT_S, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return [f"sweep skipped in {where}: {type(e).__name__}: {e}"]
    lines = r.stdout.splitlines()
    # The worktrees block names what is kept and why on its own lines (a removed one is "clean" there and said again below).
    block = lines[lines.index("worktrees:") + 1:] if "worktrees:" in lines else []
    block = block[:block.index("")] if "" in block else block
    kept = [l for l in block if l.startswith("  ") and not l.endswith("  clean") and "(none besides" not in l]
    said = kept + [l for l in lines if l.startswith(SAID)]
    # What the command said about itself on stderr (a registry it could not read) reaches the person even when it exits 0.
    said += [l for l in r.stderr.splitlines() if l.startswith("fabric-branches: ")]
    if r.returncode != 0:
        err = next((l for l in r.stderr.splitlines() if l.strip()), f"exit {r.returncode}")
        said.append(f"sweep of {where} did not finish (exit {r.returncode}): {err}")
    return said or [f"sweep of {where}: nothing to remove, nothing kept"]
