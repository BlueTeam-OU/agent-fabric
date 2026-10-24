#!/usr/bin/env python3
"""tools/fabric/github/pr_counts.py — fabric-pr counts: one pasteable line per
pull request, across repositories.

    fabric-pr counts <ref>… [--json] [--timeout S]

A ref is `167` (a pull request of this checkout's repository), `myproject#1075`
(a project id, or the name of a project's repository, from
projects/registry.json) or `owner/repo#N`; a leading `#` is allowed. One line
per ref, in the order given:

    #167 (9 work, 2 fix) open, armed, checks pending, head reviewed: claude ✓ codex ✓ (head 6bc0ad18)
    myproject#1075 (4 work, 3 fix) open, unarmed, checks red, review claude ✓ codex ✗ (head 0a1b2c3d)
    #164 (1 work, 4 fix) merged

The first token is what the Stop hook (runtime/claude-code/hooks/pr-counts.py)
asks a reply to state, so a reply can paste it. The counts are `fabric-pr
gate`'s: the commits of the pull request, classified by commit_class (the
Kind:/Answers: trailers, merges told by their parents) and netted by their
reverts by pr_split.split_rows, the function the gate's own split runs. They
are read from GitHub's commit list, one GraphQL query per repository (ten
pull requests at most per query; a query GitHub refuses is asked again one
pull request at a time), not from a clone, so any registered repository can
be asked. Open, merged and closed-unmerged pull requests are all counted.

WHAT THE LINE DOES NOT SAY. Each engine the repository's arming policy
requires of every pull request (`reviews`; every engine when the policy cannot
be read) is marked ✓ when a review object carrying the review class's marker
(the current one, the built-in earlier one, and the project's
legacy_review_markers from its pr-tools.json) and that engine's model line is
posted on the head; `head reviewed: ` opens it only when all are (a
boundary's extra engines are fabric-pr arm's to judge). An engine in
`additional_reviews` is marked as well: ✓, `unavailable (<reason>)` when its
marker for the head, from the PR's author or AGENT_FABRIC_REVIEW_POSTERS, is
the first line of a review on it, or `absent` with neither, which never keeps
`head reviewed: ` off. When a boundary also requires it, no marker stands in:
`✗ (boundary only)` replaces `absent`, or follows `unavailable (<reason>)`;
`fabric-pr review-status`, which also counts a configured reviewer's verdict,
is the gate's reading and costs several calls a pull request. `checks` is the
head's rollup state (green, red, pending, none yet). A pull request over 100
commits is read through the REST list (up to GitHub's 250); beyond that it is
`cannot be read`.

Exit: 0 every ref was read; 2 a ref could not be read (its line names why) or
the usage is wrong. A line for a ref that could not be read is
`<ref> cannot be read: <why>`; never a traceback. Stdout is the lines (--json:
one object per ref); every `fabric-pr counts: ` message is on stderr.

For the hook: `count_lines(refs, timeout)` returns the lines;
`count_rows(refs, timeout)` the rows they are made from (`ok`, `line`, `work`,
`fix`, `state`, ...).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Callable, Sequence

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402
import roots  # noqa: E402
from github import arm_policy, commit_class, review_coverage  # noqa: E402
from github.pr_split import split_rows  # noqa: E402
from github.review_status.config import BUILTIN_LEGACY_MARKER, REVIEW_MARKER  # noqa: E402
from github.review_status.verdicts import engine_of, unavailable_of  # noqa: E402

PROG = "fabric-pr counts"
DEFAULT_TIMEOUT_S = 20.0
PER_QUERY = 10
REST_COMMIT_CAP = 250
REF = re.compile(r"(?:(?P<where>[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?)?#|(?=[0-9]))(?P<n>[1-9][0-9]*)")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
FIELDS = """number state isDraft mergedAt headRefOid baseRefName author { login }
  autoMergeRequest { enabledAt } mergeQueueEntry { state }
  mergeCommit { parents(first: 2) { nodes { oid } } }
  commits(first: 100) { totalCount pageInfo { hasNextPage } nodes { commit { oid message parents(first: 3) { totalCount } } } }
  tip: commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
  reviews(last: 50) { nodes { body commit { oid } author { login } } }"""


class Unreadable(Exception):
    """A ref (or a repository) that could not be read; the message is why."""


def registry_projects() -> dict[str, dict]:
    try:
        with open(roots.projects_registry(engine=roots.code_root()), encoding="utf-8") as fh:
            doc = json.load(fh)
        projects = doc["projects"]
        if not isinstance(projects, dict):
            raise TypeError("projects is not an object")
        return projects
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise Unreadable(f"projects/registry.json cannot be read ({type(e).__name__}: {e})") from None


def remote_repos(entry: dict) -> list[str]:
    out = []
    for remote in entry.get("remotes") or []:
        m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", str(remote))
        if m:
            out.append(m.group(1))
    return out


def resolve_name(name: str, projects: dict[str, dict]) -> tuple[str, str]:
    """(owner/repo, project id) for a project id or a repository's name,
    case-insensitively; two projects answering to one name are refused."""
    low = name.lower()
    hits: dict[str, str] = {}
    for pid, entry in projects.items():
        repos = remote_repos(entry if isinstance(entry, dict) else {})
        if not repos:
            continue
        if pid.lower() == low or any(r.split("/")[1].lower() == low for r in repos):
            hits[pid] = repos[0]
    if not hits:
        raise Unreadable(f"'{name}' is no project id or repository name in projects/registry.json")
    if len(hits) > 1:
        raise Unreadable(f"'{name}' names more than one project ({', '.join(sorted(hits))}); say owner/repo#N")
    (pid, repo), = hits.items()
    return repo, pid


def project_of_repo(repo: str, projects: dict[str, dict]) -> str | None:
    for pid, entry in projects.items():
        if isinstance(entry, dict) and any(r.lower() == repo.lower() for r in remote_repos(entry)):
            return pid
    return None


def parse_ref(ref: str, projects_loader=registry_projects) -> tuple[str, str | None, str | None, int]:
    """(the label to print, owner/repo or None for this checkout's, project id
    or None, number). A ref without a repository prints as #N."""
    m = REF.fullmatch(ref)
    if not m:
        raise Unreadable(f"'{ref}' is not a ref: 167, project#167 or owner/repo#167")
    number, where = int(m.group("n")), m.group("where")
    if not where:
        return f"#{number}", None, None, number
    if "/" in where:
        if not REPO.fullmatch(where):
            raise Unreadable(f"'{where}' is not owner/repo")
        return ref, where, None, number
    repo, pid = resolve_name(where, projects_loader())
    return ref, repo, pid, number


