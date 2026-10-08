#!/usr/bin/env python3
"""tools/fabric/results.py — verified results, supervision and cost per
verified result (ADR-026, ADR-036), read from artifacts only.

    fabric-results [--days 14] [--window 14] [--repo OWNER/NAME]... [--all] [--json] [--no-tokens]

For each pull request merged in the period:

- **verified** (ADR-026 §2): its head carried a posted review (the marker
  post-review.sh writes, on the head commit), its checks were green, and
  within the window after its merge it was neither reverted nor given a fix
  naming it (a later commit on main naming #N that the commit classifier
  calls a fix for #N). A PR still inside its window is **pending**: it may
  yet be verified or not.
- **supervision events** it needed (ADR-026 §2, the inputs readable here):
  the owner's arming of a PR under the band's floor (fewer than 8 work
  commits), and each commit whose subject records the owner's correction
  ("(owner" in the subject). Not yet read: OWNER-WORD sections in relay
  DECISIONs and drain collisions; the report says so.

The period's **cost** (ADR-036 §5 rule 3) is every login's own session
records (`fabric-ctl all tokens --days D`): input-token equivalents on the
direct path and on the broker, reported apart, never summed. A session
record names no repository, so the spend is the whole fleet's: it is divided
by verified results only with --all, when the results cover every registered
project too; per-repository cost waits on that attribution.

Every number is a trend to read, never a target and never a comparison
between agents (ADR-026 §5 rule 4, ADR-036 §5 rule 4).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import gh  # noqa: E402
import roots  # noqa: E402
from github import commit_class  # noqa: E402
from github.post_review import REVIEW_MARKER  # noqa: E402
BAND_FLOOR = 8                                       # ADR-019: fewer work commits, the owner arms
GREEN = {"SUCCESS", "SKIPPED", "NEUTRAL"}
OWNER_CORRECTION = re.compile(r"\(owner\b", re.I)


def classify(subject: str, body: str, pr: int, repo: str, parents: int = 1) -> str:
    """The one classifier (tools/fabric/github/commit_class.py): work, fix or merge.
    A merge is told by its parents, as pr-gate tells it, never by its words."""
    answers = "\n".join(m.group(1) for m in re.finditer(r"^Answers:\s*(.*)$", body, re.M))
    return commit_class.classify(" ".join(["p"] * max(parents, 1)), subject, answers, str(pr), repo)


def judge(pr: dict, later: list[dict], now: dt.datetime, window_days: int, cls=classify, repo: str = "") -> dict:
    """One merged PR against the commits on main after its merge.
    `later` holds {sha, subject, body, when} for main's commits inside the window."""
    n, head = pr["number"], pr["headRefOid"]
    merged = dt.datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00"))
    reviewed = any((rv.get("body") or "").startswith(REVIEW_MARKER) and (rv.get("commit") or {}).get("oid") == head
                   for rv in pr.get("reviews") or [])
    checks = [c.get("conclusion") or c.get("state") for c in pr.get("statusCheckRollup") or []]
    green = bool(checks) and all(c in GREEN for c in checks)
    own = {c["oid"] for c in pr.get("commits") or []} | {(pr.get("mergeCommit") or {}).get("oid")}
    reverted = any(any(t.startswith(sha[:7]) or sha.startswith(t) for t in re.findall(r"This reverts commit ([0-9a-f]{7,40})", c["body"])
                       for sha in own if sha) for c in later)
    naming = re.compile(rf"#{n}\b")
    fixed = [c["sha"][:7] for c in later if naming.search(c["subject"]) and cls(c["subject"], c["body"], n, repo) == "fix"]
    classes = [cls(c["messageHeadline"], c.get("messageBody") or "", n, repo, c.get("parents", 1)) for c in pr.get("commits") or []]
    work, fix = classes.count("work"), classes.count("fix")
    pending = now < merged + dt.timedelta(days=window_days)
    ok = reviewed and green and not reverted and not fixed
    status = "pending" if ok and pending else "verified" if ok else "not verified"
    reasons = [r for r, bad in (("no review on its head", not reviewed), ("checks not green", not green),
                                ("reverted", reverted), (f"fixed forward ({', '.join(fixed)})", bool(fixed))) if bad]
    supervision = (1 if work < BAND_FLOOR else 0) + sum(1 for c in pr.get("commits") or [] if OWNER_CORRECTION.search(c["messageHeadline"]))
    return {"number": n, "title": pr["title"], "merged": pr["mergedAt"][:10], "status": status, "reasons": reasons,
            "work": work, "fix": fix, "supervision": supervision}


