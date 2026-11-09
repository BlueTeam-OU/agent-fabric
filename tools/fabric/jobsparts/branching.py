"""tools/fabric/jobsparts/branching.py — the branch a job starts on, chosen before any work (ADR-037 rule 10, step 3).
A part of tools/fabric/jobs.py, whose docstring is the contract.

The order: the for/ branch a supply job's request names (job["deliver_to"]), unless a pull request from it merged; else the job's own
recorded branch, always: a job that records a branch is resumed on it (its worktree recreated from the branch when gone) and is never
given another job's, so a branch that has landed or is gone from this clone and origin is refused, said, never replaced (the one
exception: a paused job asked to --repoint is taken from a landed branch to this agent's one open pull request, which may be armed
if it is in no merge queue and the repository disarms on push); only a job
with no branch gets one: this agent's open pull request in the repository, when it is still addable; else, for a job that needs that
pull request merged first, a block on it; else a new branch off the freshly fetched default branch. Whatever is chosen is never behind
the default branch: an existing branch gets the default merged into it, locally and unpushed, in a worktree of its own."""
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
    repointed: bool = False    # a paused job's landed branch replaced by the open pull request's (--repoint)


def slug_of(job: dict) -> str:
    """The job id and the first words of its title, without the parenthetical tail ("(REQUEST …)") a request adds."""
    title = re.sub(r"\([^)]*\)", " ", job["title"])
    words = re.findall(r"[a-z0-9]+", title.lower(), re.ASCII)[:6]
    return "-".join([job["id"], *words])[:48].rstrip("-")


def branch_name(job: dict, kind: str) -> str:
    return f"{identity.current_host()}/{identity.current_agent()}/{kind}/{slug_of(job)}"


def _worktree_path(wc: str, branch: str) -> str:
    return f"{os.path.realpath(vcs.main_checkout(wc))}-{branch.rsplit('/', 1)[-1]}"


def _checkout(wc: str, branch: str) -> str:
    """The worktree that has `branch` checked out, made beside the working copy when there is none."""
    have = vcs.worktree_of(wc, branch)
    if have and not os.path.isdir(have):
        # A swept worktree stays registered until pruned, and `worktree add` refuses a branch it still shows checked out there.
        vcs.run(wc, "worktree", "prune")
        have = None
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


def _row(repo: str, number: int) -> dict:
    counts = _load("fabric_pr_counts", os.path.join(FABRIC_ROOT, "tools", "fabric", "github", "pr_counts.py"))
    rows = counts.count_rows([f"{repo}#{number}"])
    return rows[0] if rows else {}


def _judge(row: dict, repo: str, number: int, held_ok: bool = False) -> str | None:
    """None when the pull request `row` describes can take another commit, else why not. `held_ok`: an armed pull request that is in no
    merge queue takes one (its first push disarms it); a queued one never does, a push races the queue."""
    if not row.get("ok") or row.get("state") != "open" or not isinstance(row.get("work"), int):
        return f"{repo}#{number} could not be read ({row.get('error') or row.get('line') or 'no row'})"
    if row.get("armed") != "unarmed" and not (held_ok and row.get("armed") == "armed"):
        return f"{repo}#{number} is {row.get('armed')}"
    if row["work"] >= WORK_COMMITS_MAX:
        return f"{repo}#{number} holds {row['work']} work commits"
    return None


def _addable(repo: str, number: int) -> str | None:
    return _judge(_row(repo, number), repo, number)


def _landed(wc: str, repo: str, branch: str) -> bool:
    """Whether a pull request from `branch` merged: its delivery is on the default branch and the name is spent."""
    return bool(vcs.gh.pr_list(["number"], repo=repo, state="merged", search=f"head:{branch}"))


def _no_disarm(repo: str, default: str) -> str | None:
    """None when `repo` is known to disarm an armed pull request on a push (the workflow disarm-on-push.yml on its default branch, or a
    ruleset on it requiring fabric/armed, so a head pushed later waits for its own arming), else why that is not known. Fail closed: a
    read that fails or an answer of another shape is "not known", never "does": the note "the first push disarms it" is printed only
    where this holds, and elsewhere an armed pull request would keep its arming on a head nobody reviewed (coordinator, 2026-11-09)."""
    reasons = []
    try:
        vcs.gh.api(f"repos/{repo}/contents/.github/workflows/disarm-on-push.yml?ref={default}")
        return None
    except vcs.gh.GhError as e:
        reasons.append("no disarm-on-push.yml on " + default if e.status == 404 else f"the workflow could not be read ({e.reason})")
    try:
        rules = vcs.gh.api(f"repos/{repo}/rules/branches/{default}")
        if not isinstance(rules, list):
            reasons.append("the rules could not be read (not a list)")
        elif any(isinstance(r, dict) and r.get("type") == "required_status_checks"
                 and any(isinstance(c, dict) and c.get("context") == "fabric/armed"
                         for c in ((r.get("parameters") or {}).get("required_status_checks") or []))
                 for r in rules):
            return None
        else:
            reasons.append(f"no rule on {default} requires fabric/armed")
    except (vcs.gh.GhError, AttributeError, TypeError) as e:
        reasons.append(f"the rules could not be read ({getattr(e, 'reason', e)})")
    return "; ".join(reasons)


