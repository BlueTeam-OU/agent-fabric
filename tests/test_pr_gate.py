#!/usr/bin/env python3
"""Tests for tools/fabric/github/pr_gate.py's internals; the behaviour is
tests/test_pr_gate_cli.py's, run against the shim (ADR-040
§5 rule 5). What the oracle does not pin: the band's edges, which it
tests only at 6, 9 and 17."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from github import pr_gate  # noqa: E402

CLEAR = {"mergeable": "MERGEABLE", "checks": "green", "unresolved": "0", "queue": "", "armed": "no"}


def commits(work: int) -> dict:
    return {"work": work, "fix": 0, "merge": 0, "netted": 0, "fix_subjects": [], "netted_subjects": []}


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    print("the band's edges")
    v = lambda w: pr_gate.verdict(1, "main", False, commits(w), CLEAR, "head reviewed", [])  # noqa: E731
    check("7 work: ask the owner", v(7).startswith("MERGEABLE — ask the owner (7 work commits < 8)"))
    check("8 work: arm", v(8).startswith("MERGEABLE — arm: post the basis (8 work commits"))
    check("16 work: arm", v(16).startswith("MERGEABLE — arm: post the basis (16 work commits"))
    check("17 work: over 16, still mergeable", v(17).startswith("MERGEABLE — 17 work commits, over 16"))
    check("unknown commits: by hand", pr_gate.verdict(1, "main", False, None, CLEAR, "head reviewed", [])
          .startswith("MERGEABLE — commits unknown"))
    check("a queue position wins over every block",
          pr_gate.verdict(1, "main", True, commits(9), dict(CLEAR, queue="2"), "none", []).startswith("QUEUED"))

    print("AWAITING-SUPPLY")
    body = "AWAITING-SUPPLY: h/db-admin\n - AWAITING-SUPPLY: web-dev-01\naaaaaaa1..bbbbbbb2: web-dev-01 (web-dev)"
    check("the unmet login, by its last segment", pr_gate.awaiting_supply(body) == ["db-admin"])
    check("a range line for a longer login does not meet a shorter one",
          pr_gate.awaiting_supply("AWAITING-SUPPLY: web\naaaaaaa1..bbbbbbb2: web-dev") == ["web"])
    check("a login with a regex character is matched literally, never a crash",
          pr_gate.awaiting_supply("AWAITING-SUPPLY: a+b\naaaaaaa1..bbbbbbb2: aab") == ["a+b"])
    check("no body, nothing awaited", pr_gate.awaiting_supply("") == [])

    print("owner and jq's semantics")
    check("<host>/<login>/… names its session", pr_gate.owner_of("h/l/feat/x") == "h/l")
    check("two segments are their first", pr_gate.owner_of("h/l") == "h")
    check("jq's // skips null and false", pr_gate.alt(None, False, "", "x") == "")
    check("a null reads null in interpolation", pr_gate.jq_str(None) == "null")
    print("review threads past the first 100 (review of #71)")
    from github import pr_review_status as prs
    import gh
    real = gh.graphql

    def node(resolved):
        return {"isResolved": resolved, "isOutdated": False, "path": "a"}

    def paged(pages):
        def fake(query, **kw):
            i = 0 if kw.get("after") is None else int(kw["after"])
            last = i == len(pages) - 1
            return {"repository": {"pullRequest": {"reviewThreads": {
                "nodes": pages[i], "pageInfo": {"hasNextPage": not last, "endCursor": None if last else str(i + 1)}}}}}
        return fake
    try:
        gh.graphql = paged([[node(True)] * 100, [node(False)] * 3])
        check("two pages read whole", len(prs.review_threads("o", "r", 1)) == 103)
        gh.graphql = paged([[node(True)]] * (prs.THREAD_PAGES + 1))
        try:
            prs.review_threads("o", "r", 1)
            check("past the page cap: raised", False)
        except ValueError:
            check("past the page cap: raised, never a short count", True)

        first = {"repository": {"pullRequest": {
            "mergeStateStatus": "CLEAN", "mergeable": "MERGEABLE", "mergeQueueEntry": None, "autoMergeRequest": None,
            "statusCheckRollup": {"contexts": {"nodes": [{"name": "a", "status": "COMPLETED", "conclusion": "SUCCESS"}]}},
            "reviewThreads": {"nodes": [node(True)] * 100, "pageInfo": {"hasNextPage": True, "endCursor": "1"}}}}}

        def gate(rest):
            def fake(query, **kw):
                if "mergeStateStatus" in query:
                    return first
                if isinstance(rest, Exception):
                    raise rest
                return {"repository": {"pullRequest": {"reviewThreads": {
                    "nodes": rest, "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}
            return fake
        gh.graphql = gate([node(False)])
        check("pr-gate counts an unresolved thread on the second page", pr_gate.gate_state("o/r", 1)["unresolved"] == "1")
        gh.graphql = gate(gh.GhError("gh api graphql", "no answer", transient=True))
        st = pr_gate.gate_state("o/r", 1)
        check("a second page that cannot be read: ?, which blocks", st["unresolved"] == "?"
              and "unresolved thread" in pr_gate.verdict(1, "main", False, None, st, "head reviewed", []))

        print("checks past the first 100")
        ok = {"name": "ok", "status": "COMPLETED", "conclusion": "SUCCESS"}
        red = {"name": "late", "status": "COMPLETED", "conclusion": "FAILURE"}

        def rollup(rest, more=True):
            """GATE_QUERY's answer with 100 green checks and, when `more`, a
            next page; CONTEXTS_QUERY's pages are `rest` (a list of pages,
            or an exception). Like GitHub, it answers pageInfo only to a
            query whose contexts ask for it."""
            def fake(query, **kw):
                asks = re.search(r"contexts\(first: 100(, after: \$after)?\) \{ pageInfo \{ hasNextPage endCursor \}", query)
                if "mergeStateStatus" in query:
                    if not asks:
                        return {"repository": {"pullRequest": {
                            "mergeStateStatus": "CLEAN", "mergeable": "MERGEABLE", "mergeQueueEntry": None,
                            "autoMergeRequest": None, "reviewThreads": {"nodes": [], "pageInfo": {"hasNextPage": False}},
                            "statusCheckRollup": {"contexts": {"nodes": [ok] * 100}}}}}
                    return {"repository": {"pullRequest": {
                        "mergeStateStatus": "CLEAN", "mergeable": "MERGEABLE", "mergeQueueEntry": None,
                        "autoMergeRequest": None, "reviewThreads": {"nodes": [], "pageInfo": {"hasNextPage": False}},
                        "statusCheckRollup": {"contexts": {"nodes": [ok] * 100,
                                                           "pageInfo": {"hasNextPage": more, "endCursor": "0" if more else None}}}}}}
                assert asks and asks.group(1) and kw.get("after") is not None, (query, kw)
                if isinstance(rest, Exception):
                    raise rest
                i = int(kw["after"])
                last = i == len(rest) - 1
                return {"repository": {"pullRequest": {"statusCheckRollup": {"contexts": {
                    "nodes": rest[i], "pageInfo": {"hasNextPage": not last, "endCursor": None if last else str(i + 1)}}}}}}
            return fake
        gh.graphql = rollup([], more=False)
        check("one page of green checks: green", pr_gate.gate_state("o/r", 1)["checks"] == "green")
        gh.graphql = rollup([[ok] * 100, [red]])
        check("a red check on the third page: red, named", pr_gate.gate_state("o/r", 1)["checks"] == "red:late")
        gh.graphql = rollup([[ok, {"name": "slow", "status": "IN_PROGRESS", "conclusion": None}]])
        check("a running check on the second page: pending", pr_gate.gate_state("o/r", 1)["checks"] == "pending:1")
        for label, rest in (("a page that cannot be read", gh.GhError("gh api graphql", "HTTP 502", 502, True)),
                            ("a page with no cursor to the next", "no-cursor"),
                            ("past the page cap", [[ok]] * (pr_gate.CONTEXT_PAGES + 1)),
                            ("a malformed page", [None])):
            if rest == "no-cursor":
                def rest_fake(query, **kw):
                    if "mergeStateStatus" in query:
                        return rollup([])(query, **kw)
                    return {"repository": {"pullRequest": {"statusCheckRollup": {"contexts": {
                        "nodes": [ok], "pageInfo": {"hasNextPage": True, "endCursor": None}}}}}}
                gh.graphql = rest_fake
            else:
                gh.graphql = rollup(rest)
            st = pr_gate.gate_state("o/r", 1)
            check(f"{label}: checks ?, which blocks", st["checks"] == "?"
                  and "the checks could not all be read" in pr_gate.verdict(1, "main", False, None, st, "head reviewed", []))
        st = dict(st, checks="green")
        check("...and green does not", "BLOCKED" not in pr_gate.verdict(1, "main", False, None, st, "head reviewed", []))
    finally:
        gh.graphql = real


    # The Kind: declaration reaches the classifier through split_range's
    # own git log, in a real range: each row's subject would read the
    # other way without it, and a revert pair declared work still nets.
    print("split_range reads the Kind: trailer")
    with tempfile.TemporaryDirectory() as repo:
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t",
                   GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")

        def git(*args: str) -> str:
            return subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True,
                                  text=True).stdout.strip()

        def commit(n: int, *msg: str) -> str:
            open(os.path.join(repo, f"f{n}"), "w").write(str(n))
            git("add", "-A")
            git("commit", "-q", *[a for m in msg for a in ("-m", m)])
            return git("rev-parse", "HEAD")

        git("init", "-q", "-b", "main")
        base = commit(0, "base")
        commit(1, "review fix (#7 F1): the probe exits 3", "Kind: work")
        commit(2, "the guard reads the count from the file", "Kind: review-fix\nAnswers: F2")
        commit(3, "an undeclared plain commit")
        commit(4, "review F4: undeclared, read as before")
        # Two Kind: trailers: git joins them with US in split_range's
        # format, and the last one wins.
        commit(6, "review fix (#7 F2): declared twice", "Kind: review-fix\nKind: work")
        undo = commit(5, "a change later undone", "Kind: work")
        git("revert", "--no-edit", undo)
        here = os.getcwd()
        os.chdir(repo)
        try:
            c = pr_gate.split_range(7, "", f"{base}..HEAD")
        finally:
            os.chdir(here)
        check(f"work 3, fix 2, netted 2 (got work {c['work']}, fix {c['fix']}, netted {c['netted']})",
              (c["work"], c["fix"], c["netted"]) == (3, 2, 2))
        check("the fixes are the declared one and the undeclared review subject",
              sorted(c["fix_subjects"]) == ["review F4: undeclared, read as before",
                                            "the guard reads the count from the file"])

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