def merged_prs(repo: str, since: dt.datetime) -> list[dict]:
    # The numbers first, then each PR alone: GitHub refuses one query over
    # 500,000 possible nodes, which fifty PRs with their commits, reviews
    # and checks already exceed. GitHub's search takes a date; the exact
    # bound is applied here, as main_commits applies it (review of #68).
    numbers = gh.pr_list(["number"], repo=repo, state="merged", search=f"merged:>={since.date().isoformat()}")
    fields = ["number", "title", "mergedAt", "headRefOid", "mergeCommit", "commits", "reviews", "statusCheckRollup"]
    prs = []
    for p in numbers:
        pr = gh.pr_view(p["number"], fields, repo=repo)
        # gh's commit list has no parents; the REST list has them, so a
        # merge folded into the branch is not counted as work (review of #68).
        parents = {c["sha"]: len(c.get("parents") or [])
                   for c in gh.api(f"repos/{repo}/pulls/{p['number']}/commits?per_page=100", paginate=True)}
        for c in pr.get("commits") or []:
            c["parents"] = parents.get(c["oid"], 1)
        if dt.datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00")) >= since:
            prs.append(pr)
    return prs


def main_commits(repo: str, since: dt.datetime) -> list[dict]:
    """The default branch's commits since `since`, from GitHub: any
    registered repository, not only a local clone."""
    rows = []
    for c in gh.api(f"repos/{repo}/commits?since={since.strftime('%Y-%m-%dT%H:%M:%SZ')}&per_page=100", paginate=True):
        subject, _, body = c["commit"]["message"].partition("\n")
        rows.append({"sha": c["sha"], "subject": subject, "body": body.strip("\n"),
                     "when": dt.datetime.fromisoformat(c["commit"]["committer"]["date"].replace("Z", "+00:00"))})
    return rows


def registered_repos() -> list[str]:
    """owner/name of every project in projects/registry.json, from its first GitHub remote."""
    with open(roots.projects_registry(engine=roots.code_root()), encoding="utf-8") as fh:
        doc = json.load(fh)
    out = []
    for proj in (doc.get("projects") or {}).values():
        for remote in proj.get("remotes") or []:
            m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", remote)
            if m:
                out.append(m.group(1))
                break
    return sorted(set(out))


def spend(days: int) -> dict | None:
    """Input-token equivalents per path over the period, from every login's
    own records; None when the control plane cannot be asked."""
    try:
        out = subprocess.run([os.path.join(ROOT, "bin", "fabric-ctl"), "all", "tokens", "--days", str(days), "--json"],
                             capture_output=True, text=True, timeout=180).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    by_account = {}
    for line in out.splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        t = rec.get("tokens") or {}
        if t.get("status") != "ok":
            continue
        acct = by_account.setdefault(rec.get("account") or f"?{len(by_account)}", {})
        for m in (t.get("models") or {}).values():
            acct[m.get("path", "?")] = acct.get(m.get("path", "?"), 0) + int(m.get("equiv") or 0)
    return {"by_account": by_account} if by_account else None


def period_cost(whole: dict | None, recent: dict | None) -> dict | None:
    """The period's spend: tokens over DAYS+WINDOW days less tokens over the
    last WINDOW days, subtracted account by account. The two reads are two
    fan-outs over the fleet; when they did not answer for the same
    accounts, a difference of totals would count an account's whole spend
    as the period's, or none of it — so there is no figure (review of #68)."""
    if not whole or not recent or set(whole["by_account"]) != set(recent["by_account"]):
        return None
    by_path = {}
    for acct, paths in whole["by_account"].items():
        for p, v in paths.items():
            by_path[p] = by_path.get(p, 0) + v - recent["by_account"][acct].get(p, 0)
    return {"by_path": by_path, "accounts": len(whole["by_account"])}


def closed_period(now: dt.datetime, days: int, window: int) -> tuple[dt.datetime, dt.datetime]:
    """(since, end): the DAYS before the last WINDOW days. The period is the
    one whose windows have closed: a PR merged less than WINDOW days ago
    cannot be verified yet (ADR-026 §2), so counting it made every default
    run read "verified 0" (review of #68). Those are listed apart as
    pending and never enter a ratio."""
    end = now - dt.timedelta(days=window)
    return end - dt.timedelta(days=days), end


