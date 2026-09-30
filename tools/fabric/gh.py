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
  - `transient` says whether a retry could help (a timeout, a 5xx, a rate
    limit), so a caller decides between waiting and giving up — the
    distinction pr-review-status.sh's exit 5 draws ("permanent, don't
    wait").

GitHub refuses one GraphQL query over 500,000 possible nodes; a list of
pull requests with their commits, reviews and checks passes it at about
fifty. Read the list's numbers first and each item alone (results.py).
"""
from __future__ import annotations

import json
import re
import subprocess

TIMEOUT_S = 60
_STATUS = re.compile(r"\(HTTP (\d{3})\)")


class GhError(Exception):
    """A gh call that failed: `what` it was, GitHub's `reason`, the HTTP
    `status` when gh reported one, and whether a retry could help. `stdout`
    is what gh printed before it failed: `gh pr checks` exits 8 while a
    check is pending and 1 while one fails, and prints its table either
    way."""

    def __init__(self, what: str, reason: str, status: int | None = None, transient: bool = False,
                 stdout: str = ""):
        super().__init__(f"{what}: {reason}")
        self.what, self.reason, self.status, self.transient = what, reason, status, transient
        self.stdout = stdout


def run(args: list[str], *, input: str | None = None, timeout: float = TIMEOUT_S, what: str | None = None) -> str:
    """`gh <args>`, its stdout; a failure is a GhError naming `what` (by
    default the first two words of the call)."""
    what = what or "gh " + " ".join(args[:2])
    try:
        # No input is an empty stdin, never the caller's: a gh that reads
        # stdin would otherwise wait on it for the whole bound.
        stdin = {"input": input} if input is not None else {"stdin": subprocess.DEVNULL}
        r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout, **stdin)
    except FileNotFoundError:
        raise GhError(what, "gh is not installed") from None
    except subprocess.TimeoutExpired:
        raise GhError(what, f"no answer within {timeout:g} s", transient=True) from None
    if r.returncode != 0:
        lines = [l for l in r.stderr.strip().splitlines() if l.strip()] or [f"exit {r.returncode}"]
        m = _STATUS.search(r.stderr)
        status = int(m.group(1)) if m else None
        transient = status is not None and (status >= 500 or status == 429) \
            or "rate limit" in r.stderr.lower() or "timeout" in r.stderr.lower()
        raise GhError(what, lines[-1], status, transient, r.stdout)
    return r.stdout


def api(path: str, *, method: str = "GET", body: dict | list | None = None, paginate: bool = False,
        timeout: float = TIMEOUT_S):
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
        # an object whose one list field holds them (search, check runs).
        items = []
        for page in data:
            if isinstance(page, list):
                items += page
            elif isinstance(page, dict):
                lists = [v for v in page.values() if isinstance(v, list)]
                items += lists[0] if len(lists) == 1 else [page]
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
