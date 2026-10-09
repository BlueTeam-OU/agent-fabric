"""tools/fabric/gh.py — every call the fabric's Python makes to GitHub, through
the `gh` CLI (ADR-040 §5 rule 6).

    import gh
    gh.api("repos/o/r/pulls/7")                          # one object
    gh.api("repos/o/r/pulls/7/commits", paginate=True)   # every page, one list
    gh.api("repos/o/r/pulls/7/reviews", method="POST", body={...})
    gh.graphql("query($n:Int!){...}", n=7)
    gh.pr_view(7, ["number", "mergedAt"], repo="o/r")

WHY ONE MODULE. The bash toolkit built its bodies by interpolation and
parsed with jq; each tool chose its own timeout, or none, and said its
errors its own way. Here:
  - a request body is JSON on stdin (`--input -`), never an argument —
    pr-reply.sh's invariant: a body is data, so no quoting of it can go
    wrong and nothing of it reaches argv or a process list;
  - JSON is parsed in Python, never with jq;
  - every call is bounded, and its error names the call and GitHub's
    reason (the HTTP status when gh reports one);
  - `transient` says the outcome is not known to be a refusal: a timeout,
    a 5xx, a rate limit, or an answer gh accepted and that could not be
    read. For a read that means a retry could help — the distinction
    pr-review-status.sh's exit 5 draws ("permanent, don't wait"). For a
    WRITE it means the write may have landed: never retry one on it (a
    review or a reply cannot be unsent); say so and let a person look.

GitHub refuses one GraphQL query over 500,000 possible nodes; a list of
pull requests with their commits, reviews and checks passes it at about
fifty. Read the list's numbers first and each item alone (results.py).
"""
from __future__ import annotations

import json
import os
import re
import subprocess

TIMEOUT_S = 60
_STATUS = re.compile(r"\(HTTP (\d{3})\)")
# A request that never reached GitHub, or lost its answer on the way,
# carries no HTTP status: a retry can help a read, and a write may or may
# not have landed. Measured on gh 2.87.3 through dead proxies
# (2026-10-01): "connect: connection refused", "error connecting to
# <host>" (a name that does not resolve), "i/o timeout"; the rest are the
# Go network layer's own texts for the same failures (review of #71).
NETWORK_FAILURES = ("timeout", "connection refused", "connection reset", "error connecting to", "no such host",
                    "unexpected eof", "tls handshake", "network is unreachable", "broken pipe")


class GhError(Exception):
    """A gh call that failed: `what` it was, GitHub's `reason`, the HTTP
    `status` when gh reported one, and whether the outcome is unknown
    (`transient`: a read may be retried, a write may have landed). `stdout`
    is what gh printed before it failed: `gh pr checks` exits 8 while a
    check is pending and 1 while one fails, and prints its table either
    way. `stderr` and `code` are gh's whole stderr and exit status, when gh
    ran and exited."""

    def __init__(self, what: str, reason: str, status: int | None = None, transient: bool = False,
                 stdout: str = "", stderr: str = "", code: int | None = None):
        super().__init__(f"{what}: {reason}")
        self.what, self.reason, self.status, self.transient = what, reason, status, transient
        self.stdout, self.stderr, self.code = stdout, stderr, code


# `gh pr checks` with nothing to list prints no table and no JSON — not
# even `[]` under --json — but this one line on stderr, and exits 1, the
# code it also uses for a failing check. Measured on gh 2.87.3
# (2026-10-09): "no required checks reported on the '<head>' branch" when
# checks exist but none is required, "no checks reported on the '<head>'
# branch" when the head has none at all, --required or not. Read as an
# unreadable lookup, it made wait-merged give up on a PR that merged
# minutes later (#128). The WHOLE answer is matched — exit 1, stdout
# empty, that line and nothing else on stderr — because a false match
# turns an unknown into "none": a failing check's JSON dropped, an HTTP
# error read as an empty list (review of #129). So GH_DEBUG's extra lines
# read as unreadable, the loud direction.
_NO_CHECKS = re.compile(r"no (?:required )?checks reported on the '.*' branch")


def no_checks_reported(e: GhError) -> bool:
    """Whether a failed `gh pr checks` was gh's answer "there are none":
    zero checks, a known answer, never an unknown one."""
    return e.code == 1 and not e.stdout.strip() and bool(_NO_CHECKS.fullmatch(e.stderr.strip()))


# origin's URL on github.com: scp-like or with a scheme, `.git` optional.
_ORIGIN = re.compile(r"^(?:[^@/:\s]+@github\.com:|(?:https|ssh|git)://(?:[^@/\s]+@)?github\.com/)"
                     r"(?P<repo>[A-Za-z0-9._-]+/[A-Za-z0-9._-]+?)(?:\.git)?/?$")
