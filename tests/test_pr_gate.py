#!/usr/bin/env python3
"""Tests for tools/fabric/github/pr_gate.py, in-process: the verdict and
each reason it blocks, the band's edges, the checks and threads read from
GitHub's answer, the review reader's text, and the work / fix / merge split
with a revert netted, over a small throwaway repository. The outcomes of
the command (exit status, stream, output mode, a real clone, gh failing)
are tests/test_pr_gate_cli.py's, one smoke case each; the verdict logic is
asserted here, where it costs no subprocess."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from github import arm_policy, pr_gate  # noqa: E402
from git_env import scrub_process_env  # noqa: E402 — tests/, the script's own directory

scrub_process_env()

# Both of the fleet's engines on the head, as review_of_head says it.
REVIEWED = arm_policy.review_summary({"claude", "codex"}, ["claude", "codex"], "abcdef01")
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
    v = lambda w: pr_gate.verdict(1, "main", False, commits(w), CLEAR, REVIEWED, [])  # noqa: E731
    check("7 work: ask the owner", v(7).startswith("MERGEABLE — ask the owner (7 work commits < 8)"))
    check("8 work: arm", v(8).startswith("MERGEABLE — arm: post the basis (8 work commits"))
    check("16 work: arm", v(16).startswith("MERGEABLE — arm: post the basis (16 work commits"))
    check("17 work: over 16, still mergeable", v(17).startswith("MERGEABLE — 17 work commits, over 16"))
    check("unknown commits: by hand", pr_gate.verdict(1, "main", False, None, CLEAR, REVIEWED, [])
          .startswith("MERGEABLE — commits unknown"))
    check("a queue position wins over every block",
          pr_gate.verdict(1, "main", True, commits(9), dict(CLEAR, queue="2"), "none", []).startswith("QUEUED"))

    print("the verdict's reasons")

    def why(review=REVIEWED, awaiting=(), draft=False, **st) -> str:
        return pr_gate.verdict(1, "main", draft, commits(6), dict(CLEAR, **st), review, list(awaiting))
    check("clear, reviewed, 6 work: ask the owner",
          why().startswith("MERGEABLE — ask the owner (6 work commits < 8), then arm"))
    check("one engine missing: BLOCKED, the per-engine line said",
          why(review="claude ✓ codex ✗ (head abcdef01)")
          == "BLOCKED: not every required engine has reviewed the head (claude ✓ codex ✗ (head abcdef01))")
    check("a reader that could not answer: BLOCKED, ?",
          why(review="?") == "BLOCKED: not every required engine has reviewed the head (?)")
    check("a failed check: named, BLOCKED", why(checks="red:backend / shard") == "BLOCKED: red checks: backend / shard")
    check("a running check: pending, BLOCKED", why(checks="pending:1") == "BLOCKED: 1 check(s) pending")
    check("no check reported at all (seconds after a push): not green",
          why(checks="none-yet").startswith("BLOCKED: no check has reported yet"))
    check("unresolved threads block", why(unresolved="2") == "BLOCKED: 2 unresolved thread(s)")
    check("a conflict blocks", why(mergeable="CONFLICTING") == "BLOCKED: conflicts with main")
    check("a draft is never told to arm", why(draft=True) == "BLOCKED: a draft — mark it ready first")
    check("an awaited supply blocks, by the login",
          why(awaiting=["db-admin"]).startswith("BLOCKED: awaiting supply from db-admin (AWAITING-SUPPLY"))
    check("every reason is said, in order",
          why(checks="red:x", unresolved="2") == "BLOCKED: red checks: x; 2 unresolved thread(s)")
    check("armed and clear", why(armed="yes").startswith("ARMED and clear"))
    check("armed but red: says what holds it", why(armed="yes", checks="red:x").startswith("ARMED but held: red checks"))
    check("queued: position, nothing to do", why(queue="3") == "QUEUED (position 3) — nothing to do")
    nodes_green = [{"name": "ci / a", "status": "COMPLETED", "conclusion": "SUCCESS"}]
    nodes_red = nodes_green + [{"name": "backend / shard", "status": "COMPLETED", "conclusion": "FAILURE"}]
    nodes_pending = [{"name": "ci / a", "status": "IN_PROGRESS", "conclusion": None}]
    check("checks_of: green, red (named), pending (counted), none yet",
          [pr_gate.checks_of(n) for n in (nodes_green, nodes_red, nodes_pending, [])]
          == ["green", "red:backend / shard", "pending:1", "none-yet"])
    check("checks_of: a status context reads by its state",
          pr_gate.checks_of([{"context": "legacy", "state": "FAILURE"}]) == "red:legacy"
          and pr_gate.checks_of([{"context": "legacy", "state": "PENDING"}]) == "pending:1")

    print("the review reader's blind rows, per engine (REQUEST 01a13693)")
    with tempfile.TemporaryDirectory() as tmp:
        script = os.path.join(tmp, "reader")
        head = "abcdef0123456789"

        def reader(*rows: tuple[str, str | None], code: int = 0, out: str | None = None) -> list[str]:
            """A review-status that answers `-q --json` with these (commit_sha8, engine) blind rows; engine None is a
            row from before the field, the review class's."""
            if out is None:
                out = json.dumps({"blind": {"rows": [{"commit_sha8": sha, **({"engine": e} if e else {})} for sha, e in rows]},
                                  "unresolved_threads": 0})
            with open(script, "w") as fh:
                fh.write(f'#!/bin/sh\n[ "$2 $3" = "-q --json" ] || exit 2\ncat <<\'EOF\'\n{out}\nEOF\nexit {code}\n')
            os.chmod(script, 0o755)
            return [script]
        both, claude_only = ["claude", "codex"], ["claude"]
        on = head[:8]
        cases = [
            ("claude only", [(on, "claude")], both, "claude ✓ codex ✗ (head abcdef01)"),
            ("codex only", [(on, "codex")], both, "claude ✗ codex ✓ (head abcdef01)"),
            ("both", [(on, "claude"), (on, "codex")], both, "head reviewed: claude ✓ codex ✓ (head abcdef01)"),
            ("neither", [], both, "claude ✗ codex ✗ (head abcdef01)"),
            ("claude only", [(on, "claude")], claude_only, "head reviewed: claude ✓ (head abcdef01)"),
            ("codex only", [(on, "codex")], claude_only, "claude ✗ (head abcdef01)"),
            ("both", [(on, "claude"), (on, "codex")], claude_only, "head reviewed: claude ✓ (head abcdef01)"),
            ("neither", [], claude_only, "claude ✗ (head abcdef01)"),
        ]
        for what, rows, required, want in cases:
            got = pr_gate.review_of_head(reader(*rows), 1, head, required)
            check(f"policy {'+'.join(required)}, the head reviewed by {what}: {want} (got {got})", got == want)
            reviewed = arm_policy.is_head_reviewed(got)
            check(f"…and the verdict {'does not block' if reviewed else 'blocks'} on it",
                  ("not every required engine" in pr_gate.verdict(1, "main", False, commits(9), CLEAR, got, [])) is not reviewed)
        check("a review of an older head is no engine's",
              pr_gate.review_of_head(reader(("12345678", "claude"), ("12345678", "codex")), 1, head, both)
              == "claude ✗ codex ✗ (head abcdef01)")
        check("a row with no engine is the review class's (claude)",
              pr_gate.review_of_head(reader((on, None)), 1, head, claude_only) == "head reviewed: claude ✓ (head abcdef01)")
        check("an engine only a boundary adds is shown, not required",
              pr_gate.review_of_head(reader((on, "claude")), 1, head, claude_only, ["codex"])
              == "head reviewed: claude ✓ codex ✗ (boundary only) (head abcdef01)")
        check("the review exit 1 (not reviewed) still answers its rows",
              pr_gate.review_of_head(reader((on, "claude"), code=1), 1, head, claude_only) == "head reviewed: claude ✓ (head abcdef01)")
        check("a reader that exits 2, cannot run, or answers no blind.rows is ?",
              pr_gate.review_of_head(reader((on, "claude"), code=2), 1, head, both) == "?"
              and pr_gate.review_of_head([os.path.join(tmp, "absent")], 1, head, both) == "?"
              and pr_gate.review_of_head(reader(out="  head reviewed?      : yes"), 1, head, both) == "?"
              and pr_gate.review_of_head(reader(out='{"blind": {}}'), 1, head, both) == "?")
        check("the engines a policy requires: its reviews; a boundary's extra shown apart",
              pr_gate.engines_required(dict(arm_policy.default(), reviews=["claude"], boundary_reviews=both)) == (["claude"], ["codex"], "")
              and pr_gate.engines_required(dict(arm_policy.default(), reviews=both, boundary_reviews=both)) == (both, [], "")
              and pr_gate.engines_required(arm_policy.default()) == (["claude"], [], ""))
        # A claude-only default, pinned here so the case does not follow the fleet's file, tells "every engine" from
        # "the default's" (supplier review F2).
        claude_default = arm_policy.validate({"reviews": ["claude"], "boundary_reviews": ["claude"]})
        with mock.patch.object(arm_policy, "default", return_value=claude_default), \
                mock.patch.object(arm_policy, "fleet_policy", return_value=claude_default):
            unread = pr_gate.engines_required("HTTP 500")
        check("an unreadable policy requires every engine, never the default's, and says why",
              unread == (list(arm_policy.ENGINES), [], "HTTP 500"))
        got = pr_gate.review_of_head(reader((on, "claude")), 1, head, *unread)
        check("…on the line: the missing engine is not read as the repository's requirement",
              got == "claude ✓ codex ✗ (head abcdef01; policy unread, every engine required: HTTP 500)")

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
        for label, page in (("a string", "abc"), ("a dict", {"a": 1}), ("a list holding a non-object", [node(True), 1]),
                            ("an empty string", ""), ("an empty dict", {})):
            gh.graphql = paged([[node(True)] * 100, page])
            try:
                prs.review_threads("o", "r", 1)
                check(f"a thread page of {label}: raised", False)
            except TypeError:
                check(f"a thread page of {label}: raised, never counted", True)
        gh.graphql = paged([[node(True)] * 100, None])
        check("a thread page whose nodes are null is none, not unreadable", len(prs.review_threads("o", "r", 1)) == 100)

        def thread_info(query, **kw):
            return {"repository": {"pullRequest": {"reviewThreads": {"nodes": [node(False)], "pageInfo": "x"}}}}
        gh.graphql = thread_info
        try:
            prs.review_threads("o", "r", 1)
            check("a thread page whose pageInfo is not an object: raised", False)
        except TypeError:
            check("a thread page whose pageInfo is not an object: raised, never the last page", True)
        gh.graphql = paged([[node(True)]] * (prs.THREAD_PAGES + 1))
        try:
            prs.review_threads("o", "r", 1)
            check("past the page cap: raised", False)
        except ValueError:
            check("past the page cap: raised, never a short count", True)

        first = {"repository": {"pullRequest": {
            "mergeStateStatus": "CLEAN", "mergeable": "MERGEABLE", "mergeQueueEntry": None, "autoMergeRequest": None,
            "headRefOid": "H",
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
        check("pr-gate counts an unresolved thread on the second page", pr_gate.gate_state("o/r", 1, "H")["unresolved"] == "1")
        gh.graphql = gate(gh.GhError("gh api graphql", "no answer", transient=True))
        st = pr_gate.gate_state("o/r", 1, "H")
        check("a second page that cannot be read: ?, which blocks", st["unresolved"] == "?"
              and "unresolved thread" in pr_gate.verdict(1, "main", False, None, st, REVIEWED, []))

        print("checks past the first 100")
        ok = {"name": "ok", "status": "COMPLETED", "conclusion": "SUCCESS"}
        red = {"name": "late", "status": "COMPLETED", "conclusion": "FAILURE"}

        def rollup(rest, more=True, cursor="0", head="H"):
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
                        "mergeStateStatus": "CLEAN", "mergeable": "MERGEABLE", "mergeQueueEntry": None, "headRefOid": "H",
                        "autoMergeRequest": None, "reviewThreads": {"nodes": [], "pageInfo": {"hasNextPage": False}},
                        "statusCheckRollup": {"contexts": {"nodes": [ok] * 100,
                                                           "pageInfo": {"hasNextPage": more, "endCursor": cursor if more else None}}}}}}
                assert asks and asks.group(1) and kw.get("after") is not None, (query, kw)
                if isinstance(rest, Exception):
                    raise rest
                i = int(kw["after"])
                last = i == len(rest) - 1
                pr = {"statusCheckRollup": {"contexts": {
                    "nodes": rest[i], "pageInfo": {"hasNextPage": not last, "endCursor": None if last else str(i + 1)}}}}
                if re.search(r"pullRequest\(number: \$number\) \{\s+headRefOid\b", query):
                    pr["headRefOid"] = head
                return {"repository": {"pullRequest": pr}}
            return fake
        gh.graphql = rollup([], more=False)
        check("one page of green checks: green", pr_gate.gate_state("o/r", 1, "H")["checks"] == "green")
        gh.graphql = rollup([[ok] * 100, [red]])
        check("a red check on the third page: red, named", pr_gate.gate_state("o/r", 1, "H")["checks"] == "red:late")
        gh.graphql = rollup([[ok, {"name": "slow", "status": "IN_PROGRESS", "conclusion": None}]])
        check("a running check on the second page: pending", pr_gate.gate_state("o/r", 1, "H")["checks"] == "pending:1")
        for label, rest in (("a page that cannot be read", gh.GhError("gh api graphql", "HTTP 502", 502, True)),
                            ("a page with no cursor to the next", "no-cursor"),
                            ("past the page cap", [[ok]] * (pr_gate.CONTEXT_PAGES + 1)),
                            ("a malformed page", ["x"]),
                            ("a page holding a non-object", [[ok, 1]])):
            if rest == "no-cursor":
                def rest_fake(query, **kw):
                    if "mergeStateStatus" in query:
                        return rollup([])(query, **kw)
                    return {"repository": {"pullRequest": {"headRefOid": "H", "statusCheckRollup": {"contexts": {
                        "nodes": [ok], "pageInfo": {"hasNextPage": True, "endCursor": None}}}}}}
                gh.graphql = rest_fake
            else:
                gh.graphql = rollup(rest)
            st = pr_gate.gate_state("o/r", 1, "H")
            check(f"{label}: checks ?, which blocks", st["checks"] == "?"
                  and "the checks could not all be read" in pr_gate.verdict(1, "main", False, None, st, REVIEWED, []))
        # The cases above reach a later page; these fail on the way to it.
        for label, fake in (("a first page with no cursor to the next", rollup([[ok]], cursor=None)),
                            ("a head that moved between the pages", rollup([[ok]], head="other")),
                            ("a later page whose nodes are not a list", rollup([{"name": "x"}])),
                            ("a first page whose nodes are not a list", None)):
            if fake is None:
                def fake(query, **kw):
                    d = rollup([], more=False)(query, **kw)
                    d["repository"]["pullRequest"]["statusCheckRollup"]["contexts"]["nodes"] = {"name": "x"}
                    return d
            gh.graphql = fake
            st = pr_gate.gate_state("o/r", 1, "H")
            check(f"{label}: checks ?, which blocks", st["checks"] == "?"
                  and "the checks could not all be read" in pr_gate.verdict(1, "main", False, None, st, REVIEWED, []))
        gh.graphql = rollup([[red]])
        check("the same head on every page: read", pr_gate.gate_state("o/r", 1, "H")["checks"] == "red:late")

        def threads_no_cursor(query, **kw):
            assert "mergeStateStatus" in query, "a thread page was asked with no cursor"
            d = rollup([], more=False)(query, **kw)
            d["repository"]["pullRequest"]["reviewThreads"] = {"nodes": [node(True)] * 100,
                                                               "pageInfo": {"hasNextPage": True, "endCursor": None}}
            return d
        check("listed: null is none, a list of objects is itself, anything else unreadable",
              pr_gate.listed(None) == [] and pr_gate.listed([{"a": 1}]) == [{"a": 1}] and pr_gate.listed([]) == []
              and all(pr_gate.listed(v) is None for v in ({}, "", {"a": 1}, "x", 0, [1], [{"a": 1}, None])))
        check("obj: null is empty, an object is itself, anything else unreadable",
              pr_gate.obj(None) == {} and pr_gate.obj({"a": 1}) == {"a": 1}
              and all(pr_gate.obj(v) is None for v in ("", "x", [], [1], 0)))
        for label, shape in (("an empty dict", {}), ("an empty string", ""), ("a list holding a non-object", [1])):
            def fake(query, shape=shape, **kw):
                d = rollup([], more=False)(query, **kw)
                d["repository"]["pullRequest"]["statusCheckRollup"]["contexts"]["nodes"] = shape
                d["repository"]["pullRequest"]["reviewThreads"]["nodes"] = shape
                return d
            gh.graphql = fake
            st = pr_gate.gate_state("o/r", 1, "H")
            check(f"a first page of {label}: checks and threads ?", st["checks"] == "?" and st["unresolved"] == "?")
        gh.graphql = rollup([], more=False)
        check("the checks of another head than the row's: ?", pr_gate.gate_state("o/r", 1, "other")["checks"] == "?")
        def headless(query, **kw):
            d = rollup([], more=False)(query, **kw)
            d["repository"]["pullRequest"]["headRefOid"] = ""
            return d
        gh.graphql = headless
        check("no head to compare, on either side: ?", pr_gate.gate_state("o/r", 1, "")["checks"] == "?")
        def shaped(*path_value):
            """GATE_QUERY's one-page answer with the value at each path replaced."""
            def fake(query, **kw):
                d = rollup([], more=False)(query, **kw)
                for path, value in path_value:
                    at = d["repository"]["pullRequest"]
                    for key in path[:-1]:
                        at = at[key]
                    at[path[-1]] = value
                return d
            return fake
        for label, path, value, column in (
                ("a rollup that is not an object", ("statusCheckRollup",), "x", "checks"),
                ("contexts that are not an object", ("statusCheckRollup", "contexts"), "x", "checks"),
                ("a contexts pageInfo that is not an object", ("statusCheckRollup", "contexts", "pageInfo"), "x", "checks"),
                ("threads that are not an object", ("reviewThreads",), [1], "unresolved"),
                ("a threads pageInfo that is not an object", ("reviewThreads", "pageInfo"), "x", "unresolved")):
            gh.graphql = shaped((path, value))
            st = pr_gate.gate_state("o/r", 1, "H")
            check(f"{label}: ?, not a traceback nor a count", st[column] == "?")
        gh.graphql = shaped((("statusCheckRollup", "contexts", "pageInfo"), None), (("reviewThreads", "pageInfo"), None))
        st = pr_gate.gate_state("o/r", 1, "H")
        check("a null pageInfo is no next page", st["checks"] == "green" and st["unresolved"] == "0")
        gh.graphql = shaped((("mergeQueueEntry",), "x"))
        check("a queue entry that is not an object: the PR unreadable, not a traceback", pr_gate.gate_state("o/r", 1, "H") is None)
        gh.graphql = lambda query, **kw: {"repository": "x"}
        check("a repository that is not an object: the PR unreadable, not a traceback", pr_gate.gate_state("o/r", 1, "H") is None)
        gh.graphql = threads_no_cursor
        check("threads: a next page with no cursor is ?, never page one again", pr_gate.gate_state("o/r", 1, "H")["unresolved"] == "?")
        gh.graphql = rollup([], more=False)
        st = pr_gate.gate_state("o/r", 1, "H")
        check("...and green does not", st["checks"] == "green" and "BLOCKED" not in pr_gate.verdict(1, "main", False, None, st, REVIEWED, []))
        gh.graphql = shaped((("mergeable",), "CONFLICTING"), (("reviewThreads", "nodes"), [node(False)] * 2),
                            (("autoMergeRequest",), {"enabledAt": "x"}),
                            (("mergeQueueEntry",), {"position": 3, "state": "AWAITING_CHECKS"}))
        st = pr_gate.gate_state("o/r", 1, "H")
        check("gate_state: the conflict, two unresolved threads, armed and the queue position are read",
              (st["mergeable"], st["unresolved"], st["armed"], st["queue"]) == ("CONFLICTING", "2", "yes", "3"))
        gh.graphql = shaped((("mergeQueueEntry",), None))
        st = pr_gate.gate_state("o/r", 1, "H")
        check("gate_state: not queued, not armed, no unresolved thread",
              (st["mergeable"], st["unresolved"], st["armed"], st["queue"]) == ("MERGEABLE", "0", "no", ""))
        gh.graphql = rollup([], more=False)
        st = pr_gate.gate_state("o/r", 1, "other")
        check("a push since the PR list: the checks are another head's, ?, which blocks",
              st["checks"] == "?" and "the checks could not all be read" in pr_gate.verdict(1, "main", False, None, st, REVIEWED, []))
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

    # The CLI suite's branch of work, fixes and a merge, split in-process:
    # the subjects that count as fix, the Answers: trailer (one of them
    # folded, RFC-822 style), and a revert netted with its in-range partner.
    print("split_range: work, fix and merge; a revert nets once")
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

        def row_of(c: dict) -> dict:
            return {"number": 7, "title": "the thing", "owner": "h/l", "mine": True, "commits_known": True,
                    "work_commits": c["work"], "fix_commits": c["fix"], "merge_commits": c["merge"],
                    "netted_commits": c["netted"], "fix_subjects": c["fix_subjects"],
                    "netted_subjects": c["netted_subjects"], "checks": "green", "review": "head reviewed",
                    "unresolved_threads": "0", "armed": "no", "queue_position": "", "verdict": "v"}

        git("init", "-q", "-b", "main")
        base = commit(0, "base")
        git("checkout", "-q", "-b", "h/l/feat/x")
        commit(1, "work one")
        commit(2, "work two")
        git("checkout", "-q", "-b", "side", "main")
        commit(3, "side change")
        git("checkout", "-q", "h/l/feat/x")
        git("merge", "-q", "--no-ff", "side", "-m", "Merge origin/main")
        fixes = ["fix: the review's F1 and F2",
                 "geocode: address the blind review of the entrypoint",
                 "third-round review: four P3s, the .env pin and the dropped spellings",
                 "db: 0055's guard was too broad and stopped the file re-applying",
                 "docs(adr): the backfilled row keeps its updated_at"]
        commit(4, fixes[0])
        commit(5, "admin driver review: approving a stranded applicant gets its own 409")
        commit(6, "fix(passenger): the debounce still fired the wrong query")
        commit(7, fixes[1])
        commit(8, fixes[2])
        commit(9, "feat(contracts): the review decision's reason reaches the merchant")
        commit(10, fixes[3], "Answers: PE-6")
        commit(11, fixes[4], "Answers: PE-6,\n  PR-1")
        here = os.getcwd()
        os.chdir(repo)
        try:
            c = pr_gate.split_range(7, "", f"{base}..HEAD")
            git("update-ref", "refs/remotes/origin/main", base)
            known = pr_gate.count_commits(7, "", "main", git("rev-parse", "HEAD"))
            unknown = pr_gate.count_commits(7, "", "main", "deadbeef" * 5)
            nobase = pr_gate.count_commits(7, "", "nobranch", git("rev-parse", "HEAD"))
            # A work commit, git's own revert of it, a revert of a commit
            # that is not in the range (it changes the tree: work), and a
            # "Revert" subject with no trailer line (prose: work).
            commit(12, "feat: the used-by guard")
            git("revert", "--no-edit", "HEAD")
            commit(13, 'Revert "base"', f"This reverts commit {base}.")
            commit(14, "Revert the thing by hand")
            after_pair = pr_gate.split_range(7, "", f"{base}..HEAD")
            # feat B; revert B; reapply B (the revert of the revert): the
            # tree after the chain is B's, so B stands as work.
            commit(15, "feat: B, the thing reapplied")
            git("revert", "--no-edit", "HEAD")
            git("revert", "--no-edit", "HEAD")
            after_chain = pr_gate.split_range(7, "", f"{base}..HEAD")
        finally:
            os.chdir(here)
        check(f"12 commits: 6 work, 5 fix, 1 merge (got {c['work']}, {c['fix']}, {c['merge']})",
              (c["work"], c["fix"], c["merge"], c["netted"]) == (6, 5, 1, 0))
        check("the fixes are the F1/F2 labels, 'address the blind review', 'third-round review', and the two "
              "review-less subjects with an Answers: trailer (one folded); a domain 'driver review:', a "
              "fix(scope): bug fix and a 'review decision' feature are work",
              sorted(c["fix_subjects"]) == sorted(fixes))
        check("count_commits: the same split over origin/<base>..<head>",
              known is not None and (known["work"], known["fix"], known["merge"]) == (6, 5, 1))
        check("count_commits: a head the clone does not have, or a base it does not have, is None, never a zero",
              unknown is None and nobase is None)
        check("four commits added: the in-range pair is netted (2); the revert of a main commit and the "
              "trailer-less 'Revert' are work (+2); fixes unchanged",
              (after_pair["work"], after_pair["fix"], after_pair["netted"]) == (8, 5, 2))
        check("...and the netted pair is named, as the fixes are",
              sorted(after_pair["netted_subjects"]) == sorted(['Revert "feat: the used-by guard"', "feat: the used-by guard"]))
        text = pr_gate.render(row_of(after_pair))
        check("the row says so, and names the pair",
              "commits=16 (8 work, 5 fix, 1 merge, 2 netted by a revert)" in text
              and 'netted by a revert: "' in text and "feat: the used-by guard" in text)
        check("a revert of a revert leaves the original as work: B stands (+1), two more netted (4)",
              (after_chain["work"], after_chain["netted"]) == (9, 4))
        unknown_row = dict(row_of(after_pair), commits_known=False, work_commits=None, fix_commits=None,
                           merge_commits=None, netted_commits=None, fix_subjects=[], netted_subjects=[])
        check("a row whose commits are unknown says so", "commits=unknown (fetch)" in pr_gate.render(unknown_row))

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

    print("a MERGED pull request named by number: its split, never a zero")
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
        commit(0, "base")
        git("checkout", "-q", "-b", "h/l/feat/x")
        commit(1, "first piece", "Kind: work")
        commit(2, "second piece", "Kind: work")
        commit(3, "answer a finding", "Answers: F1")
        git("checkout", "-q", "main")
        commit(4, "main moves on")
        git("merge", "-q", "--no-ff", "-m", "Merge pull request #9 from h/l/feat/x", "h/l/feat/x")
        merge, plain = git("rev-parse", "HEAD"), git("rev-parse", "HEAD~1")
        pr = {"number": 9, "title": "the feature", "headRefName": "h/l/feat/x", "headRefOid": "f" * 40,
              "state": "MERGED", "mergeCommit": {"oid": merge}}
        here = os.getcwd()
        os.chdir(repo)
        try:
            from github import pr_compliance
            row = pr_gate.merged_row(pr, "o/r", True, "h/l")
            same = pr_compliance.commit_split(9, "o/r", merge)
            squashed = pr_gate.merged_row(dict(pr, mergeCommit=None), "o/r", True, "h/l")
            single_parent = pr_gate.merged_row(dict(pr, mergeCommit={"oid": plain}), "o/r", True, "h/l")
            unfetched = pr_gate.merged_row(dict(pr, mergeCommit={"oid": "a" * 40}), "o/r", True, "h/l")
            no_fetch = pr_gate.merged_row(pr, "o/r", False, "h/l")
        finally:
            os.chdir(here)
        check(f"2 work, 1 fix, 0 merge over <merge>^1..<merge>^2 (got {row['work_commits']}, {row['fix_commits']}, "
              f"{row['merge_commits']})", (row["work_commits"], row["fix_commits"], row["merge_commits"]) == (2, 1, 0))
        check("the row is pr-compliance's split for the same PR",
              same is not None and (same["work"], same["fix"], same["merge"], same["netted"])
              == (row["work_commits"], row["fix_commits"], row["merge_commits"], row["netted_commits"]))
        text = pr_gate.render(row)
        check("rendered as one row marked MERGED and not at any gate",
              "commits=3 (2 work, 1 fix, 0 merge)" in text and "state=MERGED" in text
              and text.endswith("MERGED — not at any gate") and "(me)" in text)
        check("it is mine, by its branch prefix", row["mine"] is True)
        for label, r in (("no merge commit", squashed), ("a commit with one parent", single_parent),
                         ("a merge commit this clone never fetched", unfetched), ("a failed fetch", no_fetch)):
            check(f"{label}: cannot be counted, not a zero",
                  r["commits_known"] is False and r["work_commits"] is None and r["fix_commits"] is None
                  and "commits=cannot be counted" in pr_gate.render(r) and "0 work" not in pr_gate.render(r))

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
