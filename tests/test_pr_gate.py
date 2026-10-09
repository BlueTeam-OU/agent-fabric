#!/usr/bin/env python3
"""Tests for tools/fabric/github/pr_gate.py's internals; the behaviour is
tests/test_pr_gate_cli.py's, run against the shim (ADR-040
§5 rule 5). What the oracle does not pin: the band's edges, which it
tests only at 6, 9 and 17."""
from __future__ import annotations

import os
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

    # A fold reaches the classifier through split_range's <head>: #10 was
    # merged unrebased into this branch and closed, so its review fix is
    # #11's fix; without the head the range reads as before. gh is a fake
    # on PATH that knows only #10.
    print("split_range reads a folded PR's review fixes as fixes")
    with tempfile.TemporaryDirectory() as tmp:
        repo = os.path.join(tmp, "repo")
        os.makedirs(os.path.join(tmp, "bin"))
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "GH_"))}
        env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t",
                   GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t",
                   PATH=f"{tmp}/bin:{env.get('PATH', '')}")

        def git(*args: str) -> str:
            return subprocess.run(["git", "-C", repo, *args], env=env, check=True, capture_output=True,
                                  text=True).stdout.strip()

        os.makedirs(repo)
        git("init", "-q", "-b", "main")
        git("commit", "-q", "--allow-empty", "-m", "base")
        base = git("rev-parse", "HEAD")
        git("checkout", "-q", "-b", "pr-10")
        git("commit", "-q", "--allow-empty", "-m", "#10's work", "-m", "Kind: work")
        git("commit", "-q", "--allow-empty", "-m", "review fix (#10 F1): the probe exits 3",
            "-m", "Kind: review-fix\nAnswers: #10 F1")
        folded = git("rev-parse", "HEAD")
        git("checkout", "-q", "-b", "pr-11", "main")
        git("commit", "-q", "--allow-empty", "-m", "#11's work", "-m", "Kind: work")
        git("merge", "-q", "--no-ff", "--no-edit", "pr-10")
        head = git("rev-parse", "HEAD")
        fake = os.path.join(tmp, "bin", "gh")
        open(fake, "w").write("#!/bin/sh\n[ \"$3\" = 10 ] && exec echo '{\"state\": \"CLOSED\", \"mergedAt\": null, "
                              f"\"headRefOid\": \"{folded}\"}}'\nexit 1\n")
        os.chmod(fake, 0o755)
        saved, here = dict(os.environ), os.getcwd()
        os.environ.clear()
        os.environ.update(env)
        os.chdir(repo)
        # #11 merged carrying the fold; #12 answers #10 again on top of it.
        # #10's head is now inside #12's base, so the answer is #12's work
        # (ADR-019 rule 3: "its head inside this range").
        git("checkout", "-q", "main")
        git("merge", "-q", "--no-ff", "--no-edit", "pr-11")
        main2 = git("rev-parse", "HEAD")
        git("checkout", "-q", "-b", "pr-12")
        git("commit", "-q", "--allow-empty", "-m", "follow-up (#10 F2): the probe names its host",
            "-m", "Kind: review-fix\nAnswers: #10 F2")
        head12 = git("rev-parse", "HEAD")
        try:
            c = pr_gate.split_range(11, "o/r", f"{base}..{head}", head)
            before = pr_gate.split_range(11, "o/r", f"{base}..{head}")
            git("update-ref", "refs/remotes/origin/main", base)
            counted = pr_gate.count_commits(11, "o/r", "main", head)
            later = pr_gate.split_range(12, "o/r", f"{main2}..{head12}", head12, main2)
            unbased = pr_gate.split_range(12, "o/r", f"{main2}..{head12}", head12)
            git("update-ref", "refs/remotes/origin/main", main2)
            counted12 = pr_gate.count_commits(12, "o/r", "main", head12)
        finally:
            os.chdir(here)
            os.environ.clear()
            os.environ.update(saved)
        check(f"with the head: work 2, fix 1, merge 1 (got {c['work']}, {c['fix']}, {c['merge']})",
              (c["work"], c["fix"], c["merge"]) == (2, 1, 1))
        check(f"without it: work 3, fix 0 — the follow-up reading (got {before['work']}, {before['fix']})",
              (before["work"], before["fix"]) == (3, 0))
        # count_commits must hand split_range the head and the base, or fold
        # reading is silently off and every split above still passes.
        check(f"count_commits reads the fold: work 2, fix 1 (got {counted and (counted['work'], counted['fix'])})",
              counted is not None and (counted["work"], counted["fix"]) == (2, 1))
        check(f"a fold already in the base: #12's answer is work 1, fix 0 (got {later['work']}, {later['fix']})",
              (later["work"], later["fix"]) == (1, 0))
        check(f"…the reading the base corrects: fix 1 without it (got {unbased['work']}, {unbased['fix']})",
              (unbased["work"], unbased["fix"]) == (0, 1))
        check(f"count_commits passes the base: work 1, fix 0 (got {counted12 and (counted12['work'], counted12['fix'])})",
              counted12 is not None and (counted12["work"], counted12["fix"]) == (1, 0))

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
