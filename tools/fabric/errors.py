#!/usr/bin/env python3
"""tools/fabric/errors.py — errors per actor and per kind, the same for people
and agents, read from artifacts only (agent-fabric ADR-061, Proposed: its
definitions are the contract here and change only by an amendment of it).

    fabric-errors [--days 7] [--window 14] [--repo OWNER/NAME]... [--all] [--json]

For the pull requests merged in the last DAYS days, per repository and in
total, per actor, per actor class (person or agent) and per role:

1. **review findings** by level, from marked reviews (the marker
   fabric-pr post-review writes) given on a commit of the PR, parsed from the
   `**F<n> (P<level>` shape. Per review given; each finding is *answered*
   (an `Answers:` commit of the PR, later in the PR than the reviewed commit,
   names its label) or *unjudged*. "Judged not real" has no parseable form
   yet and is not read. A marked review that mentions a level but whose
   findings do not parse is counted apart (`unparsed`), never as zero.
2. **red checks** per head pushed, by check name: a named check run that
   concluded failure or timed_out. A head is a commit of the PR on which a
   named check ran to a conclusion (checks run on push); never the aggregate
   the ruleset requires (`ci-ok`, which counts its dependencies again), never
   a cancelled run. A named check that failed and later succeeded on the same
   sha is *flaky*: the check's, counted apart and not the actor's.
3. **reverts** (git's own revert line naming a commit of the PR, as
   results.reverted_shas matches it) and **fixes forward** (a later commit
   the classifier calls a fix naming the PR) per PR merged, inside the window.
   Only a PR whose window has closed is in their denominator; what was found
   so far on a PR whose window is still open is reported apart.

ACTOR. The login in the head ref `<host>/<login>/...`, for a host the fabric
registry knows (so `dependabot/...` is not a login). A commit that arrived by
a fold of a `<host>/<login>/for/<caller>/<what>` branch (a merge commit's
"Merge branch '<that>'") is that branch's login: for the red heads and the
reverts, which are about a commit; findings and fixes forward are about the
PR and fall to the head ref's login. Anything else is "unattributed", with
its count. CLASS: *agent* when the commit carries a `Fabric-Role:` trailer
(the hooks stamp every commit an account makes, AGENTS.md), with the role from
it; *person* when it carries none. A login is not a class: the operator's own
login commits with and without a role.

EVERY count carries its denominator; below 5 denominators there is no rate.
No combined score, no ranking, no sort by count (ADR-061 §5 rule 6): actors
are listed in name order. Every number is information for the rules, never a
target. Input: GitHub only, through gh.py; never a transcript, a memory or a
message body.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import gh  # noqa: E402
import results  # noqa: E402
from github import commit_class  # noqa: E402
from github.post_review import REVIEW_MARKER  # noqa: E402

MIN_DENOMINATOR = 5                                  # ADR-061 §5 rule 4
RED = {"failure", "timed_out"}
FINDING = re.compile(r"\*\*F(\d+) \(P([123])\b")
LEVEL_LINE = re.compile(r"\bP[123]\b")
# A line that mentions a level to say there is none ("P1: none", "no P2").
NO_FINDING = re.compile(r"\bnone\b|\bno\b|\b0\b|\bnothing\b", re.I)
LABEL = re.compile(r"[A-Z]{1,2}-?[0-9]+(?:-[0-9]+)?")
FOLD = re.compile(r"^Merge (?:remote-tracking )?branch '(?:origin/)?([^'/\s]+)/([^'/\s]+)/for/[^'\s]+'")
UNATTRIBUTED = "unattributed"


def aggregate_checks() -> set[str]:
    """The contexts the ruleset requires: the aggregate job, which is never counted as a check of its own."""
    with open(os.path.join(ROOT, "tools", "fabric", "github-ruleset-main.json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    return {c["context"] for r in doc["rules"] if r["type"] == "required_status_checks"
            for c in r["parameters"]["required_status_checks"]}


def known_hosts() -> set[str]:
    with open(os.path.join(ROOT, "runtime", "hosts", "registry.json"), encoding="utf-8") as fh:
        return set(json.load(fh)["hosts"])


def head_actor(ref: str, hosts: set[str]) -> str:
    parts = ref.split("/")
    return parts[1] if len(parts) >= 3 and parts[0] in hosts and parts[1] else UNATTRIBUTED


def fold_logins(commits: list[dict], hosts: set[str]) -> dict[str, str]:
    """sha -> login of the `for/` branch it arrived by. A fold merge commit's second parent and what it brings
    that its first parent does not hold, inside this PR's commits; the first fold to claim a commit keeps it."""
    parents = {c["oid"]: c.get("parentShas") or [] for c in commits}

    def reach(start: str) -> set[str]:
        seen, todo = set(), [start]
        while todo:
            sha = todo.pop()
            if sha in parents and sha not in seen:
                seen.add(sha)
                todo += parents[sha]
        return seen

    out: dict[str, str] = {}
    for c in commits:
        m = FOLD.match(c.get("messageHeadline") or "")
        ps = parents.get(c["oid"], [])
        if not m or m.group(1) not in hosts or len(ps) < 2:
            continue
        base = reach(ps[0])
        for sha in reach(ps[1]) - base:
            out.setdefault(sha, m.group(2))
    return out


