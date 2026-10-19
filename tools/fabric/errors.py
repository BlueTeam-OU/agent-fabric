#!/usr/bin/env python3
"""tools/fabric/errors.py — errors per actor and per kind, the same for people
and agents, read from artifacts only (ADR-061, Proposed: its
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
   concluded failure or timed_out. The runs counted are the jobs the
   repository's required aggregate `needs` (ADR-061 §2, amended after #312's
   review: in agent-fabric the jobs `ci-ok` lists in .github/workflows/ci.yml
   on the default branch), a matrix job by its "name (legs)" runs; never the
   aggregate itself, which counts them again, never a cancelled run and never
   a run of another workflow (pr-counts, stripped-nightly): by the run's name
   only, so a check of another workflow that shares a needed job's name would
   be counted (none does in agent-fabric). A head is a
   commit of the PR on which such a run ran to a conclusion (checks run on
   push). A repository with no such aggregate is not read for red checks, and
   says so. A named check that failed and whose last run on the same
   sha passed is *flaky*: the check's, counted apart and not the actor's.
3. **reverts** (git's own revert line naming a commit of the PR, as
   results.reverted_shas matches it) and **fixes forward** (a later commit
   the classifier calls a fix naming the PR) per PR merged, inside the window.
   Their denominator is the PRs merged in the DAYS that end WINDOW days ago
   (windows closed: a period shorter than the window holds none); what was
   found so far on a PR of the period whose window is still open is apart.

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

A revert's row is the actor, class and role of the commit that was reverted (a
fold's contributor; a commit with or without a role; a revert of the merge commit
is the head ref's login with the head commit's class and role), so the
denominator of the reverts and fixes forward of a row is the PRs of the
closed-window period in which that row had a commit or which it owns, never
only the PRs it owns: its count is always
drawn from its denominator, and a rate cannot exceed 1.

EVERY count carries its denominator; below 5 denominators there is no rate.
No combined score, no ranking, no sort by count (ADR-061 §5 rule 6): actors
are listed in name order. Every number is information for the rules, never a
target. Input: GitHub only, through gh.py; never a transcript, a memory or a
message body.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import datetime as dt
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import gh  # noqa: E402
import results  # noqa: E402
import roots  # noqa: E402
from github import commit_class  # noqa: E402
from github.post_review import REVIEW_MARKER  # noqa: E402

MIN_DENOMINATOR = 5                                  # ADR-061 §5 rule 4
RED = {"failure", "timed_out"}
FINDING = re.compile(r"\*\*F(\d+) \(P([123])\b")
LEVEL_LINE = re.compile(r"\bP[123]\b")
# A clause that only says a level is empty ("P1: none", "None at P1, P2 or P3.", "No findings (P1, P2, P3 empty)"):
# once the level tokens are taken out, every word left is one of these. A clause with any other word in it
# ("P2: none of the callers check the result", "returns no error") is a finding in another shape, not an absence.
ABSENCE_WORDS = {"none", "no", "nothing", "finding", "findings", "empty", "0", "at", "or", "and"}
# "P2 findings:" names a level and states nothing; an absence needs a word that denies.
NEGATIONS = {"none", "no", "nothing", "empty", "0"}
CLAUSE = re.compile(r"[.;\n]")
LABEL = re.compile(r"[A-Z]{1,2}-?[0-9]+(?:-[0-9]+)?")
FOLD = re.compile(r"^Merge (?:remote-tracking )?branch '(?:origin/)?([^'/\s]+)/([^'/\s]+)/for/[^'\s]+'")
UNATTRIBUTED = "unattributed"


def aggregate_checks() -> set[str]:
    """The contexts the ruleset requires: the aggregate job, which is never counted as a check of its own."""
    with open(os.path.join(ROOT, "tools", "fabric", "github-ruleset-main.json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    return {c["context"] for r in doc["rules"] if r["type"] == "required_status_checks"
            for c in r["parameters"]["required_status_checks"]}


WORKFLOW = ".github/workflows/ci.yml"


def needed_jobs(workflow: str, aggregates: set[str]) -> set[str] | None:
    """The check-run names the aggregate job `needs`, from the workflow text: each needed job's `name:` (else its
    id), which a matrix job's runs extend as "<name> (<legs>)". None when the workflow has no aggregate of the
    ruleset's name or a needed name cannot be read (an expression): unknown, never guessed from the runs seen."""
    jobs: dict[str, list[str]] = {}
    current = None
    in_jobs = False
    for line in workflow.splitlines():
        if re.fullmatch(r"jobs:\s*", line):
            in_jobs = True
        elif in_jobs and re.match(r"^\S", line):
            in_jobs = False
        m = re.fullmatch(r"  ([A-Za-z0-9_-]+):\s*", line) if in_jobs else None
        if m:
            current = m.group(1)
            jobs[current] = []
        elif current:
            jobs[current].append(line)
    agg = next((j for j in jobs if j in aggregates), None)
    if agg is None:
        return None
    body = "\n".join(l for l in jobs[agg] if l.strip() and not l.lstrip().startswith("#"))
    m = re.search(r"^    needs:[ \t]*(\[[^\]]*\]|(?:\n      - .*)+|\S.*)$", body, re.M)
    if not m or "#" in m.group(1):      # a trailing comment would add its words as job names
        return None
    needed = re.findall(r"[A-Za-z0-9_][A-Za-z0-9_-]*", m.group(1).replace("needs:", ""))
    names = set()
    for j in needed:
        if j not in jobs:
            return None
        nm = next((re.fullmatch(r"    name:\s*(.+?)\s*", l) for l in jobs[j] if re.match(r"^    name:", l)), None)
        name = nm.group(1).strip("'\"") if nm else j
        if "${{" in name or " #" in name:     # an expression or a trailing comment: the check name is not readable here
            return None
        names.add(name)
    return names


