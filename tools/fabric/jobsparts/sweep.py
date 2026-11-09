"""tools/fabric/jobsparts/sweep.py — `fabric-jobs sweep`: a delivered job whose evidence has landed becomes done.
A part of tools/fabric/jobs.py, whose docstring is the contract.

`switch` looks at a delivered job's evidence once, when its agent leaves it; a supplier's work that merged later, in someone
else's pull request, stayed delivered for ever and read as open work. The test here is settle.done_test, the one `done` applies
and not a second one: a PR merged, a commit or a branch tip on origin's default branch, a reply sent, a reflection cursor
closed, the artifacts read by artifacts.py as `done` reads them. What is sweep's own is that no one stands at the job's
checkout: old jobs hold free text ("PR #156 merged as 9a731b31"), and a bare #N that names no repository is a reason to stay,
never a guess.

A job closes only when something landed and nothing the artifacts name is open, unreadable or unresolved: unknown stays
unknown. One gh lookup per distinct pull request in the whole run, each bounded; a lookup that fails keeps every job that
named it delivered and says why."""
from __future__ import annotations

import contextlib
import re
import sys
from fabric_jobs import artifacts, needs
from fabric_jobs import settle as st
from fabric_jobs import vcs
from fabric_jobs.base import Job, identity, mutate
from fabric_jobs.records import transition

GH_TIMEOUT_S = 30


class PrStates:
    """gh's answer per distinct pull request, asked once for the whole run; a failed answer is remembered too, so a PR that cannot
    be read is not asked again by every job that names it. The head is a second question, asked only for a merged PR beside an
    un-folded branch."""

    def __init__(self) -> None:
        self.answers: dict[tuple[str, str], str | Exception] = {}
        self.heads: dict[tuple[str, str], str | Exception] = {}

    def _ask(self, cache: dict, field: str, repo: str, number: str) -> str:
        key = (repo.lower(), number)
        if key not in cache:
            try:
                cache[key] = str(vcs.gh.pr_view(int(number), [field], repo=repo, timeout=GH_TIMEOUT_S).get(field) or "")
            except (vcs.gh.GhError, ValueError) as e:
                cache[key] = e
        answer = cache[key]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def __call__(self, repo: str, number: str) -> str:
        return self._ask(self.answers, "state", repo, number)

    def head(self, repo: str, number: str) -> str:
        return self._ask(self.heads, "headRefOid", repo, number)


def verdict(job: Job, repos: dict[str, str], named: re.Pattern | None, states: PrStates) -> tuple[list[str], list[str]]:
    """(the evidence that landed, the reasons the job stays). The job closes when the first is non-empty and the second empty.
    The test is settle's, the one `done` applies; what is sweep's own is that no one is at the job's checkout to say what a bare
    #N means (bare_repo None: it stays, unresolved) and the reasons a person reads in its report."""
    problems: list[str] = []
    if not job.get("artifacts") and job.get("topic") != "reflection":
        return [], ["no artifacts"]
    landed = st.done_test(job, problems, bare_repo=None, repos=repos, named=named, pr_state=states, pr_head=states.head)
    explicit = [n for a in job.get("artifacts") or [] for n in re.findall(r"\bbranch:\s*(\S+)", str(a), re.IGNORECASE)]
    if explicit and not landed and not problems:
        problems.append(f"branch {', '.join(explicit)} is not on origin, or its name is no ref this sweep can ask for")
    if not landed and not problems:
        problems.append("no artifact names a pull request, a commit or a branch it can resolve: " + "; ".join(repr(str(a)[:60]) for a in (job.get("artifacts") or [])[:3]))
    return landed, problems


@contextlib.contextmanager
def one_fetch_per_checkout():
    """settle's checks fetch for every job they look at; a sweep over dozens of jobs of one working copy fetches it once, and a fetch
    that failed fails the same way for the jobs after it, instead of timing out again for each."""
    real, seen = vcs.fetch, {}

    def fetch(repo: str) -> None:
        if repo not in seen:
            try:
                real(repo)
                seen[repo] = None
            except vcs.VcsError as e:
                seen[repo] = e
        if seen[repo] is not None:
            raise seen[repo]
    vcs.fetch = fetch
    try:
        yield
    finally:
        vcs.fetch = real


def sweep(args) -> int:
    """sweep [--dry-run]: every delivered job on this list whose evidence has landed becomes done, with a note naming the evidence."""
    doc = identity.read_jobs()
    delivered = [j for j in doc["jobs"] if j["state"] == "delivered"]
    repos, why = artifacts.registry_repos()
    if why:
        print(f"fabric-jobs: free-text pull request references are not resolved: {why}", file=sys.stderr)
    named = artifacts.project_pattern(list(repos))
    states = PrStates()
    with one_fetch_per_checkout():
        verdicts = {j["id"]: (list(j.get("artifacts") or []), *verdict(j, repos, named, states)) for j in delivered}
    closes = {jid: ev for jid, (_, ev, why_not) in verdicts.items() if ev and not why_not}
    applied: dict[str, str] = {}
    if closes and not args.dry_run:
        def close(d):
            for job in d["jobs"]:
                if job["id"] not in closes:
                    continue
                if job["state"] != "delivered" or list(job.get("artifacts") or []) != verdicts[job["id"]][0]:
                    applied[job["id"]] = "changed while the sweep ran"       # the evidence was read from another job than this one
                    continue
                transition(d, job, "done", "sweep", needs.done_proof(job, closes[job["id"]]), note="swept: " + "; ".join(closes[job["id"]]))
                applied[job["id"]] = ""
        mutate(close)
    if not delivered:
        print("no delivered jobs")
    for job in delivered:
        _, ev, why_not = verdicts[job["id"]]
        head = f"{job['id']}  {job['title'][:60]}"
        if job["id"] in closes and applied.get(job["id"], "") == "":
            print(f"{head}: {'would close' if args.dry_run else 'closed'} ({'; '.join(ev)})")
        elif job["id"] in closes:
            print(f"{head}: stays ({applied[job['id']]})")
        else:
            print(f"{head}: stays ({'; '.join(why_not)})")
    return 0
