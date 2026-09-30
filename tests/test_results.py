#!/usr/bin/env python3
"""Tests for tools/fabric/results.py's judgement of one merged PR (ADR-026 §2):
planted PRs and commits, a stub classifier, no network."""
from __future__ import annotations

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "fabric"))
import results  # noqa: E402

NOW = dt.datetime(2026, 10, 30, tzinfo=dt.timezone.utc)
HEAD = "a" * 40


def pr(**kw) -> dict:
    base = {"number": 7, "title": "t", "mergedAt": "2026-10-01T10:00:00Z", "headRefOid": HEAD,
            "mergeCommit": {"oid": "m" * 40},
            "reviews": [{"body": results.REVIEW_MARKER + "\nfindings", "commit": {"oid": HEAD}}],
            "statusCheckRollup": [{"conclusion": "SUCCESS"}, {"conclusion": "SKIPPED"}],
            "commits": [{"oid": HEAD, "messageHeadline": f"work {i}", "messageBody": ""} for i in range(8)]}
    base.update(kw)
    return base


def cls(subject: str, body: str, n: int, repo: str, parents: int = 1) -> str:
    if parents > 1:
        return "merge"
    return "fix" if subject.startswith("review fix") else "work"


def later(subject: str, body: str = "") -> dict:
    return {"sha": "b" * 40, "subject": subject, "body": body, "when": dt.datetime(2026, 10, 3, tzinfo=dt.timezone.utc)}


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    r = results.judge(pr(), [], NOW, 14, cls)
    check("reviewed on its head, green, nothing after it, window closed: verified", r["status"] == "verified" and r["work"] == 8, r)
    r = results.judge(pr(), [], dt.datetime(2026, 10, 5, tzinfo=dt.timezone.utc), 14, cls)
    check("the same inside its window: pending", r["status"] == "pending", r)
    r = results.judge(pr(reviews=[{"body": results.REVIEW_MARKER, "commit": {"oid": "c" * 40}}]), [], NOW, 14, cls)
    check("a review of an earlier head is not a review of the head", r["status"] == "not verified" and "no review on its head" in r["reasons"], r)
    r = results.judge(pr(reviews=[{"body": "LGTM", "commit": {"oid": HEAD}}]), [], NOW, 14, cls)
    check("a comment without the marker is not the review", r["status"] == "not verified", r)
    r = results.judge(pr(statusCheckRollup=[{"conclusion": "SUCCESS"}, {"conclusion": "FAILURE"}]), [], NOW, 14, cls)
    check("one red check: not verified", "checks not green" in r["reasons"], r)
    r = results.judge(pr(statusCheckRollup=[]), [], NOW, 14, cls)
    check("no checks at all is not green", "checks not green" in r["reasons"], r)
    r = results.judge(pr(), [later("Revert x", f"This reverts commit {HEAD}.")], NOW, 14, cls)
    check("a revert of one of its commits: not verified", r["reasons"] == ["reverted"], r)
    r = results.judge(pr(), [later("review fix (#7 review, P2): the bound")], NOW, 14, cls)
    check("a later fix naming it: not verified, the fix named", r["status"] == "not verified" and r["reasons"][0].startswith("fixed forward"), r)
    r = results.judge(pr(), [later("review fix (#70 review): other"), later("feat: mention #7 in passing")], NOW, 14, cls)
    check("#70's fix and a work commit naming #7 do not unverify it", r["status"] == "verified", r)
    few = pr(commits=[{"oid": HEAD, "messageHeadline": "a thing (owner)", "messageBody": ""},
                      {"oid": HEAD, "messageHeadline": "review fix (#7): x", "messageBody": ""}])
    r = results.judge(few, [], NOW, 14, cls)
    check("supervision: under the band's floor (the owner arms) plus one owner correction", r["supervision"] == 2 and (r["work"], r["fix"]) == (1, 1), r)
    merged_in = pr(commits=[{"oid": HEAD, "messageHeadline": f"work {i}", "messageBody": ""} for i in range(7)]
                   + [{"oid": HEAD, "messageHeadline": "Merge a contributor branch", "messageBody": "", "parents": 2}])
    r = results.judge(merged_in, [], NOW, 14, cls)
    check("a merge folded into the branch is not work: 7 work, so the owner armed it", (r["work"], r["supervision"]) == (7, 1), r)
    r = results.judge(merged_in, [], NOW, 14)   # the real classifier, through commit-class.sh
    check("…and the real classifier reads the merge by its parents", r["work"] == 7, r)

    # The reads, through gh.py against a fake gh: the PR numbers, each PR
    # alone, its commits' parents from REST, main's commits from REST.
    import tempfile
    fake = r"""#!/usr/bin/env python3
import json, sys
a = sys.argv[1:]
if a[:2] == ["pr", "list"]:
    print(json.dumps([{"number": 7}]))
elif a[:2] == ["pr", "view"]:
    print(json.dumps({"number": 7, "mergedAt": "2026-10-01T10:00:00Z",
                      "commits": [{"oid": "c1"}, {"oid": "c2"}]}))
elif "pulls/7/commits" in a[1]:
    print(json.dumps([[{"sha": "c1", "parents": [{}]}, {"sha": "c2", "parents": [{}, {}]}]]))
elif "/commits?since=" in a[1]:
    print(json.dumps([[{"sha": "s1", "commit": {"message": "fix x\n\nbody", "committer": {"date": "2026-10-02T00:00:00Z"}}}]]))
else:
    sys.exit(9)
"""
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "gh"), "w").write(fake)
        os.chmod(os.path.join(tmp, "gh"), 0o755)
        old = os.environ["PATH"]
        os.environ["PATH"] = tmp + os.pathsep + old
        try:
            prs = results.merged_prs("o/r", dt.date(2026, 9, 1))
            commits = results.main_commits("o/r", dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc))
        finally:
            os.environ["PATH"] = old
    check("merged_prs: each PR read alone, its commits' parents counted from REST",
          [c["parents"] for c in prs[0]["commits"]] == [1, 2], prs)
    check("main_commits: subject, body and time from the REST list",
          commits == [{"sha": "s1", "subject": "fix x", "body": "body",
                       "when": dt.datetime(2026, 10, 2, tzinfo=dt.timezone.utc)}], commits)
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