def legacy_markers(pid: str | None) -> tuple[list[str], str]:
    """(the markers a review of this project's pull requests may carry, "" or
    why the project's own cannot be read). The built-in earlier marker, the
    project's legacy_review_markers, and the environment's, as the gate's
    readers have them."""
    markers = [REVIEW_MARKER, BUILTIN_LEGACY_MARKER]
    markers += [m for m in (os.environ.get("AGENT_FABRIC_LEGACY_REVIEW_MARKERS") or "").split("\n") if m]
    if not pid:
        return markers, ""
    path = roots.project_integration(pid, "pr-tools.json")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        listed = doc.get("legacy_review_markers", [])
        if not isinstance(listed, list) or not all(isinstance(x, str) for x in listed):
            raise TypeError("legacy_review_markers is not a list of strings")
    except FileNotFoundError:
        return markers, ""
    except (OSError, ValueError, TypeError, AttributeError) as e:
        return markers, f"{pid}'s pr-tools.json is unusable ({type(e).__name__})"
    return markers + [m for m in listed if m], ""


class Budget:
    """The call's whole time, spent across its gh calls."""

    def __init__(self, seconds: float, clock=time.monotonic):
        self.clock, self.end = clock, clock() + seconds

    def left(self) -> float:
        left = self.end - self.clock()
        if left <= 0.2:
            raise Unreadable("the time allowed ran out")
        return left