_REPO = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
# What gh takes after --repo/-R: [HOST/]OWNER/REPO (a GitHub Enterprise
# host included); naming the host names the repository too (#111 review).
# gh reads the first of three parts as the host whatever it is, so a
# dotless one (an internal name, localhost:8080) names it as well (#114).
_SELECTOR = re.compile(r"^([A-Za-z0-9.-]+(:[0-9]+)?/)?[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
_ITEM_URL = re.compile(r"^https://github\.com/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+/(pull|issues)/\d+/?$")


def this_repo(cwd: str | None = None) -> str:
    """The repository this working copy's pull requests are in: GH_REPO
    when set, else origin's on github.com. Never gh's default repository:
    in a fork clone with an `upstream` remote gh may default to upstream,
    and a review meant for the fork was posted on the upstream project's
    public pull request of the same number (a managed fork, 2026-10-07)."""
    env = os.environ.get("GH_REPO", "").strip()
    if env:
        if not _REPO.match(env):
            raise GhError("this repository", f"GH_REPO is not <owner>/<repo>: {env!r}")
        return env
    try:
        r = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, timeout=30,
                           cwd=cwd, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GhError("this repository", f"git remote get-url origin: {e.__class__.__name__}") from None
    m = _ORIGIN.match(r.stdout.strip()) if r.returncode == 0 else None
    if not m:
        # The URL itself is never echoed: it can carry a credential.
        raise GhError("this repository", "origin is not a github.com repository here (set GH_REPO=<owner>/<repo> "
                      "to name one); gh's default repository is never used")
    return m.group("repo")


# gh's subcommands that act on one repository, guessed from the git
# remotes when none is named.
_REPO_SCOPED = {"pr", "repo", "issue", "run", "workflow", "release", "secret", "variable", "label", "cache",
                "ruleset", "browse", "attestation"}


def _a_value(args: list[str], i: int) -> bool:
    """Whether args[i] may be the value of the option before it, as gh's
    flag parser takes the next word for any flag that is not a boolean
    and has no `=`: `--body -Ro/r` is a body, not a selector (#114). gh's
    booleans are not listed here, so a selector right after one (`--web
    -R o/r`) reads as unnamed too: refused only where GH_REPO cannot be
    pinned, and named by putting it first or by GH_REPO."""
    if i == 0:
        return False
    before = args[i - 1]
    return before.startswith("-") and before not in ("-", "--") and "=" not in before \
        and not (before.startswith("-R") and len(before) > 2)


def _scoped(args: list[str]) -> bool:
    """Whether gh would pick a repository for this call itself: a scoped
    subcommand without --repo/-R, or an api path naming {owner}/{repo}."""
    # Only a real selector names the repository: --repo/-R with a value, a
    # joined -R<owner>/<repo>, `gh repo <verb> <owner>/<repo>`, or a pull
    # request's or issue's URL as the subcommand's argument. A URL or a
    # "-R…" inside a flag's value (a body, a title) names nothing (review
    # of the carried-109 branch, F1).
    for i, a in enumerate(args):
        if _a_value(args, i):
            continue
        value = (args[i + 1] if i + 1 < len(args) else "") if a in ("--repo", "-R") \
            else a[len("--repo="):] if a.startswith("--repo=") else a[2:] if a.startswith("-R") else None
        if value is not None and _SELECTOR.match(value):
            return False
    if args[:1] == ["api"]:
        return any("{owner}" in a or "{repo}" in a for a in args[1:])
    if args[:1] == ["repo"] and len(args) > 2 and not _a_value(args, 2) and _SELECTOR.match(args[2]):
        return False
    if args[:1] in (["pr"], ["issue"]) and len(args) > 2 and _ITEM_URL.match(args[2]):
        return False
    return bool(args) and args[0] in _REPO_SCOPED


def _env(args: list[str], what: str) -> dict[str, str] | None:
    """The environment for gh: GH_REPO pinned to this_repo(), so a command
    that takes no --repo (gh pr view N, gh pr merge N, gh api's {owner}/
    {repo}) targets this working copy's repository, never gh's default.
    When nothing names one, a call gh would aim by guessing is refused: gh
    ranks an `upstream` remote above origin, and outside a GitHub origin
    that guess is the upstream project (review of the merges branch)."""
    if os.environ.get("GH_REPO"):
        return None
    try:
        return {**os.environ, "GH_REPO": this_repo()}
    except GhError as e:
        if _scoped(args):
            raise GhError(what, e.reason) from None
        return None


def run(args: list[str], *, input: str | None = None, timeout: float = TIMEOUT_S, what: str | None = None) -> str:
    """`gh <args>`, its stdout; a failure is a GhError naming `what` (by
    default the first two words of the call)."""
    what = what or "gh " + " ".join(args[:2])
    try:
        # No input is an empty stdin, never the caller's: a gh that reads
        # stdin would otherwise wait on it for the whole bound.
        stdin = {"input": input} if input is not None else {"stdin": subprocess.DEVNULL}
        env = _env(args, what)
        r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout, env=env, **stdin)
    except FileNotFoundError:
        raise GhError(what, "gh is not installed") from None
    except subprocess.TimeoutExpired:
        raise GhError(what, f"no answer within {timeout:g} s", transient=True) from None
    if r.returncode != 0:
        lines = [l for l in r.stderr.strip().splitlines() if l.strip()] or [f"exit {r.returncode}"]
        m = _STATUS.search(r.stderr)
        status = int(m.group(1)) if m else None
        low = r.stderr.lower()
        transient = status is not None and (status >= 500 or status == 429) \
            or "rate limit" in low or any(t in low for t in NETWORK_FAILURES)
        raise GhError(what, lines[-1], status, transient, r.stdout, r.stderr, r.returncode)
    return r.stdout