def counted_run(name: str, needed: set[str]) -> bool:
    return any(name == n or name.startswith(n + " (") for n in needed)


def known_hosts() -> set[str]:
    with open(roots.hosts_registry(engine=roots.code_root()), encoding="utf-8") as fh:
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
        m = FOLD.match(c.get("subject") or c.get("messageHeadline") or "")
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


def words_of(clause: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[A-Za-z0-9]+", LEVEL_LINE.sub(" ", clause))]


def absence(clause: str) -> bool:
    words = words_of(clause)
    return bool(words) and all(w in ABSENCE_WORDS for w in words) and any(w in NEGATIONS for w in words)


def is_heading(clause: str) -> bool:
    return bool(re.match(r"\s*(#|\*\*)", clause)) or clause.rstrip().endswith(":")


def level_unparsed(clauses: list[str], i: int) -> bool:
    """Whether the level clause at `i` leaves what the review says unknown. A level with no other word is a heading
    and says what its next clause says; a heading that denies findings ("## No P1 findings") speaks for its whole
    section, so a clause of the section that is not itself a denial is a finding it would hide."""
    clause = clauses[i]
    if not words_of(clause):
        nxt = clauses[i + 1] if i + 1 < len(clauses) else ""
        return not absence(nxt) or bool(LEVEL_LINE.search(nxt))
    if not absence(clause):
        return True
    if not is_heading(clause):
        return False
    for later in clauses[i + 1:]:
        if LEVEL_LINE.search(later) or later.startswith("#"):
            break
        if not absence(later):
            return True
    return False


def parse_review(body: str) -> tuple[list[tuple[str, str]], bool]:
    """((label, level) findings, unparsed): unparsed when no finding parsed yet a line names a level without
    saying there is none."""
    found: dict[str, str] = {}
    for m in FINDING.finditer(body):
        found.setdefault(f"F{m.group(1)}", f"P{m.group(2)}")
    clauses = [c.strip() for c in CLAUSE.split(body) if c.strip()]
    unparsed = not found and any(LEVEL_LINE.search(c) and level_unparsed(clauses, i) for i, c in enumerate(clauses))
    return list(found.items()), unparsed


def check_verdict(runs: list[dict], needed: set[str]) -> tuple[bool, list[str], list[str]]:
    """(counted, red names, flaky names) for one sha's check runs of the needed jobs."""
    by_name: dict[str, list[dict]] = {}
    for r in runs:
        if not counted_run(r.get("name") or "", needed) or not r.get("conclusion") or r["conclusion"] == "cancelled":
            continue
        by_name.setdefault(r["name"], []).append(r)
    red, flaky = [], []
    for name, rs in sorted(by_name.items()):
        rs.sort(key=lambda r: (r.get("completed_at") or "", r.get("id") or 0))
        if not any(r["conclusion"] in RED for r in rs):
            continue
        # Red and the sha's last run green: the check flaked, the actor's head did not fail. Red, green, red is red.
        (flaky if rs[-1]["conclusion"] == "success" else red).append(name)
    return bool(by_name), red, flaky


def merged_at(pr: dict) -> dt.datetime:
    return dt.datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00"))


def in_period(pr: dict, now: dt.datetime, days: int) -> bool:
    return merged_at(pr) >= now - dt.timedelta(days=days)


def in_closed_period(pr: dict, now: dt.datetime, days: int, window: int) -> bool:
    """Merged in the DAYS that end WINDOW days ago: the PRs whose windows have closed, which a period shorter than
    the window can never hold (a PR merged in the last 7 days has 7 more days to be reverted)."""
    return now - dt.timedelta(days=days + window) <= merged_at(pr) <= now - dt.timedelta(days=window)


def events_of(repo: str, pr: dict, later: list[dict], checks, now: dt.datetime, days: int, window: int,
              hosts: set[str], needed: set[str] | None) -> list[dict]:
    """The error events of one merged PR. `checks(repo, sha)` gives a sha's check runs; `needed` the check-run
    names of the repository's aggregate's dependencies, None when unknown (no head is then counted)."""
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
    merged = merged_at(pr)
    closed = now >= merged + dt.timedelta(days=window)
    period, cperiod = in_period(pr, now, days), in_closed_period(pr, now, days, window)
    base = {**base, "period": period, "cperiod": cperiod}
    if not (period or cperiod):
        return []
    ev = [{**base, "kind": "pr", "closed": closed}]
    # Every row that had a commit in this PR is in the denominator of its reverts and fixes forward, and so is the
    # head ref's own row: fixes forward and a revert of the merge commit are attributed to it even when the head
    # commit is not among the commits read (then its class and role are "person" and "-"), and a count must
    # never stand in a row whose denominator lacks the PR.
    rows = {(owner, pr_class, pr_role)} | {(w["actor"], w["class"], w["role"]) for w in (who(c["oid"]) for c in commits)}
    ev += [{**base, "actor": a_, "class": c_, "role": r_, "kind": "pr_part", "closed": closed} for a_, c_, r_ in sorted(rows)]
    if not period:
        # Only reverts and fixes forward are read for a PR that is in the closed period alone.
        return ev + reverts_and_fixes(pr, later, merged, window, closed, base, who, by_sha)

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

    if needed is None:
        ev.append({**base, "kind": "checks_unread"})
    for c in commits if needed is not None else ():
        counted, red, flaky = check_verdict(checks(repo, c["oid"]), needed)
        if counted:
            ev.append({**base, **who(c["oid"]), "kind": "head", "red": red, "flaky": flaky})

    return ev + reverts_and_fixes(pr, later, merged, window, closed, base, who, by_sha)


def reverts_and_fixes(pr: dict, later: list[dict], merged: dt.datetime, window: int, closed: bool, base: dict,
                      who, by_sha: dict) -> list[dict]:
    inside = [c for c in later if merged < c["when"] <= merged + dt.timedelta(days=window)]
    own = set(by_sha) | {(pr.get("mergeCommit") or {}).get("oid")}
    # A revert is counted per PR (and per actor, when a fold's contributor and the integrator both had commits
    # reverted), not per commit: the denominator is PRs merged.
    reverted = {(w["actor"], w["class"], w["role"]): w for w in (who(sha) for sha in sorted(results.reverted_shas(own, inside)))}
    ev = [{**base, **w, "kind": "revert", "closed": closed} for w in reverted.values()]
    return ev + [{**base, "kind": "fix", "closed": closed} for _ in results.fixes_forward(pr["number"], inside, repo=base["repo"])]


def rate(count: int, denominator: int) -> float | None:
    return round(count / denominator, 2) if denominator >= MIN_DENOMINATOR else None


def tally(events: list[dict]) -> dict:
    """One group's counts, each beside its denominator."""
    prs = [e for e in events if e["kind"] == "pr" and e["period"]]
    closed = len({(e["repo"], e["pr"]) for e in events if e["kind"] == "pr_part" and e["cperiod"]})
    closed_owned = sum(1 for e in events if e["kind"] == "pr" and e["cperiod"])
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
        # PRs, not events: two reverted commits or two fix commits of one PR are one PR reverted or fixed.
        n_closed = len({(e["repo"], e["pr"]) for e in found if e["cperiod"]})
        out[key] = {"count": n_closed, "of_prs_with_closed_window": closed, "rate": rate(n_closed, closed),
                    "found_so_far_in_open_windows": len({(e["repo"], e["pr"]) for e in found if e["period"] and not e["closed"]})}
    return {"prs_merged": len(prs), "prs_in_closed_period": closed_owned,
            "reviews": {"given": len(reviews), "unparsed": sum(1 for e in reviews if e["unparsed"]),
                        "findings": {k: findings[k] for k in sorted(findings)}, "findings_total": nfind,
                        "findings_per_review": rate(nfind, len(reviews) - sum(1 for e in reviews if e["unparsed"])),
                        "on_a_commit_not_in_the_pr": sum(1 for e in events if e["kind"] == "review_elsewhere")},
            "red_checks": {"unread_no_aggregate": sum(1 for e in events if e["kind"] == "checks_unread"),
                           "heads": len(heads), "heads_red": red_heads, "rate": rate(red_heads, len(heads)),
                           "by_check": {k: red_by[k] for k in sorted(red_by)},
                           "flaky_not_the_actors": {k: flaky_by[k] for k in sorted(flaky_by)}},
            **out}


def report(events: list[dict]) -> dict:
    """Per repository and total; each by actor, by class and by role; names in order, never by count."""
    def groups(evs: list[dict]) -> dict:
        res = {"all": tally(evs)}
        for dim in ("actor", "class", "role"):
            res["by_" + dim] = {k: tally([e for e in evs if e[dim] == k]) for k in sorted({e[dim] for e in evs})}
        res["unattributed_prs"] = sum(1 for e in evs if e["kind"] == "pr" and e["period"] and e["actor"] == UNATTRIBUTED)
        return res
    repos = sorted({e["repo"] for e in events})
    return {"total": groups(events), "repos": {r: groups([e for e in events if e["repo"] == r]) for r in repos}}


def render(rep: dict, doc: dict) -> str:
    lines = [f"fabric-errors: PRs merged in the last {doc['days']} days (reverts and fixes: {doc['window']}-day window, counted on the PRs merged {doc['closed_period'][0][:10]}..{doc['closed_period'][1][:10]}, whose windows have closed); "
             f"attribution: head ref, a fold's contributor; class: Fabric-Role trailer. "
             f"Counts for the rules, never a target, a ranking or a score (ADR-061, Proposed).",
             f"judged-not-real findings: not read (no parseable judgement); signature attribution: not read"]

    def line(name: str, t: dict) -> str:
        r, c = t["reviews"], t["red_checks"]
        fnd = ", ".join(f"{k} {v['answered']} answered/{v['unjudged']} unjudged" for k, v in r["findings"].items()) or "none"
        pct = lambda x: "no rate (<5)" if x is None else f"rate {x}"  # noqa: E731
        return (f"  {name}: PRs {t['prs_merged']} ({t['prs_in_closed_period']} in the closed-window period); "
                f"findings in {r['given']} reviews ({r['unparsed']} unparsed): {fnd}; "
                f"red heads {c['heads_red']}/{c['heads']} {pct(c['rate'])}, by check {c['by_check'] or '-'}, flaky {c['flaky_not_the_actors'] or '-'}"
                f"{'; red checks NOT READ for %d PRs (no aggregate in %s)' % (c['unread_no_aggregate'], WORKFLOW) if c['unread_no_aggregate'] else ''}; "
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


WORKERS = 8                                          # one gh call per commit: the wait is the network's, not the CPU's
RETRIES = 2


def check_runs(repo: str, sha: str) -> list[dict]:
    """A sha's check runs. A read that failed in a way a retry could help (gh.GhError.transient) is retried; any
    other failure, or the last one, is raised: a head whose checks are unread is never counted green."""
    for attempt in range(RETRIES + 1):
        try:
            return gh.api(f"repos/{repo}/commits/{sha}/check-runs?per_page=100", paginate=True, items_key="check_runs")
        except gh.GhError as e:
            if not e.transient or attempt == RETRIES:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def read_needed(repo: str, aggregates: set[str]) -> set[str] | None:
    """The default branch's workflow, through GitHub: any registered repository, not only a local clone. A repository
    with no such file is a known answer (None, unread); any other failure is raised."""
    try:
        doc = gh.api(f"repos/{repo}/contents/{WORKFLOW}")
    except gh.GhError as e:
        if e.status == 404:
            return None
        raise
    if not isinstance(doc, dict) or doc.get("encoding") != "base64":
        raise gh.GhError(f"read {WORKFLOW} of {repo}", "not a base64 file")
    return needed_jobs(base64.b64decode(doc["content"]).decode("utf-8"), aggregates)


def collect(repos: list[str], now: dt.datetime, days: int, window: int) -> list[dict]:
    hosts, aggregates = known_hosts(), aggregate_checks()
    needed = {repo: read_needed(repo, aggregates) for repo in repos}
    since = now - dt.timedelta(days=days + window)
    read = {repo: (results.main_commits(repo, since), results.merged_prs(repo, since, ("headRefName",))) for repo in repos}
    wanted = sorted({(repo, c["oid"]) for repo, (_, prs) in read.items() for pr in prs for c in pr.get("commits") or []
                     if needed[repo] is not None and in_period(pr, now, days)})
    # A sha never changes, so what GitHub says of it is asked once, all at once.
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        cache = dict(zip(wanted, pool.map(lambda k: check_runs(*k), wanted)))
    events: list[dict] = []
    for repo, (later, prs) in read.items():
        for pr in prs:
            events += events_of(repo, pr, later, lambda r, sha: cache[r, sha], now, days, window, hosts, needed[repo])
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
           "closed_period": [(now - dt.timedelta(days=a.days + a.window)).isoformat(), (now - dt.timedelta(days=a.window)).isoformat()],
           "attribution": "head ref; a fold's contributor", "judged_not_real": "not read", **rep}
    print(json.dumps(doc, indent=2) if a.json else render(rep, doc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
