#!/usr/bin/env python3
"""Tests for tools/fabric/errors.py (ADR-061, Proposed): recorded PRs, reviews, check runs and
main-branch commits as planted fixtures, no network. The ruleset and the host registry are the real ones."""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "fabric"))
import errors  # noqa: E402

NOW = dt.datetime(2026, 10, 30, tzinfo=dt.timezone.utc)
MARK = errors.REVIEW_MARKER
# The host registry is instance data (ADR-045 §5 rule 3): a fixture, never the checkout's.
HOSTS = {"develop-qzapp", "other-host"}
AGG = errors.aggregate_checks()
H = "develop-qzapp"


def commit(oid, headline="work", body="", parents=("p",), role="python-dev"):
    trailer = f"\n\nFabric-Role: {role}" if role else ""
    return {"oid": oid, "messageHeadline": headline, "messageBody": body + trailer if not body else f"{body}\nFabric-Role: {role}" if role else body,
            "parents": len(parents), "parentShas": list(parents)}


def pr(number=7, ref=None, commits=None, reviews=(), merged="2026-10-01T10:00:00Z", merge="m1"):
    commits = commits or [commit("c1"), commit("c2", parents=("c1",))]
    return {"number": number, "headRefName": ref or f"{H}/alice/feat/x", "headRefOid": commits[-1]["oid"],
            "mergedAt": merged, "mergeCommit": {"oid": merge}, "commits": commits, "reviews": list(reviews)}


def review(body, oid):
    return {"body": MARK + "\n" + body, "commit": {"oid": oid}}


def run(p, later=(), runs=None):
    runs = runs or {}
    return errors.events_of("o/r", p, list(later), lambda repo, sha: runs.get(sha, []), NOW, 14, HOSTS, AGG)


def cr(name, conclusion, at="2026-10-01T01:00:00Z"):
    return {"name": name, "conclusion": conclusion, "completed_at": at, "id": 1}