def role_of(commit: dict) -> tuple[str, str]:
    """(class, role) of one commit from its Fabric-Role trailer."""
    roles = commit_class.trailer_values(commit.get("messageBody") or "", "Fabric-Role")
    role = roles[-1] if roles else ""
    return ("agent", role) if role else ("person", "-")


def parse_review(body: str) -> tuple[list[tuple[str, str]], bool]:
    """((label, level) findings, unparsed): unparsed when no finding parsed yet a line names a level without
    saying there is none."""
    found: dict[str, str] = {}
    for m in FINDING.finditer(body):
        found.setdefault(f"F{m.group(1)}", f"P{m.group(2)}")
    unparsed = not found and any(LEVEL_LINE.search(l) and not NO_FINDING.search(l) for l in body.splitlines())
    return list(found.items()), unparsed


def check_verdict(runs: list[dict], aggregates: set[str]) -> tuple[bool, list[str], list[str]]:
    """(counted, red names, flaky names) for one sha's check runs."""
    by_name: dict[str, list[dict]] = {}
    for r in runs:
        if r.get("name") in aggregates or not r.get("conclusion") or r["conclusion"] == "cancelled":
            continue
        by_name.setdefault(r["name"], []).append(r)
    red, flaky = [], []
    for name, rs in sorted(by_name.items()):
        rs.sort(key=lambda r: (r.get("completed_at") or "", r.get("id") or 0))
        bad = [i for i, r in enumerate(rs) if r["conclusion"] in RED]
        if not bad:
            continue
        # Red then green on the same sha: the check flaked, the actor's head did not fail.
        (flaky if any(r["conclusion"] == "success" for r in rs[bad[0] + 1:]) else red).append(name)
    return bool(by_name), red, flaky


def events_of(repo: str, pr: dict, later: list[dict], checks, now: dt.datetime, window: int,
              hosts: set[str], aggregates: set[str]) -> list[dict]:
    """The error events of one merged PR. `checks(repo, sha)` gives a sha's check runs."""
    n = pr["number"]
    commits = pr.get("commits") or []
    by_sha = {c["oid"]: c for c in commits}
    owner = head_actor(pr.get("headRefName") or "", hosts)
    folds = fold_logins(commits, hosts)
    head = by_sha.get(pr["headRefOid"]) or {}
    pr_class, pr_role = role_of(head)

    def who(sha: str) -> dict:
        c = by_sha.get(sha) or {}
        cls, role = role_of(c) if c else (pr_class, pr_role)
        return {"actor": folds.get(sha, owner), "class": cls, "role": role}

    base = {"repo": repo, "pr": n, "actor": owner, "class": pr_class, "role": pr_role}
    merged = dt.datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00"))
    closed = now >= merged + dt.timedelta(days=window)
    ev = [{**base, "kind": "pr", "closed": closed}]

    order = [c["oid"] for c in commits]
    answers = [(i, set(LABEL.findall(commit_class.answers_of(c.get("messageBody") or ""))))
               for i, c in enumerate(commits)]
    for rv in pr.get("reviews") or []:
        if not (rv.get("body") or "").startswith(REVIEW_MARKER):
            continue
        sha = (rv.get("commit") or {}).get("oid")
        if sha not in by_sha:
            ev.append({**base, "kind": "review_elsewhere"})
            continue
        findings, unparsed = parse_review(rv["body"])
        at = order.index(sha)
        ev.append({**base, "kind": "review", "unparsed": unparsed,
                   "findings": [{"level": lvl, "answered": any(i > at and label in ls for i, ls in answers)}
                                for label, lvl in findings]})

    for c in commits:
        if c.get("parents", 1) > 1 and FOLD.match(c.get("messageHeadline") or ""):
            continue          # a fold merge is the integrator's commit, not a head anyone pushed to be tested
        counted, red, flaky = check_verdict(checks(repo, c["oid"]), aggregates)
        if counted:
            ev.append({**base, **who(c["oid"]), "kind": "head", "red": red, "flaky": flaky})

    inside = [c for c in later if merged < c["when"] <= merged + dt.timedelta(days=window)]
    own = set(by_sha) | {(pr.get("mergeCommit") or {}).get("oid")}
    for sha in sorted(results.reverted_shas(own, inside)):
        ev.append({**base, **who(sha), "kind": "revert", "closed": closed})
    for c in results.fixes_forward(n, inside, repo=repo):
        ev.append({**base, "kind": "fix", "closed": closed})
    return ev


