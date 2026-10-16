"""tools/fabric/jobsparts/sweep.py — `fabric-jobs sweep`: a delivered job whose evidence has landed becomes done.
A part of tools/fabric/jobs.py, whose docstring is the contract.

`switch` looks at a delivered job's evidence once, when its agent leaves it; a supplier's work that merged later, in someone
else's pull request, stayed delivered for ever and read as open work. The test here is settle._landed's plus _reflected's, the one
`done` applies and not a second one: a PR merged, a commit or a branch tip on origin's default branch, a reply sent, a reflection
cursor closed. What differs is how the artifacts are read, because old jobs hold
free text ("PR #156 merged as 9a731b31"): a reference that cannot be resolved to a repository is a reason to stay, never a guess.

A job closes only when something landed and nothing the artifacts name is open, unreadable or unresolved: unknown stays
unknown. One gh lookup per distinct pull request in the whole run, each bounded; a lookup that fails keeps every job that
named it delivered and says why."""
from __future__ import annotations

import contextlib
import os
import re
import sys
from fabric_jobs import settle as st
from fabric_jobs import vcs
from fabric_jobs.base import FABRIC_ROOT, Job, _load, identity, mutate
from fabric_jobs.records import transition

GH_TIMEOUT_S = 30
# "branch:<name>" is the explicit form; the same word without the prefix is read as settle reads a branch artifact.
# The words that may stand before a bare "PR #N" or "#N" without making it another project's: any other word there ("gzcoord #3",
# "unreg merged #3", "gzcoord #3, #4") could be a project this registry does not know, and the number is then no pull request of the job's own.
BARE_AFTER = frozenset("on in and see via of to for the a as by from with merged open pr pull request fixes closes landed lands is was are also then plus after before per".split())
# Stands in the text for a reference already read, so a bare number after it is not mistaken for the first thing the artifact says.
XREF = " xref "
BRANCH_PREFIX = re.compile(r"\bbranch:\s*(?=[A-Za-z0-9])", re.ASCII | re.IGNORECASE)


def registry_repos() -> tuple[dict[str, str], str | None]:
    """({project: owner/repo}, why the registry could not be read). The repository is the project's first github.com remote: a
    project with remotes in two organisations is the first one's, which the registry lists as the primary."""
    wc = _load("fabric_workingcopy", os.path.join(FABRIC_ROOT, "tools", "fabric", "workingcopy.py"))
    roots = _load("fabric_roots", os.path.join(FABRIC_ROOT, "tools", "fabric", "roots.py"))
    path = roots.projects_registry(engine=FABRIC_ROOT)
    try:
        registry = wc.load_registry(path)
        projects = registry.get("projects") or {}
        out = {}
        for name, entry in projects.items():
            for remote in entry.get("remotes") or []:
                parsed = wc.parse_remote(remote)
                if parsed and parsed["host"] == "github.com" and parsed["path"].count("/") == 1:
                    out[name] = parsed["path"]
                    break
        return out, None
    except (OSError, ValueError, AttributeError) as e:
        return {}, f"{path} could not be read ({type(e).__name__}: {e})"


def _project_pattern(names: list[str]) -> re.Pattern | None:
    if not names:
        return None
    alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.compile(rf"(?<![\w./-])({alt})(?:\s+PR\s*#?\s*|\s*#\s*)([1-9][0-9]{{0,8}})\b", re.ASCII | re.IGNORECASE)


