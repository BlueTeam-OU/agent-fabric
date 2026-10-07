#!/usr/bin/env python3
"""runtime/github/pr-gate.sh with gh and pr-review-status mocked on PATH
and a throwaway git repository for the commit classification: the work /
fix / merge split, a revert netted with its in-range partner (once — a
revert-then-reapply leaves the original), each verdict (ask the owner,
arm, split, blocked by red checks, pending checks, no review, threads, a
conflict; armed; queued), the session filter, --all, numbers, --json, the
empty states, and --in-flight / --overlap. Ported from
runtime/github/test_pr-gate.sh (ADR-040 Wave 6), case for case. Plain
script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNDER_TEST = os.path.join(ROOT, "runtime", "github", "pr-gate.sh")

GH_MOCK = r'''#!/usr/bin/env python3
import json, os, sys
s, a = os.environ["MOCK_STATE"], sys.argv[1:]
line = " ".join(a)
def load(name):
    with open(os.path.join(s, name)) as fh:
        return json.load(fh)
if line.startswith("pr list"):
    if os.path.exists(os.path.join(s, "prlist_fail")):
        sys.exit(1)
    print(open(os.path.join(s, "prs.json")).read()); sys.exit(0)
if line.startswith("pr view"):
    n = int(a[2])
    for pr in load("prs.json") + load("closed.json"):
        if pr.get("number") == n:
            print(json.dumps(pr)); sys.exit(0)
    sys.exit(1)
if "graphql" in line:
    if os.path.exists(os.path.join(s, "graphql_fail")):
        sys.exit(1)
    print(open(os.path.join(s, "graphql.json")).read()); sys.exit(0)
print("mock gh: unhandled " + line, file=sys.stderr); sys.exit(1)
'''

REVIEW_STATUS_MOCK = r'''#!/usr/bin/env bash
S="$MOCK_STATE"
echo "PR #$1  state=OPEN"
echo "  independent reviews : $(cat "$S/reviews" 2>/dev/null || echo 0)"
echo "  blind reviews       : 0"
echo "  verdict comments    : $(cat "$S/verdicts" 2>/dev/null || echo 0)"
echo "  head reviewed?      : $(cat "$S/head_reviewed" 2>/dev/null || echo no)"
echo "  unresolved threads  : 0"
exit 0
'''

GREEN = [{"name": "ci / a", "status": "COMPLETED", "conclusion": "SUCCESS"}]
RED = [{"name": "ci / a", "status": "COMPLETED", "conclusion": "SUCCESS"},
       {"name": "backend / shard", "status": "COMPLETED", "conclusion": "FAILURE"}]
PENDING = [{"name": "ci / a", "status": "IN_PROGRESS", "conclusion": None}]


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    def has(pattern: str, text: str) -> bool:
        return re.search(pattern, text, re.M) is not None

    base_env = {k: v for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_")) and k != "GIT_DIR"}
    # The repository the mock serves, named as a session names it outside a
    # GitHub clone: gh's default repository is never read (gh.this_repo).
    base_env["GH_REPO"] = "testorg/testrepo"

    with tempfile.TemporaryDirectory() as sandbox:
        state, repo, origin = f"{sandbox}/state", f"{sandbox}/repo", f"{sandbox}/origin.git"
        os.makedirs(state)
        os.makedirs(f"{sandbox}/bin")

        def git(*args: str, cwd: str = repo, ok: bool = False) -> str:
            r = subprocess.run(["git", *args], cwd=cwd, env=base_env, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True, timeout=60)
            if r.returncode and not ok:
                raise RuntimeError(f"git {' '.join(args)}: exit {r.returncode}")
            return r.stdout

        def append(path: str, text: str) -> None:
            os.makedirs(os.path.dirname(f"{repo}/{path}"), exist_ok=True)
            with open(f"{repo}/{path}", "a", encoding="utf-8") as fh:
                fh.write(text)

        def c(msg: str) -> None:
            append("f.txt", msg + "\n")
            git("add", "-A")
            git("commit", "-q", "-m", msg)

        def head(ref: str = "HEAD") -> str:
            return git("rev-parse", ref).strip()

        # A repository with an origin: main, and a branch of work, fixes
        # and a merge.
        subprocess.run(["git", "init", "-q", "--bare", origin], env=base_env, check=True, timeout=30)
        subprocess.run(["git", "init", "-q", "-b", "main", repo], env=base_env, check=True, timeout=30)
        for k, v in (("user.email", "t@example.invalid"), ("user.name", "t"), ("commit.gpgsign", "false"),
                     ("tag.gpgSign", "false")):
            git("config", k, v)
        git("remote", "add", "origin", origin)
        c("base")
        git("push", "-q", "origin", "main")
        branch = "develop-qzapp/me/feat/thing"
        git("checkout", "-q", "-b", branch)
        c("work one")
        c("work two")
        git("checkout", "-q", "-b", "side", "main")
        append("g.txt", "side\n")
        git("add", "-A")
        git("commit", "-q", "-m", "side change")
        git("checkout", "-q", branch)
        git("merge", "-q", "--no-ff", "side", "-m", "Merge origin/main")
        c("fix: the review's F1 and F2")
        c("admin driver review: approving a stranded applicant gets its own 409")
        c("fix(passenger): the debounce still fired the wrong query")
        c("geocode: address the blind review of the entrypoint")
        c("third-round review: four P3s, the .env pin and the dropped spellings")
        c("feat(contracts): the review decision's reason reaches the merchant")
        # A fix whose subject names no review at all, carrying the trailer.
        append("f.txt", "trailer\n")
        git("add", "-A")
        git("commit", "-q", "-m", "db: 0055's guard was too broad and stopped the file re-applying", "-m", "Answers: PE-6")
        # A FOLDED trailer value (RFC-822 continuation): one record, one fix
        # — never a phantom work commit from the continuation line (#894
        # review F2).
        append("f.txt", "folded\n")
        git("add", "-A")
        git("commit", "-q", "-m", "docs(adr): the backfilled row keeps its updated_at", "-m", "Answers: PE-6,\n  PR-1")
        head_sha = head()
        git("push", "-q", "origin", branch)

        for name, text in (("gh", GH_MOCK), ("pr-review-status.sh", REVIEW_STATUS_MOCK)):
            with open(f"{sandbox}/bin/{name}", "w", encoding="utf-8") as fh:
                fh.write(text)
            os.chmod(f"{sandbox}/bin/{name}", 0o755)

        def put(name: str, text: str) -> None:
            with open(f"{state}/{name}", "w", encoding="utf-8") as fh:
                fh.write(text)

        def drop(name: str) -> None:
            if os.path.exists(f"{state}/{name}"):
                os.remove(f"{state}/{name}")

        def prs(rows: list) -> None:
            put("prs.json", json.dumps(rows))

        def graphql(mergeable: str, unresolved: int, armed: bool, queue: int | None, nodes: list) -> None:
            put("graphql.json", json.dumps({"data": {"repository": {"pullRequest": {
                "mergeStateStatus": "CLEAN", "mergeable": mergeable,
                "reviewThreads": {"nodes": [{"isResolved": False}] * unresolved},
                "mergeQueueEntry": None if queue is None else {"position": queue, "state": "AWAITING_CHECKS"},
                "autoMergeRequest": {"enabledAt": "x"} if armed else None,
                "statusCheckRollup": {"contexts": {"nodes": nodes}}}}}}))

        def review(head_reviewed: str, reviews: int = 1, verdicts: int = 0) -> None:
            put("head_reviewed", f"{head_reviewed}\n")
            put("reviews", f"{reviews}\n")
            put("verdicts", f"{verdicts}\n")
        put("closed.json", "[]")

        def run(*args: str) -> tuple[int, str]:
            env = {**base_env, "MOCK_STATE": state, "PATH": f"{sandbox}/bin:{base_env.get('PATH', '')}",
                   "AGENT_FABRIC_PR_REVIEW_STATUS": f"{sandbox}/bin/pr-review-status.sh",
                   "AGENT_FABRIC_PR_SESSION": "develop-qzapp/me"}
            r = subprocess.run(["bash", UNDER_TEST, *args], cwd=repo, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, timeout=300)
            return r.returncode, r.stdout

        def as_json(text: str):
            try:
                return json.loads(text)
            except ValueError:
                return None

        def pr_row(sha: str, n: int = 42, title: str = "the thing", ref: str = branch) -> dict:
            return {"number": n, "title": title, "headRefName": ref, "headRefOid": sha, "baseRefName": "main",
                    "state": "OPEN"}
        one = [pr_row(head_sha), pr_row(head_sha, 43, "someone else", "develop-qzapp/other/fix/x")]

        print("commits are split into work, review fixes and merges")
        prs(one)
        graphql("MERGEABLE", 0, False, None, GREEN)
        review("yes")
        rc, out = run()
        check("12 commits: 6 work (two own, one merged in, a domain 'driver review:', a fix(scope): bug fix, a "
              "'review decision' feature), 5 fix (F1/F2 labels; 'address the blind review'; 'third-round review: "
              "four P3s'; two review-less subjects with an Answers: trailer, one of them folded), 1 merge",
              rc == 0 and has(r"^#42  develop-qzapp/me \(me\)  commits=12 \(6 work, 5 fix, 1 merge\)", out),
              f"rc={rc}\n{out}")
        fixline = next((ln for ln in out.split("\n") if "counted as fix:" in ln), "")
        check("the subjects counted as fix are printed (and only those), so the split can be checked",
              '"fix: the review\'s F1 and F2"' in fixline and '"geocode: address the blind review of the entrypoint"'
              in fixline and '"third-round review: four P3s' in fixline and "fix(passenger)" not in fixline
              and "driver review" not in fixline, out)
        check("another session's PR is not listed by default", not has(r"^#43", out), out)

        print("the verdicts")
        check("green, reviewed head, 0 threads, under 8: ask the owner",
              "MERGEABLE — ask the owner (6 work commits < 8), then arm" in out, out)
        review("no", 1)
        out = run()[1]
        check("a review not on the head: BLOCKED, says NOT on head", "BLOCKED: no review of the head (NOT on head)" in out,
              out)
        review("no", 0)
        out = run()[1]
        check("no review at all: says none", "no review of the head (none)" in out, out)
        review("no", 0, 1)
        out = run()[1]
        check("a clean verdict comment on an earlier head counts as a review NOT on head, not none",
              "no review of the head (NOT on head)" in out, out)
        review("yes")
        graphql("MERGEABLE", 0, False, None, RED)
        out = run()[1]
        check("a failed check: named, BLOCKED",
              "checks=red:backend / shard" in out and "BLOCKED: red checks: backend / shard" in out, out)
        graphql("MERGEABLE", 0, False, None, PENDING)
        out = run()[1]
        check("a running check: pending, BLOCKED", "checks=pending:1" in out and "1 check(s) pending" in out, out)
        graphql("MERGEABLE", 2, False, None, GREEN)
        out = run()[1]
        check("unresolved threads block", "threads=2" in out and "2 unresolved thread(s)" in out, out)
        graphql("CONFLICTING", 0, False, None, GREEN)
        out = run()[1]
        check("a conflict blocks", "BLOCKED: conflicts with main" in out, out)
        graphql("MERGEABLE", 0, True, None, GREEN)
        out = run()[1]
        check("armed and clear", "armed=yes" in out and "ARMED and clear" in out, out)
        graphql("MERGEABLE", 0, True, None, RED)
        out = run()[1]
        check("armed but red: says what holds it", "ARMED but held: red checks" in out, out)
        graphql("MERGEABLE", 0, False, 3, GREEN)
        out = run()[1]
        check("queued: position, nothing to do", "queue=3" in out and "QUEUED (position 3)" in out, out)
        graphql("MERGEABLE", 0, False, None, [])
        out = run()[1]
        check("no check reported at all (seconds after a push): not green",
              "checks=none-yet" in out and "no check has reported yet" in out, out)
        graphql("MERGEABLE", 0, False, None, GREEN)
        prs([{**one[0], "isDraft": True}, one[1]])
        out = run()[1]
        check("a draft is never told to arm", "BLOCKED: a draft" in out, out)
        prs(one)
        put("graphql_fail", "")
        rc, out = run()
        check("a failed graphql read: exit 2, no invented BLOCKED row",
              rc == 2 and "could not read pull request #42 from GitHub" in out, f"rc={rc}\n{out}")
        drop("graphql_fail")

        print("the count rule's other bands")
        graphql("MERGEABLE", 0, False, None, GREEN)
        review("yes")
        for i in range(7, 10):
            c(f"work {i}")
        git("push", "-q", "origin", branch)
        prs([{**r, "headRefOid": head()} for r in one])
        out = run()[1]
        check("8-16 work commits at the gate: arm",
              "(9 work, " in out and "MERGEABLE — arm: post the basis (9 work commits" in out, out)
        for i in range(10, 18):
            c(f"work {i}")
        git("push", "-q", "origin", branch)
        prs([{**r, "headRefOid": head()} for r in one])
        out = run()[1]
        check("over 16: MERGEABLE, smaller batches next time, never blocked for it",
              "(17 work, " in out and "17 work commits, over 16: smaller batches next time" in out, out)

        print("selection and shapes")
        out = run("--all")[1]
        check("--all lists every open PR with its owner from the branch prefix, mine marked (me)",
              has(r"^#43  develop-qzapp/other  commits=", out) and has(r"^#42  develop-qzapp/me \(me\)  commits=", out),
              out)
        rows = as_json(run("--all", "--json")[1]) or []
        by = {r.get("number"): r for r in rows if isinstance(r, dict)}
        check("--json carries owner and mine", by.get(43, {}).get("owner") == "develop-qzapp/other"
              and by.get(43, {}).get("mine") is False and by.get(42, {}).get("mine") is True, json.dumps(rows)[:400])
        out = run("43")[1]
        check("a number lists that PR whoever opened it", has(r"^#43", out) and not has(r"^#42", out), out)
        put("closed.json", json.dumps([{"number": 40, "title": "old", "headRefName": "develop-qzapp/me/fix/old",
                                        "headRefOid": "0" * 40, "baseRefName": "main", "state": "MERGED"}]))
        rc, out = run("40", "43")
        check("a merged PR given by number is said and skipped, never gated",
              rc == 0 and "#40 is MERGED — not at any gate; skipped" in out and not has(r"^#40", out)
              and has(r"^#43", out), f"rc={rc}\n{out}")
        rc, out = run("42abc")
        check("a non-numeric argument is a usage error, not a silently dropped PR", rc == 2, f"rc={rc}\n{out}")
        rc, out = run("999")
        check("a number that is no PR is said", rc == 0 and "#999 is not a pull request" in out, f"rc={rc}\n{out}")
        rows = as_json(run("--json")[1]) or [{}]
        check("--json carries the row as data, fix_subjects included",
              len(rows) == 1 and rows[0].get("work_commits") == 17 and len(rows[0].get("fix_subjects") or []) == 5
              and str(rows[0].get("verdict", "")).startswith("MERGEABLE"), json.dumps(rows)[:400])
        prs([])
        out = run()[1]
        check("none of mine: said", "no open pull request from develop-qzapp/me" in out, out)
        out = run("--json")[1]
        check("…and --json prints an empty list", "".join(out.split()) == "[]", out)

        print("pr-gate: a head the clone does not have is 'unknown', never a zero (review F2 on #886)")
        prs([{**r, "headRefOid": "deadbeef" * 5} for r in one])
        rc, out = run("--json")
        r0 = (as_json(out) or [{}])[0]
        check("--json: commits_known false and the three counts null",
              rc == 0 and [r0.get(k, "missing") for k in ("commits_known", "work_commits", "fix_commits",
                                                          "merge_commits")] == [False, None, None, None],
              f"rc={rc}\n{out}")
        out = run()[1]
        check("the row says unknown (fetch)", "commits=unknown (fetch)" in out, out)
        check("…and the verdict says to apply the rule by hand", "commits unknown" in out, out)
        prs(one)
        r0 = (as_json(run("--json")[1]) or [{}])[0]
        check("a counted head: commits_known true", r0.get("commits_known") is True, json.dumps(r0)[:300])

        print("pr-gate: an AWAITING-SUPPLY line with no range line blocks (review F3 on #886)")
        prs([{**one[0], "body": "waiting\n\nAWAITING-SUPPLY: develop-qzapp/db-admin\nAWAITING-SUPPLY: web-dev-01\n\n"
                                "aaaaaaa1..bbbbbbb2: web-dev-01 (web-dev)"}, one[1]])
        out = run()[1]
        check("the unmet login blocks, by its last address segment",
              "awaiting supply from db-admin (AWAITING-SUPPLY" in out, out)
        check("the met login does not block", not has(r"awaiting supply from.*web-dev-01", out), out)
        r0 = (as_json(run("--json")[1]) or [{}])[0]
        check("--json carries awaiting_supply", r0.get("awaiting_supply") == ["db-admin"], json.dumps(r0)[:300])
        prs(one)

        print("pr-gate: a failed fetch makes every count unknown, not stale (re-review risk on #886)")
        git("remote", "set-url", "origin", f"{sandbox}/no-such-remote.git")
        out = run("--json")[1]
        check("the failure is said", "git fetch origin failed" in out, out)
        r0 = (as_json("\n".join(ln for ln in out.split("\n") if not ln.startswith("pr-gate:"))) or [{}])[0]
        check("commits_known false when origin cannot be fetched", r0.get("commits_known") is False, out)
        git("remote", "set-url", "origin", origin)
        r0 = (as_json(run("--json")[1]) or [{}])[0]
        check("…and counted again once the remote is back", r0.get("commits_known") is True, json.dumps(r0)[:300])

        print("pr-gate: a revert and the commit it reverts net to zero work (gzapp #912: '9 work — arm' where the "
              "count was 7)")
        # On the same branch: a work commit, then git's own revert of it
        # (the body carries "This reverts commit <sha>."), then a revert of a
        # commit that is already on main (not in the range: it changes the
        # tree, so it is work), then a "Revert …" subject with no trailer
        # line (prose: work).
        prs([pr_row(head())])
        graphql("MERGEABLE", 0, False, None, GREEN)
        review("yes")
        r0 = (as_json(run("--json")[1]) or [{}])[0]
        before_work, before_fix = r0.get("work_commits"), r0.get("fix_commits")
        c("feat: the used-by guard")
        git("revert", "--no-edit", head())
        base_sha = head("origin/main")
        if subprocess.run(["git", "revert", "--no-edit", base_sha], cwd=repo, env=base_env, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, timeout=60).returncode:
            git("revert", "--abort", ok=True)
            append("f.txt", "revert-main\n")
            git("add", "-A")
            git("commit", "-q", "-m", 'Revert "base"', "-m", f"This reverts commit {base_sha}.")
        c("Revert the thing by hand")
        git("push", "-q", "origin", branch)
        prs([pr_row(head())])
        rc, out = run("--json")
        r0 = (as_json(out) or [{}])[0]
        check("four commits added: the in-range pair is netted (2); the revert of a main commit and the "
              "trailer-less 'Revert' are work (+2); fixes unchanged",
              rc == 0 and isinstance(before_work, int)
              and [r0.get("work_commits"), r0.get("fix_commits"), r0.get("netted_commits")]
              == [before_work + 2, before_fix, 2], f"rc={rc} (before: {before_work} work, {before_fix} fix)\n{out}")
        out = run()[1]
        check("the row says so", f"work, {before_fix} fix, 1 merge, 2 netted by a revert)" in out, out)
        check("…and names the netted pair, as it names the fixes",
              'netted by a revert: "feat: the used-by guard"; "Revert "feat: the used-by guard""' in out
              or 'netted by a revert: "Revert "feat: the used-by guard""; "feat: the used-by guard"' in out, out)

        print("pr-gate: a revert of a revert leaves the original as work — a commit nets once")
        # feat B; revert B; reapply B (git's revert of the revert). The tree
        # after the chain is the tree after B: 1 work, 2 netted — not 0
        # work, 3 netted.
        c("feat: B, the thing reapplied")
        git("revert", "--no-edit", head())
        git("revert", "--no-edit", head())
        git("push", "-q", "origin", branch)
        prs([pr_row(head())])
        rc, out = run("--json")
        r0 = (as_json(out) or [{}])[0]
        check("the chain adds one work (B stands) and two netted; the earlier pair still netted",
              rc == 0 and isinstance(before_work, int)
              and [r0.get("work_commits"), r0.get("netted_commits")] == [before_work + 3, 4],
              f"rc={rc} (before: {before_work} work)\n{out}")

        print("pr-gate --in-flight / --overlap: every branch on origin, PR or not; what shares its paths")
        # A job waiting for a merge: pushed, no PR, sharing f.txt with the PR
        # branch.
        git("checkout", "-q", "-b", "develop-qzapp/other/feat/parked", "main")
        append("f.txt", "parked\n")
        append("api/stop.py", "x\n")
        git("add", "-A")
        git("commit", "-q", "-m", "parked work")
        git("push", "-q", "origin", "develop-qzapp/other/feat/parked")
        # Unrelated work: a path nobody else touches.
        git("checkout", "-q", "-b", "develop-qzapp/third/docs/readme", "main")
        append("README.md", "r\n")
        git("add", "-A")
        git("commit", "-q", "-m", "readme")
        git("push", "-q", "origin", "develop-qzapp/third/docs/readme")
        # Off the naming convention.
        git("checkout", "-q", "-b", "hotfix", "main")
        append("h.txt", "h\n")
        git("add", "-A")
        git("commit", "-q", "-m", "hotfix")
        git("push", "-q", "origin", "hotfix")
        # Merged already: not in flight.
        git("checkout", "-q", "-b", "develop-qzapp/me/done", "main")
        append("d.txt", "d\n")
        git("add", "-A")
        git("commit", "-q", "-m", "done")
        git("checkout", "-q", "main")
        git("merge", "-q", "--ff-only", "develop-qzapp/me/done")
        git("push", "-q", "origin", "main", "develop-qzapp/me/done")
        git("checkout", "-q", branch)
        prs([pr_row(head(branch))])

        def snap() -> str:
            return head() + git("status", "--porcelain") + git("for-each-ref", "--format=%(refname) %(objectname)",
                                                               "refs/heads")
        before = snap()
        rc, out = run("--in-flight")
        check("a pushed branch with no PR is a row: owner from its prefix, no PR, commits ahead",
              rc == 0 and has(r"^develop-qzapp/other  develop-qzapp/other/feat/parked  no PR  ahead=1", out),
              f"rc={rc}\n{out}")
        check("…a branch with a PR carries its number", has(r"^develop-qzapp/me  develop-qzapp/me/feat/thing  #42", out),
              out)
        check("…a branch merged into the base is not in flight", "develop-qzapp/me/done" not in out, out)
        check("…a branch off the convention reads unattributed, never guessed", has(r"^unattributed  hotfix  no PR", out),
              out)
        check("…and the clone's HEAD, working tree and branches are untouched", before == snap())

        rc, out = run("--overlap", "develop-qzapp/other/feat/parked")
        check("--overlap lists the PR sharing a path, with the path, and omits the branches sharing none",
              rc == 0 and "develop-qzapp/me/feat/thing  #42" in out and "shares 1: f.txt" in out
              and "docs/readme" not in out and "  hotfix  " not in out, f"rc={rc}\n{out}")
        rc, out = run("--overlap", "42", "--json")
        d = as_json(out) or {}
        rows = d.get("rows") or [{}] if isinstance(d, dict) else [{}]
        got = [d.get("overlap_with") if isinstance(d, dict) else None, ",".join(str(r.get("branch")) for r in rows),
               (rows[0].get("shared") or [None])[0], d.get("fetch_ok") if isinstance(d, dict) else None]
        check("…by PR number too, and as data: overlap_with, shared, fetch_ok",
              rc == 0 and got == [branch, "develop-qzapp/other/feat/parked", "f.txt", True], f"rc={rc}\n{out}")
        rc, out = run("--in-flight", "--path", "api/")
        check("--path keeps only the rows changing something under the prefix",
              rc == 0 and "feat/parked" in out and "feat/thing" not in out, f"rc={rc}\n{out}")
        rc, out = run("--overlap", "no/such/branch")
        check("an unknown branch is said, exit 2", rc == 2 and "not a branch in flight on origin" in out,
              f"rc={rc}\n{out}")
        rc, out = run("--in-flight", "42")
        check("--in-flight takes no PR numbers", rc == 2, f"rc={rc}\n{out}")
        out = run("--overlap", "develop-qzapp/other/feat/parked")[1]
        check("--overlap says that no shared path does not mean compatible",
              "no shared path is not the same as compatible" in out, out)
        rc, out = run("--overlap", branch, "--path", "api/")
        check("--overlap with --path: the target is found among every branch, though it changes nothing under the "
              "prefix", rc == 0 and "not a branch in flight" not in out, f"rc={rc}\n{out}")
        put("prlist_fail", "")
        rc, out = run("--overlap", "42")
        drop("prlist_fail")
        check("--overlap by number with no PR list: said as such, not 'not in flight'",
              rc == 2 and "cannot be resolved to a branch — the PR list is unavailable" in out, f"rc={rc}\n{out}")
        put("prlist_fail", "")
        rc, out = run("--in-flight")
        drop("prlist_fail")
        check("gh unable to list PRs: every row reads 'PR unavailable', never 'no PR'; exit 2",
              rc == 2 and "PR unavailable" in out and "  no PR  " not in out, f"rc={rc}\n{out}")
        git("remote", "set-url", "origin", f"{sandbox}/nowhere.git")
        rc, out = run("--in-flight", "--json")
        git("remote", "set-url", "origin", origin)
        check("a failed fetch is said first, fetch_ok false, exit 2 — the rows are marked as what origin last showed",
              rc == 2 and "git fetch origin failed" in out and has(r"at its last fetch \([0-9]{4}-", out)
              and '"fetch_ok": false' in out, f"rc={rc}\n{out}")

    print(f"\ntest_pr_gate_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