def main() -> int:
    fails = 0

    def check(label, good, detail=""):
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    # --- review findings
    body = "**F1 (P2, x)** a\n**F2 (P3, y)** b\n**F2 (P3, y)** again\n"
    cs = [commit("c1"), commit("c2", "review fix", "Answers: F1", parents=("c1",)), commit("c3", parents=("c2",))]
    ev = [e for e in run(pr(commits=cs, reviews=[review(body, "c1")])) if e["kind"] == "review"]
    check("findings by level, a label twice counted once; the answered one named by an Answers: commit after the review",
          ev[0]["findings"] == [{"level": "P2", "answered": True}, {"level": "P3", "answered": False}] and not ev[0]["unparsed"], ev)
    ev = [e for e in run(pr(commits=cs, reviews=[review("**F1 (P2, x)** a", "c3")])) if e["kind"] == "review"]
    check("an Answers: commit BEFORE the review does not answer it", ev[0]["findings"] == [{"level": "P2", "answered": False}], ev)
    ev = [e for e in run(pr(reviews=[review("P1: none\nP2: none\nP3: no findings", "c1")])) if e["kind"] == "review"]
    check("a review that says there are none is a parsed review of zero findings", ev[0]["findings"] == [] and not ev[0]["unparsed"], ev)
    ev = [e for e in run(pr(reviews=[review("- P2 the lock is wrong\nfix it", "c1")])) if e["kind"] == "review"]
    check("a review naming a level in another shape is unparsed, not zero", ev[0]["unparsed"] and ev[0]["findings"] == [], ev)
    ev = run(pr(reviews=[{"body": "**F1 (P1, x)** hi", "commit": {"oid": "c1"}}, review("**F1 (P1)**", "zz")]))
    check("an unmarked comment is no review; a marked one on a commit outside the PR is said, not counted",
          [e["kind"] for e in ev if e["kind"].startswith("review")] == ["review_elsewhere"], ev)

    # --- red checks
    runs = {"c1": [cr("static", "failure"), cr("ci-ok", "failure"), cr("unit", "cancelled"), cr("lint", "success")],
            "c2": [cr("static", "timed_out"), cr("static", "success", "2026-10-01T02:00:00Z"), cr("lint", "success")]}
    heads = {e["sha"] if "sha" in e else i: e for i, e in enumerate(e for e in run(pr(), runs=runs) if e["kind"] == "head")}
    h1, h2 = list(heads.values())
    check("a named failure is red; the aggregate and a cancelled run are not", h1["red"] == ["static"] and h1["flaky"] == [], h1)
    check("red then green on the same sha is flaky, the check's and not the actor's", h2["red"] == [] and h2["flaky"] == ["static"], h2)
    check("the ruleset's required context is what is excluded as the aggregate", "ci-ok" in AGG, AGG)
    ev = [e for e in run(pr(), runs={"c1": [cr("ci-ok", "failure"), cr("unit", "cancelled")]}) if e["kind"] == "head"]
    check("a head with only the aggregate and a cancelled run is not a head pushed in the denominator", ev == [], ev)
    ev = [e for e in run(pr(), runs={"c1": [cr("static", "success", "2026-10-01T02:00:00Z"), cr("static", "failure", "2026-10-01T03:00:00Z")]}) if e["kind"] == "head"]
    check("green then red is red (positive control for the flaky split)", ev[0]["red"] == ["static"] and ev[0]["flaky"] == [], ev)

    # --- reverts and fixes forward, inside the window
    def later(subject, body="", day=3):
        return {"sha": "f" * 40, "subject": subject, "body": body, "when": dt.datetime(2026, 10, day, tzinfo=dt.timezone.utc)}
    ev = run(pr(commits=[commit("a" * 40), commit("b" * 40, parents=("a" * 40,))]),
             [later("Revert x", "This reverts commit " + "a" * 40 + "."), later("review fix #7 F1: the lock", "Answers: F1"),
                    later("Revert y", "mentions revert only"), later("fix #8 other"), later("late fix #7 F2", day=25)])
    kinds = [(e["kind"], e.get("actor")) for e in ev if e["kind"] in ("revert", "fix")]
    check("one revert (git's line naming a PR commit), one fix naming #7; the phrase alone and the other PR and the late one are not",
          sorted(kinds) == [("fix", "alice"), ("revert", "alice")], ev)
    check("their PR's window had closed", all(e["closed"] for e in ev if e["kind"] in ("revert", "fix")), ev)
    ev = errors.events_of("o/r", pr(merged="2026-10-25T00:00:00Z"), [later("fix #7 F1", "Answers: F1", day=26)],
                          lambda r, s: [], NOW, 14, HOSTS, AGG)
    t = errors.tally(ev)
    check("a fix on a PR whose window is still open is apart from the denominator",
          t["fixes"]["count"] == 0 and t["fixes"]["of_prs_with_closed_window"] == 0 and t["fixes"]["found_so_far_in_open_windows"] == 1, t["fixes"])

    # --- attribution
    check("head ref: the login", errors.head_actor(f"{H}/bob/feat/x", HOSTS) == "bob")
    check("a ref whose first segment is no fabric host is unattributed, not guessed",
          errors.head_actor("dependabot/pip/x", HOSTS) == "unattributed" and errors.head_actor("main", HOSTS) == "unattributed", "")
    ev = run(pr(ref="dependabot/pip/x"))
    check("an unattributed PR is counted with its count", errors.report(ev)["total"]["unattributed_prs"] == 1
          and "unattributed" in errors.report(ev)["total"]["by_actor"], errors.report(ev)["total"]["by_actor"].keys())
    fold = [commit("a" * 40, role="web-dev"), commit("a2", parents=("a" * 40,), role="web-dev"),
            commit("b1", role="python-dev"),
            commit("m", f"Merge branch '{H}/carol/for/alice/thing' into {H}/alice/feat/x", parents=("b1", "a2"), role="python-dev")]
    runs = {"a2": [cr("static", "failure")], "b1": [cr("static", "success")], "m": [cr("static", "failure")]}
    ev = run(pr(commits=fold, reviews=[review("**F1 (P3, x)** a", "m")], merge="mm"), [later("Revert", "This reverts commit " + "a" * 40 + ".")], runs)
    h = {e["red"] and e["actor"] or "": e for e in ev if e["kind"] == "head"}
    check("a commit that arrived by a fold of a for/ branch is that branch's login; the fold merge itself is no head",
          sum(1 for e in ev if e["kind"] == "head") == 2 and h["carol"]["role"] == "web-dev" and h["carol"]["class"] == "agent", ev)
    check("a revert of a folded commit is its contributor's; the review stays with the head ref's login",
          [e["actor"] for e in ev if e["kind"] == "revert"] == ["carol"] and [e["actor"] for e in ev if e["kind"] == "review"] == ["alice"], ev)
    one = [commit("b1"), commit("m", f"Merge branch '{H}/carol/for/alice/thing'", parents=("b1",))]
    check("a fold-looking headline on a commit with one parent attributes nothing", errors.fold_logins(one, HOSTS) == {}, "")
    ev = run(pr(commits=[commit("c1", role=""), commit("c2", parents=("c1",), role="")]))
    check("no Fabric-Role trailer: class person, no role invented", ev[0]["class"] == "person" and ev[0]["role"] == "-", ev[0])

    # --- denominators and the under-5 rule
    check("rate: 4 denominators show no rate, 5 do", errors.rate(2, 4) is None and errors.rate(2, 5) == 0.4)
    many = []
    for i in range(5):
        many += run(pr(number=10 + i), runs={"c1": [cr("static", "failure")] if i == 0 else [cr("static", "success")], "c2": []})
    t = errors.tally(many)
    check("5 heads: the rate is shown beside heads_red/heads; 4 PRs would not",
          t["red_checks"]["heads"] == 5 and t["red_checks"]["heads_red"] == 1 and t["red_checks"]["rate"] == 0.2, t["red_checks"])
    check("5 closed PRs with 0 reverts: a rate of 0.0, not 'none'", t["reverts"]["rate"] == 0.0 and t["reverts"]["of_prs_with_closed_window"] == 5, t["reverts"])
    t4 = errors.tally(many[:len(many) // 5 * 4])
    check("below 5: the count stays, the rate is None", t4["red_checks"]["heads_red"] in (0, 1) and t4["red_checks"]["rate"] is None, t4["red_checks"])

    # --- report shape: names in order, no combined score
    rep = errors.report(run(pr(ref=f"{H}/zed/x")) + run(pr(number=8, ref=f"{H}/amy/x")))
    check("actors in name order, not by count", list(rep["total"]["by_actor"]) == ["amy", "zed"], list(rep["total"]["by_actor"]))
    check("no score key anywhere", "score" not in json.dumps(rep).lower() and "rank" not in json.dumps(rep).lower())

    # --- main(): text and JSON through stubbed readers
    saved = (errors.results.main_commits, errors.results.merged_prs, errors.gh.api, errors.known_hosts)
    errors.known_hosts = lambda: HOSTS
    errors.results.main_commits = lambda repo, since: []
    errors.results.merged_prs = lambda repo, since, extra=(): [pr(merged="2026-10-25T00:00:00Z")]
    errors.gh.api = lambda *a, **k: [cr("static", "failure")]
    try:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = errors.main(["--days", "30", "--repo", "o/r", "--json"])
        js = json.loads(out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc2 = errors.main(["--repo", "o/r"])
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc3 = errors.main(["--days", "0"])
    finally:
        errors.results.main_commits, errors.results.merged_prs, errors.gh.api, errors.known_hosts = saved
    check("main --json: the red head counted, window open", rc == 0 and js["repositories_read"] == ["o/r"] and list(js["repos"]) == ["o/r"]
          and js["total"]["all"]["red_checks"]["heads_red"] == 2 and js["total"]["all"]["prs_window_closed"] == 0, js["total"]["all"])
    check("main text says what is not read and shows no rate under 5", rc2 == 0 and "judged-not-real findings: not read" in out.getvalue()
          and "no rate (<5)" in out.getvalue(), out.getvalue())
    check("a bad --days is exit 2 and a line", rc3 == 2 and "at least 1" in err.getvalue(), err.getvalue())

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