def rate(count: int, denominator: int) -> float | None:
    return round(count / denominator, 2) if denominator >= MIN_DENOMINATOR else None


def tally(events: list[dict]) -> dict:
    """One group's counts, each beside its denominator."""
    prs = [e for e in events if e["kind"] == "pr"]
    closed = sum(1 for e in prs if e["closed"])
    reviews = [e for e in events if e["kind"] == "review"]
    findings: dict[str, dict] = {}
    for e in reviews:
        for f in e["findings"]:
            cell = findings.setdefault(f["level"], {"answered": 0, "unjudged": 0})
            cell["answered" if f["answered"] else "unjudged"] += 1
    nfind = sum(sum(v.values()) for v in findings.values())
    heads = [e for e in events if e["kind"] == "head"]
    red_by: dict[str, int] = {}
    flaky_by: dict[str, int] = {}
    for e in heads:
        for name in e["red"]:
            red_by[name] = red_by.get(name, 0) + 1
        for name in e["flaky"]:
            flaky_by[name] = flaky_by.get(name, 0) + 1
    red_heads = sum(1 for e in heads if e["red"])
    out = {}
    for kind, key in (("revert", "reverts"), ("fix", "fixes")):
        found = [e for e in events if e["kind"] == kind]
        n_closed = sum(1 for e in found if e["closed"])
        out[key] = {"count": n_closed, "of_prs_with_closed_window": closed, "rate": rate(n_closed, closed),
                           "found_so_far_in_open_windows": len(found) - n_closed}
    return {"prs_merged": len(prs), "prs_window_closed": closed,
            "reviews": {"given": len(reviews), "unparsed": sum(1 for e in reviews if e["unparsed"]),
                        "findings": {k: findings[k] for k in sorted(findings)}, "findings_total": nfind,
                        "findings_per_review": rate(nfind, len(reviews)),
                        "on_a_commit_not_in_the_pr": sum(1 for e in events if e["kind"] == "review_elsewhere")},
            "red_checks": {"heads": len(heads), "heads_red": red_heads, "rate": rate(red_heads, len(heads)),
                           "by_check": {k: red_by[k] for k in sorted(red_by)},
                           "flaky_not_the_actors": {k: flaky_by[k] for k in sorted(flaky_by)}},
            **out}


def report(events: list[dict]) -> dict:
    """Per repository and total; each by actor, by class and by role; names in order, never by count."""
    def groups(evs: list[dict]) -> dict:
        res = {"all": tally(evs)}
        for dim in ("actor", "class", "role"):
            res["by_" + dim] = {k: tally([e for e in evs if e[dim] == k]) for k in sorted({e[dim] for e in evs})}
        res["unattributed_prs"] = sum(1 for e in evs if e["kind"] == "pr" and e["actor"] == UNATTRIBUTED)
        return res
    repos = sorted({e["repo"] for e in events})
    return {"total": groups(events), "repos": {r: groups([e for e in events if e["repo"] == r]) for r in repos}}