def api(path: str, *, method: str = "GET", body: dict | list | None = None, paginate: bool = False,
        timeout: float = TIMEOUT_S, items_key: str | None = None):
    """A REST call, its JSON. With paginate, every page's items as one
    list (`--paginate --slurp`, which gh has had since 2.48)."""
    args = ["api", path, "--method", method]
    if paginate:
        args += ["--paginate", "--slurp"]
    if body is not None:
        args += ["--input", "-"]
    out = run(args, input=json.dumps(body) if body is not None else None, timeout=timeout,
              what=f"gh api {method} {path.split('?')[0]}")
    try:
        data = json.loads(out) if out.strip() else None
    except ValueError:
        # gh exited 0: the request was accepted and its answer is unread, so
        # the outcome is unknown — transient, like a timeout: a read may be
        # retried, and a write may have landed (re-review of #71).
        raise GhError(f"gh api {method} {path.split('?')[0]}", "the answer is not JSON", transient=True) from None
    if paginate and isinstance(data, list):
        # --slurp wraps the pages in a list; a page is a list of items, or
        # an object holding them under the field the caller names (search,
        # check suites). Guessed, a page with no list field or several was
        # appended whole, and the caller got items of two shapes (review of
        # #70): an object page without its named field is a failed read.
        items = []
        for page in data:
            if isinstance(page, list):
                items += page
            elif isinstance(page, dict) and items_key and isinstance(page.get(items_key), list):
                items += page[items_key]
            else:
                what = f"gh api {method} {path.split('?')[0]}"
                raise GhError(what, f"a page is not a list{f' and has no {items_key!r} list' if items_key else ''}"
                              f" (pass items_key= for an endpoint whose pages are objects)")
        return items
    return data


def graphql(query: str, *, timeout: float = TIMEOUT_S, **variables) -> dict:
    """A GraphQL query, its `data`; the query and its variables on stdin.
    GraphQL answers errors with HTTP 200: they are raised here too."""
    out = run(["api", "graphql", "--input", "-"], input=json.dumps({"query": query, "variables": variables}),
              timeout=timeout, what="gh api graphql")
    # An answer that is not a JSON object is a failed call, never a
    # traceback past a caller that catches GhError (review of #71).
    try:
        doc = json.loads(out)
    except ValueError:
        raise GhError("gh api graphql", "the answer is not JSON", transient=True) from None
    if not isinstance(doc, dict):
        raise GhError("gh api graphql", "the answer is not a JSON object", transient=True)
    if doc.get("errors"):
        # A rate limit can come back as an error answered with 200: waiting
        # helps it as it helps a 429 (review of #70).
        why = "; ".join(e.get("message", "?") for e in doc["errors"])[:300]
        limited = any(e.get("type") == "RATE_LIMITED" or "rate limit" in str(e.get("message", "")).lower() for e in doc["errors"])
        raise GhError("gh api graphql", why, transient=limited)
    return doc.get("data") or {}


def pr_view(number: int, fields: list[str], *, repo: str | None = None, timeout: float = TIMEOUT_S) -> dict:
    args = ["pr", "view", str(number), "--json", ",".join(fields)]
    if repo:
        args += ["--repo", repo]
    return json.loads(run(args, timeout=timeout, what=f"gh pr view {number}"))


def pr_list(fields: list[str], *, repo: str | None = None, state: str = "open", search: str | None = None,
            limit: int = 1000, timeout: float = TIMEOUT_S) -> list[dict]:
    args = ["pr", "list", "--state", state, "--limit", str(limit), "--json", ",".join(fields)]
    if repo:
        args += ["--repo", repo]
    if search:
        args += ["--search", search]
    return json.loads(run(args, timeout=timeout, what="gh pr list"))
