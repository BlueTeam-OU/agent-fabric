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
CI = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), errors.WORKFLOW), encoding="utf-8").read()
NEEDED = errors.needed_jobs(CI, AGG)
H = "develop-qzapp"


def commit(oid, headline="work", body="", parents=("p",), role="python-dev", subject=None):
    trailer = f"\n\nFabric-Role: {role}" if role else ""
    return {"oid": oid, "messageHeadline": headline, "messageBody": body + trailer if not body else f"{body}\nFabric-Role: {role}" if role else body,
            "parents": len(parents), "parentShas": list(parents), **({"subject": subject} if subject else {})}


def pr(number=7, ref=None, commits=None, reviews=(), merged="2026-10-01T10:00:00Z", merge="m1"):
    commits = commits or [commit("c1"), commit("c2", parents=("c1",))]
    return {"number": number, "headRefName": ref or f"{H}/alice/feat/x", "headRefOid": commits[-1]["oid"],
            "mergedAt": merged, "mergeCommit": {"oid": merge}, "commits": commits, "reviews": list(reviews)}


def review(body, oid):
    return {"body": MARK + "\n" + body, "commit": {"oid": oid}}


def run(p, later=(), runs=None):
    runs = runs or {}
    return errors.events_of("o/r", p, list(later), lambda repo, sha: runs.get(sha, []), NOW, 30, 14, HOSTS, NEEDED)