def batch_query(numbers: list[int]) -> str:
    body = "\n".join(f"  p{n}: pullRequest(number: {n}) {{ {FIELDS} }}" for n in numbers)
    return f"query($owner: String!, $name: String!) {{ repository(owner: $owner, name: $name) {{\n{body}\n}} }}"


def fetch_repo(repo: str, numbers: list[int], budget: Budget) -> dict[int, dict | Unreadable]:
    """The pull requests of one repository: a dict per number, or the
    Unreadable that says why. Ten at a time in one query; a query GitHub
    refuses (one number unknown fails the whole answer) is asked again a
    number at a time, so one bad ref does not hide the others."""
    owner, name = repo.split("/")
    out: dict[int, dict | Unreadable] = {}
    for i in range(0, len(numbers), PER_QUERY):
        chunk = numbers[i:i + PER_QUERY]
        try:
            data = gh.graphql(batch_query(chunk), timeout=budget.left(), owner=owner, name=name)
            repo_doc = data.get("repository")
            for n in chunk:
                pr = repo_doc.get(f"p{n}") if isinstance(repo_doc, dict) else None
                out[n] = pr if isinstance(pr, dict) else Unreadable(f"no pull request #{n} in {repo}")
        except gh.GhError as e:
            if len(chunk) == 1:
                out[chunk[0]] = Unreadable(f"{e.reason}")
                continue
            for n in chunk:
                try:
                    data = gh.graphql(batch_query([n]), timeout=budget.left(), owner=owner, name=name)
                    pr = (data.get("repository") or {}).get(f"p{n}")
                    out[n] = pr if isinstance(pr, dict) else Unreadable(f"no pull request #{n} in {repo}")
                except gh.GhError as e2:
                    out[n] = Unreadable(f"{e2.reason}")
    return out


def split_message(message: str) -> tuple[str, str]:
    """(subject, body) as git's %s and %b have them: the subject is the first
    paragraph with its lines joined by a space, the body what follows the
    blank line after it."""
    parts = re.split(r"\n[ \t]*\n", message.strip("\n"), maxsplit=1)
    return " ".join(ln.rstrip(" \t\r") for ln in parts[0].split("\n")), (parts[1].strip("\n") if len(parts) > 1 else "")


def check_trailers(sha: str, body: str) -> None:
    """The gate reads Kind: and Answers: where git finds them; commit_class
    reads them only from a block of pure `Key: value` lines. Where the last
    paragraph names either key yet that reading finds none, git may report
    what this cannot, so the count would be a guess."""
    paragraphs = [p for p in re.split(r"\n[ \t]*\n", body.strip("\n")) if p.strip()]
    if not paragraphs:
        return
    for key in ("Kind", "Answers"):
        named = any(re.match(rf"{key}[ \t]*:", ln, re.I) for ln in paragraphs[-1].split("\n"))
        if named and not commit_class.trailer_values(body, key):
            raise Unreadable(f"commit {sha[:10]}'s trailer block mixes {key}: with other lines, which git and the "
                             "gate may read differently; read it with fabric-pr gate")


def commit_rows(pr: dict, repo: str, number: int, budget: Budget) -> tuple[list[tuple], dict[str, str]]:
    """(rows newest first for pr_split.split_rows, sha -> body) from the
    pull request's commit list; GitHub lists them oldest first."""
    nodes = []
    commits = pr.get("commits") or {}
    if (commits.get("pageInfo") or {}).get("hasNextPage"):
        listed = gh.api(f"repos/{repo}/pulls/{number}/commits?per_page=100", paginate=True, timeout=budget.left())
        if len(listed) >= REST_COMMIT_CAP:
            raise Unreadable(f"it has {REST_COMMIT_CAP} commits or more, past what GitHub lists")
        for c in listed:
            nodes.append((c["sha"], len(c.get("parents") or []), c["commit"]["message"]))
    else:
        for node in commits.get("nodes") or []:
            c = node["commit"]
            nodes.append((c["oid"], (c.get("parents") or {}).get("totalCount", 1), c["message"]))
    rows, bodies = [], {}
    for sha, parents, message in reversed(nodes):
        subject, body = split_message(message)
        bodies[sha] = body
        check_trailers(sha, body)
        rows.append((sha, " ".join(["p"] * max(int(parents), 1)), subject, commit_class.answers_of(body),
                     commit_class.kind_of(body)))
    return rows, bodies


