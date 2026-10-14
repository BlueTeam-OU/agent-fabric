"""tools/fabric/jobsparts/branching.py — the branch a job starts on, chosen before any work (ADR-037 rule 10, step 3).
A part of tools/fabric/jobs.py, whose docstring is the contract.

The order: the job's own recorded branch when it was begun and is still unmerged (a paused or a blocked job taken back); else this agent's open pull request in the
repository, when it is still addable; else, for a job that needs that pull request merged first, a block on it; else a new branch
off the freshly fetched default branch. Whatever is chosen is never behind the default branch: an existing branch gets the default
merged into it, locally and unpushed, in a worktree of its own."""
from __future__ import annotations

import os
import re
from typing import NamedTuple
from fabric_jobs import vcs
from fabric_jobs.base import FABRIC_ROOT, Refused, _load, identity

WORK_COMMITS_MAX = 16          # the team rule: a branch holding sixteen work commits is landed, not added to
TYPES = ("feat", "fix", "docs", "chore", "test", "refactor")


class Choice(NamedTuple):
    kind: str                  # "own", "open-pr", "new" or "blocked"
    branch: str | None
    worktree: str | None
    pr: int | None = None
    repo: str | None = None
    note: str = ""


def slug_of(job: dict) -> str:
    """The job id and the first words of its title, without the parenthetical tail ("(REQUEST …)") a request adds."""
    title = re.sub(r"\([^)]*\)", " ", job["title"])
    words = re.findall(r"[a-z0-9]+", title.lower(), re.ASCII)[:6]
    return "-".join([job["id"], *words])[:48].rstrip("-")


def branch_name(job: dict, kind: str) -> str:
    return f"{identity.current_host()}/{identity.current_agent()}/{kind}/{slug_of(job)}"


def _worktree_path(wc: str, branch: str) -> str:
    return f"{os.path.realpath(wc)}-{branch.rsplit('/', 1)[-1]}"


def _checkout(wc: str, branch: str) -> str:
    """The worktree that has `branch` checked out, made beside the working copy when there is none."""
    have = vcs.worktree_of(wc, branch)
    if have:
        return have
    path = _worktree_path(wc, branch)
    if os.path.exists(path):
        raise Refused(f"{path} exists but does not have {branch} checked out: move it away, or check the branch out there")
    if vcs.local_branch_exists(wc, branch):
        vcs.run(wc, "worktree", "add", path, branch)
    else:
        vcs.run(wc, "worktree", "add", "--track", "-b", branch, path, f"origin/{branch}")
    return path


def bring_up_to_date(wc: str, branch: str, default: str) -> str:
    """The worktree of `branch`, with origin/<default> merged into it unless it already holds it. A worktree with changes, a
    branch that cannot fast-forward to its origin and a conflicting merge are each refused, the merge undone."""
    path = _checkout(wc, branch)
    if vcs.dirty(path):
        raise Refused(f"{path} has uncommitted changes on {branch}: commit them before the branch is brought up to date")
    if vcs.remote_tip(wc, branch) and not vcs.question(path, "merge-base", "--is-ancestor", f"origin/{branch}", "HEAD"):
        if vcs.run(path, "merge", "--ff-only", f"origin/{branch}", check=False).returncode != 0:
            raise Refused(f"{branch} and origin/{branch} have diverged in {path}: reconcile them first")
    if not vcs.question(path, "merge-base", "--is-ancestor", f"origin/{default}", "HEAD"):
        r = vcs.run(path, "merge", "--no-edit", f"origin/{default}", check=False, timeout=120)
        if r.returncode != 0:
            undone = vcs.run(path, "merge", "--abort", check=False).returncode == 0
            raise Refused(f"origin/{default} does not merge into {branch} cleanly in {path} "
                          f"({'merge undone' if undone else 'the merge could NOT be undone: run git merge --abort there'}): "
                          "merge it by hand, then switch again")
    return path