def summarize(rows: list[dict], *, since: dt.datetime, end: dt.datetime, window: int, repos: list[str],
              cost: dict | None, every_repo: bool) -> dict:
    """The period's figures from the judged rows: only merges whose windows
    have closed count; every ratio divides by verified results; spend is
    divided only when the results cover every registered repository."""
    period = [r for r in rows if r["in_period"]]
    verified = [r for r in period if r["status"] == "verified"]
    sup = sum(r["supervision"] for r in verified)
    summary = {"period": f"{since.date()}..{end.date()}", "window_days": window, "repos": repos,
               "merged_in_period": len(period), "verified": len(verified),
               "pending_after_period": len(rows) - len(period),
               "verified_rate": round(len(verified) / len(period), 2) if period else None,
               "supervision_events": sup, "supervision_per_result": round(sup / len(verified), 2) if verified else None,
               "spend": cost, "unread_inputs": ["OWNER-WORD in relay DECISIONs", "drain collisions"]}
    if cost and every_repo and verified:
        summary["spend_per_result"] = {p: v // len(verified) for p, v in cost["by_path"].items()}
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=14,
                    help="the period's length: PRs merged between DAYS+WINDOW and WINDOW days ago, whose windows have closed")
    ap.add_argument("--window", type=int, default=14, help="days after a merge in which a revert or a fix unverifies it")
    ap.add_argument("--repo", action="append", help="owner/name; may repeat (default gzapi-org/agent-fabric)")
    ap.add_argument("--all", action="store_true", help="every registered project, and the spend divided by their results")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-tokens", action="store_true", help="skip the control plane's token read")
    a = ap.parse_args(argv)
    now = dt.datetime.now(dt.timezone.utc)
    since, end = closed_period(now, a.days, a.window)
    repos = registered_repos() if a.all else (a.repo or ["gzapi-org/agent-fabric"])
    rows = []
    try:
        read = {repo: (main_commits(repo, since), merged_prs(repo, since)) for repo in repos}
    except gh.GhError as e:
        print(f"fabric-results: {e}", file=sys.stderr)
        return 1
    for repo, (later, prs) in read.items():
        for pr in sorted(prs, key=lambda p: p["number"]):
            merged = dt.datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00"))
            inside = [c for c in later if merged < c["when"] <= merged + dt.timedelta(days=a.window)]
            row = {"repo": repo, **judge(pr, inside, now, a.window, repo=repo)}
            row["in_period"] = merged <= end
            rows.append(row)
    # The span the period's merges lie in: tokens over DAYS+WINDOW days less
    # tokens over the last WINDOW days, both from every login's records.
    whole, recent = (None, None) if a.no_tokens else (spend(a.days + a.window), spend(a.window))
    cost = period_cost(whole, recent)
    summary = summarize(rows, since=since, end=end, window=a.window, repos=repos, cost=cost, every_repo=a.all)
    # Both reads answered, for different logins: said as that, not as "not
    # read" (review of #70).
    if whole and recent and not cost:
        summary["spend_unmatched"] = sorted(set(whole["by_account"]) ^ set(recent["by_account"]))
    period = [r for r in rows if r["in_period"]]
    sup, pending = summary["supervision_events"], summary["pending_after_period"]
    if a.json:
        print(json.dumps({"summary": summary, "prs": rows}, indent=2))
        return 0
    for r in period:
        why = f"  ({'; '.join(r['reasons'])})" if r["reasons"] else ""
        print(f"{r['repo'].split('/')[-1]}#{r['number']:<5} {r['merged']}  {r['status']:<12} {r['work']} work, {r['fix']} fix  supervision {r['supervision']}{why}")
    print(f"\n{', '.join(repos)}: PRs merged {summary['period']} (their {a.window}-day windows closed): {len(period)}; "
          f"verified {summary['verified']}; verified rate {summary['verified_rate']}")
    print(f"after the period, still inside their windows, not counted: {pending}")
    print(f"supervision events on the verified results: {sup} ({summary['supervision_per_result']} per result); "
          f"not yet read: {', '.join(summary['unread_inputs'])}")
    if cost:
        paths = ", ".join(f"{p}: {v / 1e6:.1f}M" for p, v in sorted(cost["by_path"].items()))
        per = ", ".join(f"{p}: {v / 1e6:.1f}M" for p, v in sorted(summary.get("spend_per_result", {}).items()))
        print(f"spend over {summary['period']}, the whole fleet ({cost['accounts']} accounts answered): {paths} input-token equivalents; "
              + (f"per verified result: {per}" if per else "per result only with --all (the spend is every repository's)"))
    elif summary.get("spend_unmatched"):
        print(f"spend: no figure — the two token reads answered for different accounts "
              f"({', '.join(summary['spend_unmatched'])}); run it again when the fleet answers whole")
    else:
        print("spend: not read (--no-tokens, or the control plane did not answer)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