def checks_word(pr: dict) -> str:
    nodes = (pr.get("tip") or {}).get("nodes") or []
    rollup = ((nodes[0].get("commit") or {}).get("statusCheckRollup") if nodes else None) or {}
    state = rollup.get("state")
    return {"SUCCESS": "green", "FAILURE": "red", "ERROR": "red", "PENDING": "pending",
            "EXPECTED": "pending"}.get(state, "none yet" if state is None else f"{str(state).lower()}")


def engines_on_head(pr: dict, markers: list[str]) -> set[str]:
    """The engines (review_status's engine_of) of the marked reviews posted on the head: a v1 or legacy marker, or a v2
    review the gate counts (review_coverage reads it in full and its marker names the head). A v2 review with a path
    not read, or one that does not read, is no engine on the head, as the gate has it."""
    head = pr.get("headRefOid")

    def marked(r: dict) -> bool:
        body = r.get("body") or ""
        v2 = review_coverage.read_review(body)
        if v2 is not None:
            return v2.counts and v2.marker.head == head
        return any(m in body for m in markers)

    return {engine_of(r) for r in (pr.get("reviews") or {}).get("nodes") or []
            if (r.get("commit") or {}).get("oid") == head and marked(r)}


def engines_unavailable(pr: dict) -> dict[str, str]:
    """{engine: reason} of the unavailable markers for the head, from the PR's author or a login in
    AGENT_FABRIC_REVIEW_POSTERS, as pr-review-status binds them (arm_policy.engines_unavailable reads the same). A
    posters list that is not a JSON array of strings is none: this line is a report, and none asks more."""
    try:
        posters = json.loads(os.environ.get("AGENT_FABRIC_REVIEW_POSTERS") or "[]")
    except ValueError:
        posters = []
    if not isinstance(posters, list) or not all(isinstance(x, str) for x in posters):
        posters = []
    author = ((pr.get("author") or {}).get("login") or "")
    rows = []
    for r in (pr.get("reviews") or {}).get("nodes") or []:
        login = ((r.get("author") or {}).get("login") or "")
        u = unavailable_of(r)
        if u and login and (login == author or login in posters):
            rows.append({**u, "commit_sha8": str((r.get("commit") or {}).get("oid") or "")[:8]})
    return arm_policy.engines_unavailable(rows, str(pr.get("headRefOid") or ""))


def additional_engines(repo: str, budget: Budget, cache: dict) -> list[str]:
    """The engines the repository's policy asks beyond the required ones; none when the policy is unread, which
    requires every engine (required_engines). Read with it, once per repository."""
    required_engines(repo, budget, cache)
    return cache[repo][2]


def required_engines(repo: str, budget: Budget, cache: dict) -> tuple[list[str], str]:
    """(the engines the repository's arming policy requires of every pull request, why it is unread or ""), read once
    per repository. One that cannot be read requires every engine and says why: never the default, which could ask
    fewer and say "head reviewed" early."""
    if repo not in cache:
        try:
            policy = arm_policy.load(repo, api=lambda path, **kw: gh.api(path, timeout=budget.left(), **kw))
            cache[repo] = (arm_policy.required_engines(policy, False), "", arm_policy.additional_engines(policy, False))
        except (arm_policy.PolicyError, arm_policy.PolicyUnavailable, Unreadable) as e:
            cache[repo] = (list(arm_policy.ENGINES), str(e), [])
    return cache[repo][:2]