def render(rep: dict, doc: dict) -> str:
    lines = [f"fabric-errors: PRs merged in the last {doc['days']} days (reverts and fixes: {doc['window']}-day window); "
             f"attribution: head ref, a fold's contributor; class: Fabric-Role trailer. "
             f"Counts for the rules, never a target, a ranking or a score (ADR-061, Proposed).",
             f"judged-not-real findings: not read (no parseable judgement); signature attribution: not read"]

    def line(name: str, t: dict) -> str:
        r, c = t["reviews"], t["red_checks"]
        fnd = ", ".join(f"{k} {v['answered']} answered/{v['unjudged']} unjudged" for k, v in r["findings"].items()) or "none"
        pct = lambda x: "no rate (<5)" if x is None else f"rate {x}"  # noqa: E731
        return (f"  {name}: PRs {t['prs_merged']} ({t['prs_window_closed']} windows closed); "
                f"findings in {r['given']} reviews ({r['unparsed']} unparsed): {fnd}; "
                f"red heads {c['heads_red']}/{c['heads']} {pct(c['rate'])}, by check {c['by_check'] or '-'}, flaky {c['flaky_not_the_actors'] or '-'}; "
                f"reverts {t['reverts']['count']}/{t['reverts']['of_prs_with_closed_window']} {pct(t['reverts']['rate'])} "
                f"(+{t['reverts']['found_so_far_in_open_windows']} in open windows); "
                f"fixes forward {t['fixes']['count']}/{t['fixes']['of_prs_with_closed_window']} {pct(t['fixes']['rate'])} "
                f"(+{t['fixes']['found_so_far_in_open_windows']} in open windows)")

    for title, g in [("total", rep["total"]), *[(r, g) for r, g in rep["repos"].items()]]:
        lines.append(f"{title}  (unattributed PRs: {g['unattributed_prs']})")
        lines.append(line("all", g["all"]))
        for dim in ("actor", "class", "role"):
            for k, t in g["by_" + dim].items():
                lines.append(line(f"{dim} {k}", t))
    return "\n".join(lines)


def collect(repos: list[str], now: dt.datetime, days: int, window: int) -> list[dict]:
    hosts, aggregates = known_hosts(), aggregate_checks()
    cache: dict[tuple[str, str], list[dict]] = {}

    def checks(repo: str, sha: str) -> list[dict]:
        # A sha never changes, so what GitHub says of it is asked once.
        if (repo, sha) not in cache:
            cache[repo, sha] = gh.api(f"repos/{repo}/commits/{sha}/check-runs?per_page=100", paginate=True,
                                      items_key="check_runs")
        return cache[repo, sha]

    since = now - dt.timedelta(days=days)
    events: list[dict] = []
    for repo in repos:
        later = results.main_commits(repo, since)
        for pr in results.merged_prs(repo, since, ("headRefName",)):
            events += events_of(repo, pr, later, checks, now, window, hosts, aggregates)
    return events


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=7, help="the period: PRs merged in the last DAYS days")
    ap.add_argument("--window", type=int, default=14, help="days after a merge in which a revert or a fix counts")
    ap.add_argument("--repo", action="append", help="owner/name; may repeat (default BlueTeam-OU/agent-fabric)")
    ap.add_argument("--all", action="store_true", help="every registered project")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.days < 1 or a.window < 1:
        print("fabric-errors: --days and --window are at least 1", file=sys.stderr)
        return 2
    now = dt.datetime.now(dt.timezone.utc)
    try:
        repos = results.registered_repos() if a.all else (a.repo or ["BlueTeam-OU/agent-fabric"])
        rep = report(collect(repos, now, a.days, a.window))
    except (gh.GhError, OSError, ValueError) as e:
        print(f"fabric-errors: {e}", file=sys.stderr)
        return 1
    doc = {"days": a.days, "window": a.window, "repositories_read": repos, "since": (now - dt.timedelta(days=a.days)).isoformat(),
           "attribution": "head ref; a fold's contributor", "judged_not_real": "not read", **rep}
    print(json.dumps(doc, indent=2) if a.json else render(rep, doc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
