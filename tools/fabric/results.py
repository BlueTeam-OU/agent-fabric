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
REVIEW_MARKER = "<!-- agent-fabric-review v1 -->"   # runtime/github/post-review.sh
BAND_FLOOR = 8                                       # ADR-019: fewer work commits, the owner arms
GREEN = {"SUCCESS", "SKIPPED", "NEUTRAL"}
OWNER_CORRECTION = re.compile(r"\(owner\b", re.I)


def classify(subject: str, body: str, pr: int, repo: str) -> str:
    """The one classifier (runtime/github/commit-class.sh): work, fix or merge."""
    answers = "\n".join(m.group(1) for m in re.finditer(r"^Answers:\s*(.*)$", body, re.M))
    r = subprocess.run(["bash", "-c", 'source "$0"; commit_class "$1" "$2" "$3" "$4" "$5"',
                        os.path.join(ROOT, "runtime", "github", "commit-class.sh"),
                        "p", subject, answers, str(pr), repo.split("/")[-1]], capture_output=True, text=True)
    return r.stdout.strip() or "work"


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
    classes = [cls(c["messageHeadline"], c.get("messageBody") or "", n, repo) for c in pr.get("commits") or []]
    work, fix = classes.count("work"), classes.count("fix")
    pending = now < merged + dt.timedelta(days=window_days)
    ok = reviewed and green and not reverted and not fixed
    status = "pending" if ok and pending else "verified" if ok else "not verified"
    reasons = [r for r, bad in (("no review on its head", not reviewed), ("checks not green", not green),
                                ("reverted", reverted), (f"fixed forward ({', '.join(fixed)})", bool(fixed))) if bad]
    supervision = (1 if work < BAND_FLOOR else 0) + sum(1 for c in pr.get("commits") or [] if OWNER_CORRECTION.search(c["messageHeadline"]))
    return {"number": n, "title": pr["title"], "merged": pr["mergedAt"][:10], "status": status, "reasons": reasons,
            "work": work, "fix": fix, "supervision": supervision}


def _gh(*args: str) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"fabric-results: gh {args[0]} {args[1]}: {(r.stderr.strip().splitlines() or ['failed'])[-1]}")
    return r.stdout


def merged_prs(repo: str, since: dt.date) -> list[dict]:
    # The numbers first, then each PR alone: GitHub refuses one query over
    # 500,000 possible nodes, which fifty PRs with their commits, reviews
    # and checks already exceed.
    numbers = json.loads(_gh("pr", "list", "--repo", repo, "--state", "merged", "--limit", "1000",
                             "--search", f"merged:>={since.isoformat()}", "--json", "number"))
    fields = "number,title,mergedAt,headRefOid,mergeCommit,commits,reviews,statusCheckRollup"
    return [json.loads(_gh("pr", "view", str(p["number"]), "--repo", repo, "--json", fields)) for p in numbers]


def main_commits(repo: str, since: dt.datetime) -> list[dict]:
    """The default branch's commits since `since`, from GitHub: any
    registered repository, not only a local clone."""
    out = _gh("api", "--paginate", f"repos/{repo}/commits?since={since.strftime('%Y-%m-%dT%H:%M:%SZ')}&per_page=100",
              "--jq", ".[] | {sha, message: .commit.message, when: .commit.committer.date}")
    rows = []
    for line in out.splitlines():
        c = json.loads(line)
        subject, _, body = c["message"].partition("\n")
        rows.append({"sha": c["sha"], "subject": subject, "body": body.strip("\n"),
                     "when": dt.datetime.fromisoformat(c["when"].replace("Z", "+00:00"))})
    return rows


def registered_repos() -> list[str]:
    """owner/name of every project in projects/registry.json, from its first GitHub remote."""
    with open(os.path.join(ROOT, "projects", "registry.json"), encoding="utf-8") as fh:
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
    total, answered = {}, 0
    for line in out.splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        t = rec.get("tokens") or {}
        if t.get("status") != "ok":
            continue
        answered += 1
        for m in (t.get("models") or {}).values():
            total[m.get("path", "?")] = total.get(m.get("path", "?"), 0) + int(m.get("equiv") or 0)
    return {"by_path": total, "accounts": answered} if answered else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=14, help="the period: PRs merged in the last N days")
    ap.add_argument("--window", type=int, default=14, help="days after a merge in which a revert or a fix unverifies it")
    ap.add_argument("--repo", action="append", help="owner/name; may repeat (default gzapi-org/agent-fabric)")
    ap.add_argument("--all", action="store_true", help="every registered project, and the spend divided by their results")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-tokens", action="store_true", help="skip the control plane's token read")
    a = ap.parse_args(argv)
    now = dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(days=a.days)
    repos = registered_repos() if a.all else (a.repo or ["gzapi-org/agent-fabric"])
    rows = []
    for repo in repos:
        later = main_commits(repo, since)
        for pr in sorted(merged_prs(repo, since.date()), key=lambda p: p["number"]):
            merged = dt.datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00"))
            inside = [c for c in later if merged < c["when"] <= merged + dt.timedelta(days=a.window)]
            rows.append({"repo": repo, **judge(pr, inside, now, a.window, repo=repo)})
    verified = [r for r in rows if r["status"] == "verified"]
    pending = [r for r in rows if r["status"] == "pending"]
    sup = sum(r["supervision"] for r in rows if r["status"] in ("verified", "pending"))
    cost = None if a.no_tokens else spend(a.days)
    summary = {"period_days": a.days, "window_days": a.window, "repos": repos, "merged": len(rows),
               "verified": len(verified), "pending": len(pending),
               "verified_rate": round(len(verified) / len(rows), 2) if rows else None,
               "supervision_events": sup, "supervision_per_result": round(sup / (len(verified) + len(pending)), 2) if verified or pending else None,
               "spend": cost, "unread_inputs": ["OWNER-WORD in relay DECISIONs", "drain collisions"]}
    if cost and a.all and (verified or pending):
        summary["spend_per_result"] = {p: v // (len(verified) + len(pending)) for p, v in cost["by_path"].items()}
    if a.json:
        print(json.dumps({"summary": summary, "prs": rows}, indent=2))
        return 0
    for r in rows:
        why = f"  ({'; '.join(r['reasons'])})" if r["reasons"] else ""
        print(f"{r['repo'].split('/')[-1]}#{r['number']:<5} {r['merged']}  {r['status']:<12} {r['work']} work, {r['fix']} fix  supervision {r['supervision']}{why}")
    print(f"\n{', '.join(repos)}: PRs merged in the last {a.days} days: {len(rows)}; verified {len(verified)}, "
          f"pending (inside the {a.window}-day window) {len(pending)}; verified rate {summary['verified_rate']}")
    print(f"supervision events on verified and pending results: {sup} ({summary['supervision_per_result']} per result); "
          f"not yet read: {', '.join(summary['unread_inputs'])}")
    if cost:
        paths = ", ".join(f"{p}: {v / 1e6:.1f}M" for p, v in sorted(cost["by_path"].items()))
        per = ", ".join(f"{p}: {v / 1e6:.1f}M" for p, v in sorted(summary.get("spend_per_result", {}).items()))
        print(f"spend over the period, the whole fleet ({cost['accounts']} accounts answered): {paths} input-token equivalents; "
              + (f"per result: {per}" if per else "per result only with --all (the spend is every repository's)"))
    else:
        print("spend: not read (--no-tokens, or the control plane did not answer)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