def cr(name, conclusion, at="2026-10-01T01:00:00Z", workflow=errors.WORKFLOW):
    return {"name": name, "conclusion": conclusion, "completed_at": at, "id": 1, "workflow_path": workflow}


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
    def v2_body(report, *statuses, head="c1"):
        paths = {f"p{i}": ({"status": st} if st == "read" else {"status": st, "reason": "r"}) for i, st in enumerate(statuses)}
        marker = f"<!-- agent-fabric-review v2 base={'b' * 40} head={head.ljust(40, '0')} card={'c' * 40} config={'d' * 64} -->"
        return marker + "\n\n" + report + "\n```agent-fabric-coverage v1\n" + json.dumps({"paths": paths, "lenses": {}}) + "\n```\n"

    machine = "Finding: F1 | P2 | certain | a.py:1 | the lock\nFinding: F2 | P3 | possible | - | a nit\n"
    ev = [e for e in run(pr(commits=cs, reviews=[{"body": v2_body(machine, "read"), "commit": {"oid": "c1"}}])) if e["kind"] == "review"]
    check("a v2 review read in full is counted like a v1 one", len(ev) == 1 and not ev[0]["unparsed"]
          and [f["level"] for f in ev[0]["findings"]] == ["P2", "P3"], ev)
    ev = [e for e in run(pr(commits=cs, reviews=[{"body": v2_body(machine, "read", "not read"), "commit": {"oid": "c1"}}])) if e["kind"] == "review"]
    check("a v2 review with a path not read is shown as unparsed, its reason named, none of its findings counted",
          len(ev) == 1 and ev[0]["unparsed"] and ev[0]["findings"] == [] and "not read in full" in ev[0]["malformed"][0]
          and "1 path(s) not read" in ev[0]["malformed"][0], ev)
    ev = [e for e in run(pr(commits=cs, reviews=[{"body": v2_body(machine, "read").split("\n```")[0], "commit": {"oid": "c1"}}])) if e["kind"] == "review"]
    check("a v2 review whose block is missing is shown as unparsed too", len(ev) == 1 and ev[0]["unparsed"], ev)
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
    check("the ruleset's required context is the aggregate, and its needs are the jobs counted",
          "ci-ok" in AGG and "ci-ok" not in NEEDED and {"static", "platform-smoke"} <= NEEDED, (AGG, NEEDED))
    ev = [e for e in run(pr(), runs={"c1": [cr("pr-counts", "failure"), cr("stripped-nightly", "failure"), cr("CodeQL", "failure"),
                                            cr("platform-smoke (debian, x)", "failure")]}) if e["kind"] == "head"]
    check("a failed run of a job the aggregate does not need is not counted; a matrix leg of one it needs is",
          ev[0]["red"] == ["platform-smoke (debian, x)"], ev)
    ev = [e for e in run(pr(), runs={"c1": [cr("platform-smokeX", "failure"), cr("static-extra", "failure")]}) if e["kind"] == "head"]
    check("a name that only starts with a needed job's is not that job", ev == [], ev)
    check("needed_jobs: a job's name: is the check name; a list under needs",
          errors.needed_jobs("jobs:\n  a:\n    name: Alpha\n  z-ok:\n    needs:\n      - a\n", {"z-ok"}) == {"Alpha"}
          and errors.needed_jobs("jobs:\n  a:\n    x: 1\n  b:\n    x: 1\n  z-ok:\n    needs: [a, b]\n", {"z-ok"}) == {"a", "b"}, "")
    check("needed_jobs: no aggregate, a needed job missing, or an expression name is unknown, not guessed",
          errors.needed_jobs("jobs:\n  a:\n    x: 1\n", {"z-ok"}) is None
          and errors.needed_jobs("jobs:\n  z-ok:\n    needs: [gone]\n", {"z-ok"}) is None
          and errors.needed_jobs("jobs:\n  a:\n    name: x ${{ m }}\n  z-ok:\n    needs: [a]\n", {"z-ok"}) is None, "")
    ev = errors.events_of("o/r", pr(), [], lambda r, s: [cr("static", "failure")], NOW, 30, 14, HOSTS, None)
    t = errors.tally(ev)
    check("a repository with no readable aggregate: no head counted, said as unread",
          t["red_checks"]["heads"] == 0 and t["red_checks"]["unread_no_aggregate"] == 1, t["red_checks"])
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
                          lambda r, s: [], NOW, 30, 14, HOSTS, NEEDED)
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
    full = f"Merge branch '{H}/carol/for/alice/thing' into {H}/alice/feat/x"
    # GitHub cuts messageHeadline at about 70 characters and ends it in an ellipsis; the REST subject is whole.
    cut = f"Merge branch '{H}/carol/for/\u2026"
    fold = [commit("a" * 40, role="web-dev"), commit("a2", parents=("a" * 40,), role="web-dev"),
            commit("b1", role="python-dev"),
            commit("m", cut, parents=("b1", "a2"), role="python-dev", subject=full)]
    runs = {"a2": [cr("static", "failure")], "b1": [cr("static", "success")], "m": [cr("static", "failure")]}
    ev = run(pr(commits=fold, reviews=[review("**F1 (P3, x)** a", "m")], merge="mm"), [later("Revert", "This reverts commit " + "a" * 40 + ".")], runs)
    heads = [e for e in ev if e["kind"] == "head"]
    check("a commit that arrived by a fold of a for/ branch is that branch's login, read from the whole subject, not GitHub's cut headline",
          [e["actor"] for e in heads] == ["carol", "alice", "alice"] and heads[0]["role"] == "web-dev" and heads[0]["class"] == "agent", heads)
    check("the fold merge is a head CI ran on: counted, red, and the head-ref login's",
          heads[2]["red"] == ["static"] and heads[2]["actor"] == "alice", heads)
    check("with only the cut headline there is no fold to read: nothing is attributed to the branch's login",
          errors.fold_logins([dict(c, subject=None) for c in fold], HOSTS) == {}, "")
    rep = errors.report(ev)["total"]
    check("a fold contributor's revert row is beside the PRs it had a commit in: 1 of 1, a rate cannot exceed 1",
          rep["by_actor"]["carol"]["reverts"]["count"] == 1 and rep["by_actor"]["carol"]["reverts"]["of_prs_with_closed_window"] == 1
          and rep["by_actor"]["alice"]["reverts"]["of_prs_with_closed_window"] == 1 and rep["by_actor"]["alice"]["reverts"]["count"] == 0,
          {k: v["reverts"] for k, v in rep["by_actor"].items()})
    check("the class and role rows of the reverted commit have the same denominator: web-dev 1 of 1, agent 1 of 1",
          rep["by_role"]["web-dev"]["reverts"]["count"] == 1 and rep["by_role"]["web-dev"]["reverts"]["of_prs_with_closed_window"] == 1
          and rep["by_class"]["agent"]["reverts"]["count"] == 1 and rep["by_class"]["agent"]["reverts"]["of_prs_with_closed_window"] == 1,
          {k: v["reverts"] for k, v in rep["by_role"].items()})
    check("…and the PR is owned by alice alone",
          rep["by_actor"]["carol"]["prs_merged"] == 0 and rep["by_actor"]["alice"]["prs_merged"] == 1
          and rep["by_actor"]["carol"]["prs_in_closed_period"] == 0 and rep["by_actor"]["alice"]["prs_in_closed_period"] == 1, "")
    merge_ev = run(pr(commits=fold, merge="e" * 40), [later("Revert", "This reverts commit " + "e" * 40 + ".")])
    check("a revert of the merge commit is the head ref's login with the head commit's class and role",
          [(e["actor"], e["class"], e["role"]) for e in merge_ev if e["kind"] == "revert"] == [("alice", "agent", "python-dev")], merge_ev)
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

    # --- parsing: a finding line that contains "no" or "0" is not an absence; red, green, red is red
    f, un = errors.parse_review("1. P1 confirmed: a failed read returns no error, the count is 0\nP2: the retry has no backoff\nP3: none")
    check("a level line with more than the word for none is unparsed, not a clean review", f == [] and un, (f, un))
    f, un = errors.parse_review("P2: none of the callers check the result")
    check("a line that only begins with the word for none is a finding in another shape", f == [] and un, (f, un))
    for clean in ("P1: none. P2: none.", "None at P1, P2 or P3.", "No findings: P1 none, P2 none, P3 none.",
                  "No findings (P1, P2, P3 empty)."):
        f, un = errors.parse_review(clean)
        check(f"a clean review in prose parses as zero findings: {clean!r}", f == [] and not un, (f, un))
    f, un = errors.parse_review("P1 and P2 at the boundary or P3.")
    check("connectives and level tokens alone are no statement of absence", un, (f, un))
    for heading in ("P1 findings: none.\nP2 findings:\n- the lock is held across await\nP3 findings: none.",
                    "## P2 findings\n\n1. The lock is never released on the error path.", "Finding (P2). The lock is not released."):
        f, un = errors.parse_review(heading)
        check(f"a level heading is no statement of absence: {heading[:30]!r}", un, (f, un))
    for clean in ("## P1\nNone\n## P2\nNone", "**P1**\nNone.\n**P2**\nNone\n**P3**\nNone", "P1\n\nnone"):
        f, un = errors.parse_review(clean)
        check(f"a level heading with None on the next line is a review with no findings: {clean[:22]!r}", f == [] and not un, (f, un))
    for hidden in ("## P1\nThe caller ignores the result", "## P1", "## P1\n## P2\nNone", "## No P1 findings\n- the caller ignores the result",
                   "**No findings at P1:**\nthe lock is held across await"):
        f, un = errors.parse_review(hidden)
        check(f"a heading is no clean level when a finding follows it or nothing does: {hidden[:30]!r}", f == [] and un, (f, un))
    for clean in ("## No P1 findings\n---\n", "**No P1 findings.**", "**P1: none.**\n**P2: none.**\n**P3: none.**", "**P1** none\n**P2** none\n**P3** none\nOverall fine.",
                  "## P1 findings\nNone."):
        f, un = errors.parse_review(clean)
        check(f"a bold denial, a bold label with its value, and a 'findings' heading are clean: {clean[:24]!r}", f == [] and not un, (f, un))
    for hidden in ("## P1\nNone\n- the caller ignores the result", "## P1 findings\nNone\nThe lock is not released",
                   "## No P1 findings\n- \u547c\u3073\u51fa\u3057\u5074\u304c\u7d50\u679c\u3092\u7121\u8996\u3057\u3066\u3044\u308b"):
        f, un = errors.parse_review(hidden)
        check(f"a heading and its None do not hide a finding under them: {hidden[:24]!r}", f == [] and un, (f, un))
    f, un = errors.parse_review("## No P1 findings\n\n## P2: none\n\nP3: none")
    check("…and a denying heading followed only by denials stays clean", f == [] and not un, (f, un))
    f, un = errors.parse_review("P1 or P2.")
    check("…nor are bare levels", un, (f, un))
    f, un = errors.parse_review("P1: none. P2 the lock is wrong at the boundary.")
    check("a clean clause beside a finding clause is still unparsed", un, (f, un))
    f, un = errors.parse_review("P1: none\n- P2 \u2014 no findings\nP3: 0")
    check("lines that are only a level and none parse as zero findings", f == [] and not un, (f, un))
    # --- machine lines (j296): `Finding:` / `Judgement:`, one shape for every engine
    F1 = "Finding: F1 | P2 | certain | tools/fabric/errors.py:120 | the lock is held | across await"
    F2 = "Finding: F2 | P3 | possible | - | a comment is stale"
    r = errors.read_review("Prose.\n" + F1 + "\nlonger prose about it\n" + F2 + "\n")
    check("machine lines: findings by label and level; a summary may hold '|'; path may be '-' or carry :line",
          r.findings == [("F1", "P2"), ("F2", "P3")] and not r.unparsed and not r.malformed, r)
    r = errors.read_review("Verdict: fine.\nFinding: none\n")
    check("Finding: none is a parsed review of zero findings", r.findings == [] and not r.unparsed and not r.malformed, r)
    J1, J2 = "Judgement: F1 | not-real | the caller does check it", "Judgement: F2 | real | confirmed | by a run"
    r = errors.read_review("Finding: none\n" + J1 + "\n" + J2 + "\n")
    check("judgements by label and verdict, a reason may hold '|'",
          r.judgements == [("F1", "not-real", "the caller does check it"), ("F2", "real", "confirmed | by a run")] and not r.unparsed, r)
    r = errors.read_review(J1 + "\n- P2 the lock is wrong\nfix it\n")
    check("Judgement: lines with no Finding: line leave the report unparsed, named: its own findings are unknown, never zero",
          r.unparsed and r.findings == [] and r.judgements == [] and len(r.malformed) == 1 and "no Finding: line" in r.malformed[0], r)
    r = errors.read_review("Finding: none\nJudgement: F1 | fixed | done\nJudgement: F2 | not-fixed | still there\nJudgement: F3 | partly | one of two\n")
    check("an adjudication that says Finding: none is parsed, and the verdicts fixed, not-fixed and partly are kept",
          not r.unparsed and r.judgements == [("F1", "fixed", "done"), ("F2", "not-fixed", "still there"), ("F3", "partly", "one of two")], r)
    r = errors.read_review("**F9 (P1, x)** old shape in prose\nP2 the lock is wrong\nFinding: none\n")
    check("a report with machine lines is judged by them only: prose findings in an older shape are not read",
          r.findings == [] and not r.unparsed, r)
    r = errors.read_review("P1: none\nP2: none\nFinding: F3 | P1 | likely | a.py | x\n")
    check("…and prose saying none does not hide a machine finding", r.findings == [("F3", "P1")] and not r.unparsed, r)
    for bad in ("Finding: F1 | P4 | certain | a.py | x", "Finding: F1 | P2 | sure | a.py | x", "Finding: F1 | P2 | certain | a.py",
                "Finding: 1 | P2 | certain | a.py | x", "Finding: F1 | P2 | certain | a.py | ", "Finding: F1 | P2 | certain | has space.py | x",
                "Finding: F1 | P2 | certain |  | x", "Finding: nothing", "Finding:", "Judgement: F1 | maybe | x", "Judgement: F1 | real",
                "Judgement: one | real | x", "Judgement: F1 | real | "):
        r = errors.read_review(F2 + "\n" + bad + "\n")
        check(f"a malformed machine line makes the whole report unparsed, the line named, nothing counted: {bad!r}",
              r.unparsed and r.findings == [] and r.judgements == [] and len(r.malformed) == 1 and r.malformed[0].startswith(bad.split(":")[0]),
              r)
    for bad in (F1 + "\n" + F1.replace("P2", "P3"), "Finding: none\n" + F1, "Finding: none\nFinding: none", "Finding: none\n" + J1 + "\n" + J1.replace("not-real", "real")):
        r = errors.read_review(bad + "\n")
        check(f"a repeated label, or none beside a finding, is malformed: {bad[:34]!r}", r.unparsed and r.findings == [] and r.malformed, r)
    r = errors.read_review("Finding: F1 | P9 | certain | a.py | " + "y" * 400 + "\n")
    check("a malformed line is named at a bounded length", len(r.malformed) == 1 and len(r.malformed[0]) <= errors.NAMED_LINE_CHARS + 3
          and r.malformed[0].startswith("Finding: F1 | P9"), r)
    long = "Finding: F1 | P2 | certain | a.py | " + "y" * 200
    r = errors.read_review(long + "\n" + long + "\n")
    check("a repeated label on a long line is named with its reason, cut before the reason is added",
          len(r.malformed) == 1 and r.malformed[0].endswith("...   (repeated label)") and len(r.malformed[0]) <= errors.NAMED_LINE_CHARS + 25, r)
    r = errors.read_review(F1 + "\r\n" + F1 + "\r\n")
    check("a CRLF body names a repeated label without a bare carriage return in it",
          r.unparsed and len(r.malformed) == 1 and "\r" not in r.malformed[0] and r.malformed[0].endswith("(repeated label)"), r)
    r = errors.read_review("Finding: x\n" * 50)
    check("a report names at most MAX_NAMED malformed lines and counts the rest",
          r.unparsed and len(r.malformed) == errors.MAX_NAMED + 1 and r.malformed[-1] == f"(+{50 - errors.MAX_NAMED} more malformed lines)", r)
    r = errors.read_review("Finding: x\n" * errors.MAX_NAMED)
    check("…and names them all, with no count line, at the bound (positive control)",
          len(r.malformed) == errors.MAX_NAMED and not r.malformed[-1].startswith("(+"), r)
    r = errors.read_review(F1 + "\n" + J1 + "\nJudgement: F2 | maybe | x\n")
    check("a malformed line leaves no judgement counted, as no finding", r.unparsed and r.findings == [] and r.judgements == [], r)
    for indented in ("  Finding: F1 | P2 | certain | a.py | indented, so not at the start of a line\n", "\tFinding: none\n P2: none\n"):
        r = errors.read_review(indented)
        check(f"a line that does not start with Finding: is no machine line: the older parse decides: {indented[:18]!r}",
              r.findings == [] and not r.malformed and r.unparsed == ("P2" in indented and "none" not in indented), r)
    r = errors.read_review("  Judgement: F1 | not-real | indented\nFinding: none\n")
    check("…nor does one that does not start with Judgement:", r.judgements == [] and not r.unparsed, r)
    for old, want in (("**F1 (P2, x)** a\n**F2 (P3, y)** b\n", ([("F1", "P2"), ("F2", "P3")], False)),
                      ("P1: none\nP2: none\nP3: no findings", ([], False)),
                      ("- P2 the lock is wrong\nfix it", ([], True)),
                      ("No findings reported.", ([], False))):
        r = errors.read_review(old)
        check(f"a report in an older shape reads exactly as before: {old[:24]!r}",
              (r.findings, r.unparsed) == want == errors.parse_review(old) and r.judgements == [] and r.malformed == [], r)

    cs2 = [commit("c1"), commit("c2", "review fix", "Answers: F1", parents=("c1",)), commit("c3", parents=("c2",))]
    mbody = F1 + "\n" + F2 + "\n" + J1 + "\n" + J2 + "\n"
    evs = run(pr(commits=cs2, reviews=[review(mbody, "c1"), review("Finding: F1 | P9 | certain | a | x\n", "c3"),
                                       review(J2 + "\n", "c3"), review("**F1 (P1, y)** old\n", "c3")]))
    revs = [e for e in evs if e["kind"] == "review"]
    check("events: a machine finding is answered by an Answers: commit after the review, as an older one is",
          revs[0]["findings"] == [{"level": "P2", "answered": True}, {"level": "P3", "answered": False}] and not revs[0]["unparsed"], revs[0])
    check("events: the review carries its judgements and its malformed lines",
          revs[0]["judgements"][0] == {"label": "F1", "verdict": "not-real", "reason": "the caller does check it"}
          and revs[1]["unparsed"] and revs[1]["malformed"] == ["Finding: F1 | P9 | certain | a | x"], revs[:2])
    t = errors.tally(evs)["reviews"]
    check("tally: judgements per verdict, in verdict order; the malformed lines named with their PR; unparsed counted apart",
          t["judgements"] == {"not-real": 1, "real": 1} and t["unparsed"] == 2 and t["given"] == 4
          and [m["line"] for m in t["malformed_lines"]] == ["Finding: F1 | P9 | certain | a | x",
                                                            "Judgement: lines   (no Finding: line: a report says `Finding: none` when it has none)"]
          and all(m["repo"] == "o/r" and m["pr"] == 7 for m in t["malformed_lines"]), t)
    many = "".join(f"Finding: bad{i}\n" for i in range(errors.MAX_NAMED + 2))
    t2 = errors.tally(run(pr(commits=cs2, reviews=[review(many, "c1"), review("Finding: Z | zzz\n", "c3")])))["reviews"]
    check("tally: a report's named lines stay in order with its (+k more) entry last, not sorted by their text",
          [m["line"] for m in t2["malformed_lines"]] == [f"Finding: bad{i}" for i in range(errors.MAX_NAMED)]
          + ["(+2 more malformed lines)", "Finding: Z | zzz"], t2["malformed_lines"])
    check("tally: the unparsed report's findings are not counted; the old-shape report in the same PR still is",
          t["findings_total"] == 3 and t["findings"] == {"P1": {"answered": 0, "unjudged": 1}, "P2": {"answered": 1, "unjudged": 0},
                                                         "P3": {"answered": 0, "unjudged": 1}}, t)
    txt = errors.render(errors.report(evs), {"days": 30, "window": 14, "closed_period": ["2026-09-01", "2026-10-01"]})
    check("render names the unparsed machine line with its PR", "unparsed, named: o/r#7: Finding: F1 | P9 | certain | a | x" in txt, txt)

    ev = [e for e in run(pr(), runs={"c1": [cr("static", "failure", "2026-10-01T01:00:00Z"), cr("static", "success", "2026-10-01T02:00:00Z"),
                                            cr("static", "failure", "2026-10-01T03:00:00Z")]}) if e["kind"] == "head"]
    check("red, green, red on one sha is red, not flaky", ev[0]["red"] == ["static"] and ev[0]["flaky"] == [], ev)
    check("needed_jobs: a block list of three keeps all three; a comment on a name is unknown",
          errors.needed_jobs("jobs:\n  a:\n    x: 1\n  b:\n    x: 1\n  c:\n    x: 1\n  z-ok:\n    needs:\n      - a\n      - b\n      - c\n", {"z-ok"}) == {"a", "b", "c"}
          and errors.needed_jobs("jobs:\n  a:\n    x: 1\n  b:\n    x: 1\n  z-ok:\n    needs:\n      - a\n      # b is slow\n\n      - b\n", {"z-ok"}) == {"a", "b"}
          and errors.needed_jobs("jobs:\n  a:\n    name: Alpha # the a job\n  z-ok:\n    needs: [a]\n", {"z-ok"}) is None, "")

    # --- the period: the default 7 days with a 14-day window still has a denominator for reverts and fixes
    def at(days_ago):
        return (NOW - dt.timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    def when(days_ago, subject, body=""):
        return {"sha": "f" * 40, "subject": subject, "body": body, "when": NOW - dt.timedelta(days=days_ago)}
    prs_ = [pr(number=100 + i, merged=at(15 + i)) for i in range(5)] + [pr(number=200, merged=at(3))]
    evs = []
    for p_ in prs_:
        evs += errors.events_of("o/r", p_, [when(10, "review fix #100 F1: x", "Answers: F1"), when(1, "fix #200 F1", "Answers: F1")],
                                lambda r, s: [], NOW, 7, 14, HOSTS, NEEDED)
    t = errors.tally(evs)
    check("default period: the 5 PRs merged 15-19 days ago are the closed-window denominator, the PR of 3 days ago is the period",
          t["prs_merged"] == 1 and t["prs_in_closed_period"] == 5 and t["fixes"]["of_prs_with_closed_window"] == 5
          and t["fixes"]["count"] == 1 and t["fixes"]["rate"] == 0.2 and t["fixes"]["found_so_far_in_open_windows"] == 1, t)
    old_pr = pr(number=300, merged=at(16), reviews=[review("**F1 (P2, x)** a", "c1")])
    t = errors.tally(errors.events_of("o/r", old_pr, [], lambda r, s: [cr("static", "failure")], NOW, 7, 14, HOSTS, NEEDED))
    check("a PR of the closed-window period alone gives reverts and fixes a denominator and no review or head",
          t["prs_merged"] == 0 and t["prs_in_closed_period"] == 1 and t["reviews"]["given"] == 0 and t["red_checks"]["heads"] == 0, t)
    ten = pr(merged=at(10), commits=[commit("a" * 40), commit("b" * 40, parents=("a" * 40,))])
    ev = errors.events_of("o/r", ten, [when(5, "Revert", "This reverts commit " + "a" * 40 + ".")], lambda r, s: [], NOW, 7, 14, HOSTS, NEEDED)
    check("positive control: the same PR in the closed period does give the revert",
          [e["kind"] for e in errors.events_of("o/r", dict(ten, mergedAt=at(16)), [when(10, "Revert", "This reverts commit " + "a" * 40 + ".")],
                                                lambda r, s: [], NOW, 7, 14, HOSTS, NEEDED) if e["kind"] in ("pr", "revert")] == ["pr", "revert"])
    check("a PR between the period and the closed period (10 days ago, defaults) gives no event, so no empty actor row", ev == [], ev)
    two = pr(number=400, merged=at(16), commits=[commit("a" * 40), commit("b" * 40, parents=("a" * 40,))])
    ev = errors.events_of("o/r", two, [when(10, "Revert", "This reverts commit " + "a" * 40 + ".\n\nThis reverts commit " + "b" * 40 + ".")],
                          lambda r, s: [], NOW, 7, 14, HOSTS, NEEDED)
    t = errors.tally(ev)
    check("two reverted commits of one PR are one revert of that PR: the count never exceeds its denominator",
          t["reverts"]["count"] == 1 and t["reverts"]["of_prs_with_closed_window"] == 1, t["reverts"])
    fx = errors.events_of("o/r", pr(number=500, merged=at(16)), [when(10, "review fix #500 F1", "Answers: F1"), when(9, "review fix #500 F2", "Answers: F2")],
                          lambda r, s: [], NOW, 7, 14, HOSTS, NEEDED)
    t = errors.tally(fx)
    check("two fix commits naming one PR are one PR fixed forward", t["fixes"]["count"] == 1 and t["fixes"]["of_prs_with_closed_window"] == 1, t["fixes"])
    t = errors.tally(errors.events_of("o/r", pr(number=502, merged=at(3)), [when(2, "fix #502 F1", "Answers: F1"), when(1, "fix #502 F2", "Answers: F2")],
                                      lambda r, s: [], NOW, 7, 14, HOSTS, NEEDED))
    check("two fixes in an open window are one PR found so far", t["fixes"]["found_so_far_in_open_windows"] == 1, t["fixes"])
    mixed = pr(number=501, merged=at(16), commits=[commit("a" * 40, role="x"), commit("b" * 40, parents=("a" * 40,), role="")])
    t = errors.tally(errors.events_of("o/r", mixed, [when(10, "Revert", "This reverts commit " + "a" * 40 + ".\n\nThis reverts commit " + "b" * 40 + ".")],
                                      lambda r, s: [], NOW, 7, 14, HOSTS, NEEDED))
    check("reverted commits of two classes in one PR are still one PR reverted", t["reverts"]["count"] == 1, t["reverts"])
    check("an inline comment on needs: makes the workflow unknown, not a superset",
          errors.needed_jobs("jobs:\n  a:\n    x: 1\n  b:\n    x: 1\n  z-ok:\n    needs: [a] # b\n", {"z-ok"}) is None, "")
    rvs = [review("**F1 (P2, x)** a\n**F2 (P3, y)** b", "c1")] + [review("- P2 the lock is wrong", "c1")] * 4
    t = errors.tally(errors.events_of("o/r", pr(reviews=rvs), [], lambda r, s: [], NOW, 30, 14, HOSTS, NEEDED))
    check("findings per review leaves the unparsed reviews out of its denominator (5 reviews, 4 unparsed: no rate under 5)",
          t["reviews"]["given"] == 5 and t["reviews"]["unparsed"] == 4 and t["reviews"]["findings_per_review"] is None, t["reviews"])
    orphan = dict(pr(number=600, merged=at(16)), headRefOid="d" * 40)
    t = errors.report(errors.events_of("o/r", orphan, [when(10, "review fix #600 F1", "Answers: F1")], lambda r, s: [], NOW, 7, 14, HOSTS, NEEDED))["total"]
    check("a head commit not among the commits read: the fix forward is still beside its row's denominator",
          t["by_class"]["person"]["fixes"]["count"] == 1 and t["by_class"]["person"]["fixes"]["of_prs_with_closed_window"] == 1, t["by_class"])
    check("PRs outside both spans are not read at all", errors.events_of("o/r", pr(merged=at(40)), [], lambda r, s: [], NOW, 7, 14, HOSTS, NEEDED) == [])

    # --- merged_prs keeps the REST subject whole beside gh's cut headline
    saved = (errors.results.gh.pr_list, errors.results.gh.pr_view, errors.results.gh.api)
    errors.results.gh.pr_list = lambda *a, **k: [{"number": 7}]
    errors.results.gh.pr_view = lambda *a, **k: {"number": 7, "mergedAt": "2026-10-01T10:00:00Z",
                                                  "commits": [{"oid": "m1", "messageHeadline": "Merge branch 'x/\u2026"}, {"oid": "c9"}]}
    errors.results.gh.api = lambda *a, **k: [{"sha": "m1", "parents": [{"sha": "p1"}, {"sha": "p2"}],
                                              "commit": {"message": "Merge branch 'x/y/for/z/w' into v\n\nbody"}},
                                             {"sha": "c9", "parents": [{"sha": "m1"}], "commit": {"message": "plain"}}]
    try:
        got = errors.results.merged_prs("o/r", dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc), ("headRefName",))
    finally:
        errors.results.gh.pr_list, errors.results.gh.pr_view, errors.results.gh.api = saved
    c0, c1 = got[0]["commits"]
    check("merged_prs: the whole first line of the REST message, the parents as shas and as a count",
          c0["subject"] == "Merge branch 'x/y/for/z/w' into v" and c0["parentShas"] == ["p1", "p2"] and c0["parents"] == 2
          and c1["subject"] == "plain", got)

    # --- GitHub's commit list of a PR ends at 250: a PR that long, or one whose commits the list lacks, is cut
    saved = (errors.results.gh.pr_list, errors.results.gh.pr_view, errors.results.gh.api)
    def read_with(rest_rows, gh_commits):
        errors.results.gh.pr_list = lambda *a, **k: [{"number": 7}]
        errors.results.gh.pr_view = lambda *a, **k: {"number": 7, "mergedAt": "2026-10-01T10:00:00Z",
                                                      "commits": [{"oid": o} for o in gh_commits]}
        errors.results.gh.api = lambda *a, **k: rest_rows
        return errors.results.merged_prs("o/r", dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc))[0]
    row = lambda i: {"sha": f"s{i}", "parents": [{"sha": f"s{i - 1}"}], "commit": {"message": "x"}}  # noqa: E731
    try:
        whole = read_with([row(i) for i in range(3)], ["s0", "s1", "s2"])
        at_cap = read_with([row(i) for i in range(errors.results.REST_COMMITS_CAP)], ["s0"])
        lacking = read_with([row(0)], ["s0", "s1"])
    finally:
        errors.results.gh.pr_list, errors.results.gh.pr_view, errors.results.gh.api = saved
    check("merged_prs: a whole list is not cut; 250 rows, or a commit the list lacks, is",
          not whole["cut"] and at_cap["cut"] and lacking["cut"], (whole["cut"], at_cap["cut"], lacking["cut"]))
    old_cut = errors.tally(errors.events_of("o/r", {**pr(merged="2026-09-20T10:00:00Z"), "cut": True}, [], lambda r, s_: [], NOW, 30, 14, HOSTS, NEEDED))
    check("a cut PR in the closed-window period alone is counted apart too: its reverts and fixes are partial",
          old_cut["prs_cut"] == 1, old_cut["prs_cut"])
    cut_pr = {**pr(), "cut": True}
    t = errors.tally(run(cut_pr))
    check("a cut PR is counted apart, and the report says its counts are partial",
          t["prs_cut"] == 1 and errors.tally(run(pr()))["prs_cut"] == 0
          and "READ IN PART" in errors.render(errors.report(run(cut_pr)), {"days": 30, "window": 14, "closed_period": ["2026-09-01", "2026-10-01"]}),
          t["prs_cut"])

    # --- check-run reads: a transient failure is retried, a refusal is not, and the last failure is raised
    calls = []
    def flaky_api(n_bad, transient):
        def api(path, **k):
            if "/actions/runs" in path:
                return [{"id": 99, "path": errors.WORKFLOW}, {"id": 98, "path": ".github/workflows/other.yml"}]
            calls.append(1)
            if len(calls) <= n_bad:
                raise errors.gh.GhError("gh api", "x", transient=transient)
            return [{"name": "static", "conclusion": "success", "completed_at": "2026-10-01T01:00:00Z", "id": 1,
                     "details_url": "https://github.com/o/r/actions/runs/99/job/5"},
                    {"name": "static", "conclusion": "failure", "id": 2, "details_url": "https://github.com/o/r/actions/runs/98/job/6"},
                    {"name": "static", "conclusion": "failure", "id": 3, "details_url": "https://example.test/ci/7"}]
        return api
    saved_api, saved_sleep = errors.gh.api, errors.time.sleep
    errors.time.sleep = lambda s: None
    try:
        errors.gh.api = flaky_api(2, True)
        got_runs = errors.check_runs("o/r", "s")
        ok = [(r["id"], r["workflow_path"]) for r in got_runs] == [(1, errors.WORKFLOW), (2, ".github/workflows/other.yml"), (3, None)] \
            and len(calls) == 3
        calls.clear()
        errors.gh.api = flaky_api(3, True)
        try:
            errors.check_runs("o/r", "s")
            third = False
        except errors.gh.GhError:
            third = len(calls) == 3
        calls.clear()
        errors.gh.api = flaky_api(1, False)
        try:
            errors.check_runs("o/r", "s")
            refused = False
        except errors.gh.GhError:
            refused = len(calls) == 1
    finally:
        errors.gh.api, errors.time.sleep = saved_api, saved_sleep
    check("a transient read failure is retried twice, then raised", ok and third, (ok, third))
    check("a refusal is raised at once, not retried", refused)

    # --- a same-named job of another workflow, or of none the reader can name, is not the needed job
    ev = [e for e in run(pr(), runs={"c1": [cr("static", "failure", workflow=".github/workflows/other.yml"), cr("lint", "failure", workflow=None)],
                                     "c2": [cr("static", "failure")]}) if e["kind"] == "head"]
    check("red checks are matched by workflow and job: only the aggregate's workflow counts",
          len(ev) == 1 and ev[0]["red"] == ["static"], ev)
    check("…and a head whose only red run is another workflow's is not a head at all",
          not [e for e in run(pr(), runs={"c1": [cr("static", "failure", workflow=".github/workflows/other.yml")]}) if e["kind"] == "head"])

    # --- the workflow read: base64 from the contents API; a 404 is "no aggregate", any other failure is raised
    import base64
    saved_api = errors.gh.api
    try:
        errors.gh.api = lambda path, **k: {"encoding": "base64", "content": base64.b64encode(CI.encode()).decode()}
        got = errors.read_needed("o/r", AGG)
        def nf(path, **k):
            raise errors.gh.GhError("gh api", "Not Found", status=404)
        errors.gh.api = nf
        none = errors.read_needed("o/r", AGG)
        def boom(path, **k):
            raise errors.gh.GhError("gh api", "Server", status=502, transient=True)
        errors.gh.api = boom
        try:
            errors.read_needed("o/r", AGG)
            raised = False
        except errors.gh.GhError:
            raised = True
    finally:
        errors.gh.api = saved_api
    check("read_needed: the file's jobs; a 404 is unread (None); a 502 is raised, not read as 'none'",
          got == NEEDED and none is None and raised, (got, none, raised))

    # --- main(): text and JSON through stubbed readers
    saved = (errors.results.main_commits, errors.results.merged_prs, errors.gh.api, errors.known_hosts, errors.read_needed)
    errors.known_hosts = lambda: HOSTS
    errors.read_needed = lambda repo, agg: NEEDED
    sinces = []
    errors.results.main_commits = lambda repo, since: sinces.append(since) or []
    errors.results.merged_prs = lambda repo, since, extra=(): [pr(merged="2026-10-25T00:00:00Z")]
    errors.gh.api = lambda path, **k: ([{"id": 5, "path": errors.WORKFLOW}] if "/actions/runs" in path else
                                       [{**cr("static", "failure"), "details_url": "https://github.com/o/r/actions/runs/5/job/1"}])
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
        errors.results.main_commits, errors.results.merged_prs, errors.gh.api, errors.known_hosts, errors.read_needed = saved
    check("main --json: the red head counted, window open", rc == 0 and js["repositories_read"] == ["o/r"] and list(js["repos"]) == ["o/r"]
          and js["total"]["all"]["red_checks"]["heads_red"] == 2 and js["total"]["all"]["prs_in_closed_period"] == 0, js["total"]["all"])
    check("both PR and commit reads start DAYS+WINDOW days back, not DAYS",
          len(sinces) == 2 and all(dt.timedelta(days=43, hours=23) < dt.datetime.now(dt.timezone.utc) - x < dt.timedelta(days=44, hours=1)
                                   for x in sinces[:1]) and dt.timedelta(days=20, hours=23) < dt.datetime.now(dt.timezone.utc) - sinces[1] < dt.timedelta(days=21, hours=1), sinces)
    check("the text header dates the PRs that reverts and fixes are counted on", "whose windows have closed" in out.getvalue()
          and "counted on the PRs merged" in out.getvalue(), out.getvalue()[:400])
    check("main text says where judged-not-real is counted (json, per verdict, no text view) and shows no rate under 5", rc2 == 0
          and "judged-not-real findings: counted per verdict in --json (reviews.judgements), from `Judgement:` lines only; no text view yet" in out.getvalue()
          and "no rate (<5)" in out.getvalue(), out.getvalue())
    check("a bad --days is exit 2 and a line", rc3 == 2 and "at least 1" in err.getvalue(), err.getvalue())

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