class BudgetedFolds(commit_class.Folds):
    """Folds whose every gh call is bounded by what is left of the call's
    time, and which remembers the folds it could not read: the gate counts
    such a commit as work and says so on stderr, which a caller of
    count_lines never sees, so the line says it."""

    def __init__(self, repo: str, head: str, base: str, budget: Budget):
        def ancestor(oid: str, tip: str) -> bool:
            return commit_class.on_github(repo, timeout=budget.left())(oid, tip)
        super().__init__(repo, head, base=base, ancestor=ancestor)
        self.budget, self.unread_prs = budget, []

    def _look(self, n: str) -> bool:
        self.timeout = self.budget.left()
        return super()._look(n)

    def _unread(self, n: str, why: str) -> bool:
        self.unread_prs.append(n)
        return super()._unread(n, why)


def merge_base_of(pr: dict) -> str:
    """The first parent of a merged pull request's merge commit: the base the
    gate's merged split uses (<merge>^1)."""
    nodes = (((pr.get("mergeCommit") or {}).get("parents") or {}).get("nodes")) or []
    oids = [n.get("oid") if isinstance(n, dict) else None for n in nodes]
    if len(oids) != 2 or not all(isinstance(o, str) and o for o in oids) or oids[1] != pr.get("headRefOid"):
        # A squash or rebase merge has one parent: the gate has no merged split for it either (pr_split.merged_commits).
        raise Unreadable("it is merged, but not by a merge commit of its head, so its range is not known")
    return oids[0]


def describe(label: str, repo: str, pid: str | None, number: int, pr: dict, budget: Budget,
             required: Callable[[], tuple[Sequence[str], str]] = lambda: (arm_policy.ENGINES, ""),
             additional: Callable[[], Sequence[str]] = lambda: ()) -> dict:
    """`required` gives the engines the line marks and why the policy is unread, if it is, and `additional` the
    engines it asks beyond them; both are asked only of an open pull request, so a merged one costs no policy read."""
    rows, bodies = commit_rows(pr, repo, number, budget)
    state = str(pr.get("state") or "").upper()
    base = str(pr.get("baseRefName") or "")
    merged = state == "MERGED" or bool(pr.get("mergedAt"))
    head = str(pr.get("headRefOid") or "")
    # A review fix of a closed, folded pull request reads as a fix when its
    # head is inside this range: asked of GitHub's compare, lazily, once per
    # pull request a commit names (commit_class.Folds). The range's base is
    # the branch for an open pull request and the merge's first parent for a
    # merged one, as the gate's two splits have it.
    folded = BudgetedFolds(repo, head, merge_base_of(pr) if merged else base, budget) if head else None
    c = split_rows(number, repo, rows, folded, lambda sha: bodies.get(sha, ""))
    row = {"ref": label, "repo": repo, "number": number, "ok": True, "work": c["work"], "fix": c["fix"],
           "merge": c["merge"], "netted": c["netted"], "fix_subjects": c["fix_subjects"],
           "netted_subjects": c["netted_subjects"], "state": "merged" if merged else "closed" if state == "CLOSED" else "open"}
    parts = [f"{label} ({c['work']} work, {c['fix']} fix)"]
    if folded is not None and folded.unread_prs:
        row["unread_folds"] = sorted(set(folded.unread_prs), key=int)
        parts.append("(a review's fixes counted as work: " + ", ".join(f"#{n}" for n in row["unread_folds"]) + " could not be read)")
    if row["state"] != "open":
        parts.append(row["state"])
    else:
        armed = "queued" if pr.get("mergeQueueEntry") else "armed" if pr.get("autoMergeRequest") else "unarmed"
        markers, why = legacy_markers(pid)
        if why:
            review = "review unread (" + why + ")"
        else:
            engines, unread = required()
            review = arm_policy.review_summary(engines_on_head(pr, markers), list(engines), str(pr.get("headRefOid") or ""),
                                               unread=unread, additional=list(additional()),
                                               unavailable=engines_unavailable(pr))
            review = review if arm_policy.is_head_reviewed(review) else "review " + review
        row.update(draft=bool(pr.get("isDraft")), armed=armed, checks=checks_word(pr), review=review)
        parts.append(f"{'draft' if row['draft'] else 'open'}, {armed}, checks {row['checks']}, {review}")
    row["line"] = " ".join(parts)
    return row


