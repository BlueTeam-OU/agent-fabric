"""tools/fabric/github/pr_sessions_threads.py — the THR column of pr-sessions:
one GraphQL read of the unresolved review threads of the listed PRs, the
count per PR, and whether the last word in any of them is not the PR
author's. Split out of pr_sessions.py, unchanged; the column's meaning is
that module's header."""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402

THREADS_QUERY = """query($owner: String!, $name: String!@@DECL@@) {
  repository(owner: $owner, name: $name) {@@ALIASES@@
  }
}"""


THREAD_ALIAS = """
    p{n}: pullRequest(number: $n{n}) {{ number author {{ login }}
      reviewThreads(first: 100) {{ pageInfo {{ hasNextPage }} nodes {{ isResolved
        comments(last: 1) {{ nodes {{ author {{ login }} }} }} }} }} }}"""


def thread_counts(data: dict) -> dict | None:
    """{number: {unresolved, awaiting}} from the GraphQL `data`, or None when
    its shape is not one (a failed lookup must read as UNKNOWN, never as
    zero: "0 unresolved" is exactly the reassuring answer you would act on,
    and it would be a guess).

    The PR author is bound BEFORE descending into the threads. Reading
    `.author.login` inside the thread pipeline compared each last-commenter
    against a field the thread node does not have — i.e. against null — so
    every unresolved thread counted as awaiting and every row wore a "!".
    The bang then said nothing the count had not already said.

    A TRUNCATED PAGE IS UNKNOWN, NOT ZERO. Past 100 threads only the first
    page arrives, so a pr whose early threads are all resolved and whose
    open one sits later would report "-" and be dropped from /unresolved —
    hiding exactly the outstanding work this command promises to surface.
    Same rule as a failed lookup."""
    repo = (data or {}).get("repository")
    if not isinstance(repo, dict):
        return None
    counts = {}
    for pr in repo.values():
        if not isinstance(pr, dict):
            return None
        author = (pr.get("author") or {}).get("login") or ""
        threads = pr.get("reviewThreads") or {}
        value = {"unresolved": None, "awaiting": None}
        if not (threads.get("pageInfo") or {}).get("hasNextPage"):
            nodes = threads.get("nodes")
            if not isinstance(nodes, list):
                return None
            open_ = [t for t in nodes if t.get("isResolved") is False]
            value = {"unresolved": len(open_), "awaiting": sum(1 for t in open_ if _last_word(t) != author)}
        counts[str(pr.get("number"))] = value
    return counts


def _last_word(thread: dict) -> str:
    comments = (thread.get("comments") or {}).get("nodes") or []
    return (((comments[0] if comments else None) or {}).get("author") or {}).get("login") or ""


def lookup_threads(numbers: list[int]) -> dict | None:
    """One batched call for the rows about to be PRINTED, in a single aliased
    GraphQL query rather than one request per PR: ~0.7s for the whole page
    instead of N round trips. "Unresolved" is the right count because it is
    what is still owed — not what blocks a merge; nothing does since
    2026-08-06. The "!" asks a second question the raw count cannot: is the
    last comment in the thread the PR author's? If it is not, somebody is
    waiting on YOU. None is unknown — a failed call, and no repo context,
    which means no thread data, read alike."""
    try:
        owner_repo = gh.this_repo()
    except gh.GhError:
        owner_repo = ""
    if not owner_repo:
        return None
    owner, _, name = owner_repo.partition("/")
    # The numbers are variables too, never text in the query: only the alias
    # names (p<N>) are spelled into it, and those are ints from gh.
    variables = {"owner": owner, "name": name, **{f"n{n}": n for n in numbers}}
    query = THREADS_QUERY.replace("@@DECL@@", "".join(f", $n{n}: Int!" for n in numbers)) \
        .replace("@@ALIASES@@", "".join(THREAD_ALIAS.format(n=n) for n in numbers))
    try:
        return thread_counts(gh.graphql(query, **variables))
    except (gh.GhError, ValueError):
        return None


def thr_column(row: dict, threads: dict | None, want: bool) -> str:
    """The THR column can honestly print "?" for an unknown count."""
    if not want:
        return ""
    if threads is None:
        return "?"
    t = threads.get(str(row["number"]))
    if t is None or t["unresolved"] is None:
        return "?"
    if t["unresolved"] == 0:
        return "-"
    return f"{t['unresolved']}{'!' if t['awaiting'] > 0 else ''}"


def keeps_unresolved(row: dict, threads: dict) -> bool:
    """The /unresolved FILTER cannot print "?": it must decide keep-or-drop
    per row, and the only safe default — treat unknown as zero — deletes
    exactly the rows the caller asked to see, then reports "no PRs with
    unresolved review threads" as though the question had been answered.
    That is the unknown-is-not-zero safeguard undone one stage later, so an
    unknown row is KEPT (and a wholly unknown lookup is refused by the
    caller)."""
    t = threads.get(str(row["number"]))
    return t is None or t["unresolved"] is None or t["unresolved"] > 0