def _my_open_prs(repo: str) -> list[dict]:
    prefix = f"{identity.current_host()}/{identity.current_agent()}/"
    rows = vcs.gh.pr_list(["number", "headRefName", "isDraft"], repo=repo)
    return [r for r in rows if isinstance(r, dict) and str(r.get("headRefName", "")).startswith(prefix)]


def _addable(repo: str, number: int) -> str | None:
    """None when pull request `number` can take another commit, else why not."""
    counts = _load("fabric_pr_counts", os.path.join(FABRIC_ROOT, "tools", "fabric", "github", "pr_counts.py"))
    rows = counts.count_rows([f"{repo}#{number}"])
    row = rows[0] if rows else {}
    if not row.get("ok") or row.get("state") != "open" or not isinstance(row.get("work"), int):
        return f"{repo}#{number} could not be read ({row.get('error') or row.get('line') or 'no row'})"
    if row.get("armed") != "unarmed":
        return f"{repo}#{number} is {row.get('armed')}"
    if row["work"] >= WORK_COMMITS_MAX:
        return f"{repo}#{number} holds {row['work']} work commits"
    return None


def _begun(wc: str, repo: str, branch: str) -> bool:
    """Whether `branch` exists (here or on origin) and none of its pull requests merged: work begun, not landed. Git alone cannot say
    it: a branch with no commit of its own is an ancestor of the default branch, as a merged one is."""
    if not (vcs.local_branch_exists(wc, branch) or vcs.remote_tip(wc, branch)):
        return False
    return not vcs.gh.pr_list(["number"], repo=repo, state="merged", search=f"head:{branch}")


def choose(job: dict, *, kind: str, needs_merged: bool) -> Choice:
    """The branch for `job`, prepared: fetched, checked out in a worktree and up to date. Refused when it cannot be one."""
    wc = job.get("working_copy")
    if not wc or not vcs.toplevel(wc):
        raise Refused(f"{job['id']} has no working copy that is a git checkout ({wc or 'none recorded'}): no branch can be chosen; "
                      "re-add the job with --working-copy")
    try:
        vcs.fetch(wc)
        default = vcs.default_branch(wc)
        own = job.get("branch")
        repo = vcs.gh.this_repo(wc)
        if own and _begun(wc, repo, own):
            return Choice("own", own, bring_up_to_date(wc, own, default), note="the job's own branch, work already begun")
        mine = _my_open_prs(repo)
        if len(mine) > 1:
            raise Refused(f"{len(mine)} open pull requests of this login in {repo} ({', '.join('#' + str(p['number']) for p in mine)}): "
                          "one is allowed; land or close the others first")
        if mine:
            number, head = int(mine[0]["number"]), str(mine[0]["headRefName"])
            why = _addable(repo, number)
            if why is None:
                return Choice("open-pr", head, bring_up_to_date(wc, head, default), number, repo, f"your open pull request #{number}")
            if needs_merged:
                return Choice("blocked", None, None, number, repo, f"{why}; the job needs it merged")
        # A branch of the generated name may exist: this job's earlier one that a pull request landed, or one a refused
        # switch left. A new name is made beside it, never a refusal the agent has no command to clear.
        base = branch_name(job, kind)
        name = next((n for n in [base] + [f"{base}-{i}" for i in range(2, 10)]
                     if not (vcs.local_branch_exists(wc, n) or vcs.remote_tip(wc, n) or os.path.exists(_worktree_path(wc, n)))), None)
        if name is None:
            raise Refused(f"branches {base} to {base}-9 or their worktrees exist: remove the ones that are finished")
        path = _worktree_path(wc, name)
        vcs.run(wc, "worktree", "add", "--no-track", "-b", name, path, f"origin/{default}")
        return Choice("new", name, path, note=f"a new branch off origin/{default}")
    except vcs.VcsError as e:
        raise Refused(f"the branch for {job['id']} could not be chosen: {e}") from None
    except vcs.gh.GhError as e:
        raise Refused(f"the branch for {job['id']} could not be chosen: {e.reason}") from None
    except ValueError as e:        # gh printed something that is not JSON
        raise Refused(f"the branch for {job['id']} could not be chosen: gh's answer was not readable ({e})") from None