def count_rows(refs: Sequence[str], timeout: float = DEFAULT_TIMEOUT_S, projects_loader=registry_projects) -> list[dict]:
    """One row per ref, in order. A row that could not be read has ok False
    and a `line` that says why."""
    budget = Budget(timeout)
    policies: dict[str, list[str]] = {}
    rows: list[dict | None] = [None] * len(refs)
    wanted: dict[str, dict[int, list[int]]] = {}
    meta: dict[int, tuple[str, str, str | None, int]] = {}
    cwd_repo: str | None = None
    for i, ref in enumerate(refs):
        try:
            label, repo, pid, number = parse_ref(ref, projects_loader)
            if repo is None:
                if cwd_repo is None:
                    try:
                        cwd_repo = gh.this_repo()
                    except gh.GhError as e:
                        raise Unreadable(f"this checkout's repository cannot be named ({e.reason})") from None
                repo = cwd_repo
            if pid is None:
                try:
                    pid = project_of_repo(repo, projects_loader())
                except Unreadable:
                    pid = None
            meta[i] = (label, repo, pid, number)
            wanted.setdefault(repo, {}).setdefault(number, []).append(i)
        except Unreadable as e:
            rows[i] = {"ref": ref, "ok": False, "line": f"{ref} cannot be read: {e}"}
    for repo, by_number in wanted.items():
        try:
            fetched = fetch_repo(repo, list(by_number), budget)
        except Unreadable as e:
            fetched = {n: e for n in by_number}
        for number, idxs in by_number.items():
            got = fetched.get(number) or Unreadable("no answer")
            for i in idxs:
                label, _, pid, _ = meta[i]
                try:
                    if isinstance(got, Unreadable):
                        raise got
                    rows[i] = describe(label, repo, pid, number, got, budget, lambda: required_engines(repo, budget, policies),
                                       lambda: additional_engines(repo, budget, policies))
                except Unreadable as e:
                    rows[i] = {"ref": label, "repo": repo, "number": number, "ok": False, "line": f"{label} cannot be read: {e}"}
                except gh.GhError as e:
                    rows[i] = {"ref": label, "repo": repo, "number": number, "ok": False, "line": f"{label} cannot be read: {e.reason}"}
                except (KeyError, TypeError, ValueError) as e:
                    rows[i] = {"ref": label, "repo": repo, "number": number, "ok": False,
                               "line": f"{label} cannot be read: GitHub's answer has an unexpected shape ({type(e).__name__})"}
    return [r for r in rows if r is not None]


def count_lines(refs: Sequence[str], timeout: float = DEFAULT_TIMEOUT_S) -> list[str]:
    """The lines for the refs, in order; one per ref, a failed one naming why."""
    return [r["line"] for r in count_rows(refs, timeout)]


def main() -> int:
    argv = sys.argv[1:]
    as_json, timeout, refs = False, DEFAULT_TIMEOUT_S, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            as_json = True
        elif a in ("-h", "--help"):
            print(__doc__.strip("\n"))
            return 0
        elif a == "--timeout":
            try:
                timeout = float(argv[i + 1])
                if timeout <= 0:
                    raise ValueError
            except (IndexError, ValueError):
                print(f"{PROG}: --timeout needs a number of seconds above zero", file=sys.stderr)
                return 2
            i += 1
        elif a.startswith("-") and not a.startswith("-#"):
            print(f"{PROG}: unknown option '{a}' (try --help)", file=sys.stderr)
            return 2
        else:
            refs.append(a)
        i += 1
    if not refs:
        print(f"{PROG}: name at least one pull request: 167, project#167 or owner/repo#167 (try --help)", file=sys.stderr)
        return 2
    rows = count_rows(refs, timeout)
    for r in rows:
        print(json.dumps(r, ensure_ascii=False) if as_json else r["line"])
    return 0 if all(r["ok"] for r in rows) else 2


if __name__ == "__main__":
    sys.exit(main())