def read_artifacts(job: Job, repos: dict[str, str], named: re.Pattern | None) -> tuple[dict, list[str]]:
    """({"prs": [(repo, n)], "shas": [...], "replies": [...]}, [the pull-request references that name no repository]) for one job.
    A bare "PR #N" or "#N" is in the job's own project unless another word stands before it; a sha is read only from an artifact
    that names the job's own project, the one whose working copy there is to ask."""
    prs: list[tuple[str, str]] = []
    unresolved: list[str] = []
    shas: list[str] = []
    replies: list[str] = []
    own = job.get("project")
    for art in job.get("artifacts") or []:
        replies += [m.group(1).lower() for m in st.REPLY.finditer(str(art))]
        text = st.MESSAGE_ID.sub(" ", str(art))
        for m in st.PR_URL.finditer(text):
            prs.append((m.group(1), m.group(2)))
        text = st.PR_URL.sub(XREF, text)
        for m in st.PR_FULL.finditer(text):
            prs.append((m.group(1), m.group(2)))
        text = st.PR_FULL.sub(XREF, text)
        if named:
            for m in named.finditer(text):
                project = next(p for p in repos if p.lower() == m.group(1).lower())
                prs.append((repos[project], m.group(2)))
            text = named.sub(XREF, text)
        since = 0
        for m in st.PR_BARE.finditer(text):
            # Everything between the last resolved reference and this one must be filler: any other word may name another repository.
            stray = [w for w in re.findall(r"[\w.-]+", text[since:m.start()]) if w.lower() not in BARE_AFTER]
            if stray:
                unresolved.append(f"#{m.group(1)} stands after {' '.join(stray)[:40]!r}, so it may be another repository's")
            elif own in repos:
                prs.append((repos[own], m.group(1)))
                since = m.end()
            else:
                unresolved.append(f"#{m.group(1)} (the job's project {own or 'is not set'} is not in the registry)")
        if own and re.search(rf"(?<![\w./-]){re.escape(own)}(?![\w.-])", str(art), re.IGNORECASE):
            shas += [m.group(0) for m in st.SHA.finditer(st.PR_URL.sub(" ", st.MESSAGE_ID.sub(" ", str(art))))]
    return {"prs": list(dict.fromkeys(prs)), "shas": list(dict.fromkeys(shas)), "replies": list(dict.fromkeys(replies))}, unresolved


def branch_view(job: Job) -> Job:
    """The job as settle reads branches: `branch:<name>` is the name alone, which is all settle's branch reading takes."""
    return {**job, "artifacts": [BRANCH_PREFIX.sub(" ", str(a)) for a in job.get("artifacts") or []]}


class PrStates:
    """gh's answer per distinct pull request, asked once for the whole run; a failed answer is remembered too, so a PR that cannot
    be read is not asked again by every job that names it."""

    def __init__(self) -> None:
        self.answers: dict[tuple[str, str], str | Exception] = {}

    def __call__(self, repo: str, number: str) -> str:
        key = (repo.lower(), number)
        if key not in self.answers:
            try:
                self.answers[key] = str(vcs.gh.pr_view(int(number), ["state"], repo=repo, timeout=GH_TIMEOUT_S).get("state") or "")
            except (vcs.gh.GhError, ValueError) as e:
                self.answers[key] = e
        answer = self.answers[key]
        if isinstance(answer, Exception):
            raise answer
        return answer


def verdict(job: Job, repos: dict[str, str], named: re.Pattern | None, states: PrStates) -> tuple[list[str], list[str]]:
    """(the evidence that landed, the reasons the job stays). The job closes when the first is non-empty and the second empty."""
    found, unresolved = read_artifacts(job, repos, named)
    problems: list[str] = []
    if not job.get("artifacts") and job.get("topic") != "reflection":
        return [], ["no artifacts"]
    landed = st._landed(branch_view(job), found, problems, pr_state=states)
    # settle's done path asks the same of a reflection job: a pass lands no PR, its evidence is the closed cursor (ADR-058).
    landed += st._reflected(job, problems)
    problems += [f"unresolved: {u}" for u in unresolved]
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
    repos, why = registry_repos()
    if why:
        print(f"fabric-jobs: free-text pull request references are not resolved: {why}", file=sys.stderr)
    named = _project_pattern(list(repos))
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
                transition(d, job, "done", note="swept: " + "; ".join(closes[job["id"]]))
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