def _repoint(wc: str, repo: str, job: dict, landed: str, default: str) -> Choice:
    """A paused job whose branch a pull request landed, taken to this agent's one open pull request in the repository (j641): the work
    continued there. Never a pick among several, and never a pull request that cannot take more commits: the refusal says which."""
    mine = _my_open_prs(repo)
    if len(mine) != 1:
        found = f"{len(mine)} open pull requests of this login in {repo}" + (f" ({', '.join('#' + str(p['number']) for p in mine)})" if mine else "")
        raise Refused(f"{job['id']} records branch {landed}, which a pull request has landed, and --repoint needs exactly one open pull request "
                      f"of this login to take it to: {found}; close {job['id']} (fabric-jobs done or drop), or switch to another job by its id")
    number, head = int(mine[0]["number"]), str(mine[0]["headRefName"])
    row = _row(repo, number)     # one read: the verdict and the armed note must describe the same pull request
    why = _judge(row, repo, number, held_ok=True)
    if why is not None:
        raise Refused(f"{job['id']} records branch {landed}, which a pull request has landed, and the one open pull request cannot take it: {why}")
    if row.get("armed") == "armed":
        unsafe = _no_disarm(repo, default)
        if unsafe is not None:
            raise Refused(f"{job['id']} records branch {landed}, which a pull request has landed, and the one open pull request #{number} is armed "
                          f"and {repo} is not known to disarm it on push: {unsafe}; unarm it, or close {job['id']} (fabric-jobs done or drop)")
    armed = "; it is armed (held, in no merge queue): the first push disarms it" if row.get("armed") == "armed" else ""
    return Choice("open-pr", head, bring_up_to_date(wc, head, default), number, repo,
                  f"re-pointed from {landed}, which a pull request landed, to your open pull request #{number}{armed}", repointed=True)


def _resume(wc: str, repo: str, job: dict, default: str, repoint: bool) -> Choice:
    """The job's recorded branch, prepared. One that is on neither this clone nor origin, or that a pull request landed, is refused
    and said: replacing it would hand the job a branch that is another's work (j511 got j513's). A paused job asked to `repoint` is the
    one exception for a landed branch."""
    own = job["branch"]
    # Landed is asked first: a merged branch is usually deleted too, and "restore it" would be the wrong advice for it.
    if _landed(wc, repo, own):
        if repoint and job["state"] == "paused":
            return _repoint(wc, repo, job, own, default)
        offer = ("; --repoint takes a paused job to this login's one open pull request" if job["state"] == "paused"
                 else f"; --repoint was asked and applies only to a paused job ({job['id']} is {job['state']})" if repoint else "")
        raise Refused(f"{job['id']} records branch {own}, which a pull request has landed: it is not replaced; close {job['id']} "
                      f"(fabric-jobs done or drop), or switch to another job by its id{offer}")
    if not (vcs.local_branch_exists(wc, own) or vcs.remote_tip(wc, own)):
        raise Refused(f"{job['id']} records branch {own}, which is on neither this clone nor origin: it is not replaced; restore the branch, "
                      f"or drop {job['id']} and add its work again")
    return Choice("own", own, bring_up_to_date(wc, own, default), note="the job's own branch, work already begun")


def _checkout_of(job: dict) -> str:
    """A git checkout to ask in: the job's working copy, or, for a job with a branch of its own whose worktree is gone (a sweep removed
    it), the checkout it was made beside (`_worktree_path` names a worktree <checkout>-<last segment of the branch>), where it is made again."""
    wc = job.get("working_copy")
    if wc and vcs.toplevel(wc):
        return wc
    own = job.get("branch")
    suffix = f"-{own.rsplit('/', 1)[-1]}" if own else None
    for path in (job.get("worktree"), wc):
        if suffix and path and path.endswith(suffix) and vcs.toplevel(path[:-len(suffix)]):
            return path[:-len(suffix)]
    raise Refused(f"{job['id']} has no working copy that is a git checkout ({wc or 'none recorded'}): no branch can be chosen; "
                      f"name one with fabric-jobs project {job['id']} {job.get('project') or '<project>'} --working-copy DIR")


def choose(job: dict, *, kind: str, needs_merged: bool, repoint: bool = False) -> Choice:
    """The branch for `job`, prepared: fetched, checked out in a worktree and up to date. Refused when it cannot be one."""
    wc = _checkout_of(job)
    try:
        vcs.fetch(wc)
        default = vcs.default_branch(wc)
        own = job.get("branch")
        repo = vcs.gh.this_repo(wc)
        supply = job.get("deliver_to")
        # A job that began on another branch keeps it: the name may have been recorded after its work started.
        if supply and (not own or own == supply) and not _landed(wc, repo, supply):
            if vcs.local_branch_exists(wc, supply) or vcs.remote_tip(wc, supply):
                return Choice("own", supply, bring_up_to_date(wc, supply, default), note="the for/ branch the request names, the job's to deliver on")
            path = _worktree_path(wc, supply)
            if os.path.exists(path):
                raise Refused(f"{path} exists but does not have {supply} checked out: move it away, or check the branch out there")
            vcs.run(wc, "worktree", "add", "--no-track", "-b", supply, path, f"origin/{default}")
            return Choice("new", supply, path, note=f"the for/ branch the request names, new off origin/{default}")
        if own:
            return _resume(wc, repo, job, default, repoint)
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
        # A branch of the generated name may exist: one a pull request landed that no job records, or one a refused
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
