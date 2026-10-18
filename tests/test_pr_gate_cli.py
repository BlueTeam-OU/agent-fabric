#!/usr/bin/env python3
"""fabric-pr gate with gh and pr-review-status mocked on PATH and a
throwaway git repository: one smoke case for each outcome of the command
itself — the commit split read through git from a real clone, the session
filter, --all, numbers (open, merged, closed, no PR, not a number), --json,
the empty states, a head or a remote the clone cannot read, gh failing
(exit 2), and --in-flight / --overlap. The verdict logic (ask the owner,
arm, split, blocked by red checks, pending checks, no review, threads, a
conflict; armed; queued), the work / fix / merge classification and the
revert netting are asserted in-process by tests/test_pr_gate.py, which is
where a new reason or a new commit shape goes. Ported from
runtime/github/test_pr-gate.sh (ADR-040 Wave 6). Plain script: prints
ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory
scrub_process_env()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNDER_TEST = [os.path.join(ROOT, "bin", "fabric-pr"), "gate"]

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
    # Like GitHub, headRefOid is the asked PR's head, and only when the
    # query asks for it.
    req = json.load(sys.stdin)
    doc = load("graphql.json")
    if "headRefOid" in req["query"]:
        head = next((pr.get("headRefOid") for pr in load("prs.json") if pr.get("number") == req["variables"].get("number")), None)
        doc["data"]["repository"]["pullRequest"]["headRefOid"] = head
    print(json.dumps(doc)); sys.exit(0)
print("mock gh: unhandled " + line, file=sys.stderr); sys.exit(1)
'''

# Both engines' reviews of the asked PR's head (from the same prs.json the gh mock answers from), as `-q --json`.
REVIEW_STATUS_MOCK = r'''#!/usr/bin/env python3
import json, os, sys
[ "-q", "--json"] == sys.argv[2:] or sys.exit(2)
with open(os.path.join(os.environ["MOCK_STATE"], "prs.json")) as fh:
    head = next(pr["headRefOid"] for pr in json.load(fh) if pr.get("number") == int(sys.argv[1]))
print(json.dumps({"blind": {"rows": [{"commit_sha8": head[:8], "engine": e} for e in ("claude", "codex")]},
                  "unresolved_threads": 0}))
'''

GREEN = [{"name": "ci / a", "status": "COMPLETED", "conclusion": "SUCCESS"}]


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
            r = subprocess.run(["git", *args], cwd=cwd, env=git_env(base_env), stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True, timeout=60)
            if r.returncode and not ok:
                raise RuntimeError(f"git {' '.join(args)}: exit {r.returncode}")
            return r.stdout

        def append(path: str, text: str) -> None:
            os.makedirs(os.path.dirname(f"{repo}/{path}"), exist_ok=True)
            with open(f"{repo}/{path}", "a", encoding="utf-8") as fh:
                fh.write(text)

        def c(msg: str, *more: str) -> None:
            append("f.txt", msg + "\n")
            git("add", "-A")
            git("commit", "-q", *[a for m in (msg, *more) for a in ("-m", m)])

        def head(ref: str = "HEAD") -> str:
            return git("rev-parse", ref).strip()

        # A repository with an origin: main, and a branch of work, a fix, a
        # fix whose Answers: trailer is folded, and a merge. What counts as
        # which is tests/test_pr_gate.py's; here it is read through git.
        subprocess.run(["git", "init", "-q", "--bare", origin], env=git_env(base_env), check=True, timeout=30)
        subprocess.run(["git", "init", "-q", "-b", "main", repo], env=git_env(base_env), check=True, timeout=30)
        for k, v in (("user.email", "t@example.invalid"), ("user.name", "t"), ("commit.gpgsign", "false"),
                     ("tag.gpgSign", "false")):
            git("config", k, v)
        # origin is the GitHub URL of the repository GH_REPO names, as in a real clone, so the gate counts here (it
        # counts nothing in a clone of another repository); git reaches the bare one through url.<x>.insteadOf.
        # The fork's URL is routed there too: a clone of another repository that shares the history.
        gh_url, fork_url = "git@github.com:testorg/testrepo.git", "git@github.com:testorg/fork.git"
        routed = [origin]

        def route(target: str) -> None:
            git("config", "--remove-section", f"url.{routed[0]}", ok=True)
            for u in (gh_url, fork_url):
                git("config", "--add", f"url.{target}.insteadOf", u)
            routed[0] = target

        route(origin)
        git("remote", "add", "origin", gh_url)
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
        c("docs(adr): the backfilled row keeps its updated_at", "Answers: PE-6,\n  PR-1")
        head_sha = head()
        git("push", "-q", "origin", branch)

        for name, text in (("gh", GH_MOCK), ("review-status-mock", REVIEW_STATUS_MOCK)):
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

        # A clear PR: mergeable, no thread, not armed, not queued, green.
        put("graphql.json", json.dumps({"data": {"repository": {"pullRequest": {
            "mergeStateStatus": "CLEAN", "mergeable": "MERGEABLE", "reviewThreads": {"nodes": []},
            "mergeQueueEntry": None, "autoMergeRequest": None,
            "statusCheckRollup": {"contexts": {"nodes": GREEN}}}}}}))
        put("closed.json", "[]")

        def run(*args: str) -> tuple[int, str]:
            env = {**base_env, "MOCK_STATE": state, "PATH": f"{sandbox}/bin:{base_env.get('PATH', '')}",
                   "AGENT_FABRIC_PR_REVIEW_STATUS": f"{sandbox}/bin/review-status-mock",
                   "AGENT_FABRIC_PR_SESSION": "develop-qzapp/me"}
            r = subprocess.run([*UNDER_TEST, *args], cwd=repo, env=env, stdout=subprocess.PIPE,
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

        print("the default row: the commits split as git reads them, this session's PR only")
        prs(one)
        rc, out = run()
        check("6 commits through a real clone: 3 work (two own, one merged in), 2 fix, 1 merge; the row ends in its verdict",
              rc == 0 and has(r"^#42  develop-qzapp/me \(me\)  commits=6 \(3 work, 2 fix, 1 merge\)", out)
              and "MERGEABLE — ask the owner (3 work commits < 8), then arm" in out, f"rc={rc}\n{out}")
        check("the review is each engine's the fleet default asks (claude required, codex additional), on the row's head",
              has(r"  review=head reviewed: claude ✓ codex ✓ \(head [0-9a-f]{8}\)  threads=0", out), out)
        fixline = next((ln for ln in out.split("\n") if "counted as fix:" in ln), "")
        check("the subjects counted as fix are printed (and only those), so the split can be checked",
              '"fix: the review\'s F1 and F2"' in fixline and '"docs(adr): the backfilled row' in fixline
              and "work one" not in fixline, out)
        check("another session's PR is not listed by default", not has(r"^#43", out), out)

        print("a project's pr-tools.json names its own variables for the fabric's")
        tools_cfg = os.path.join(sandbox, "pr-tools.json")
        with open(tools_cfg, "w", encoding="utf-8") as fh:
            json.dump({"env_aliases": {"T_PROJECT_SESSION": "AGENT_FABRIC_PR_SESSION"}}, fh)

        def run_as_project(config: str | None) -> str:
            env = {**base_env, "MOCK_STATE": state, "PATH": f"{sandbox}/bin:{base_env.get('PATH', '')}",
                   "AGENT_FABRIC_PR_REVIEW_STATUS": f"{sandbox}/bin/review-status-mock",
                   "T_PROJECT_SESSION": "develop-qzapp/me"}
            if config:
                env["AGENT_FABRIC_PR_TOOLS_CONFIG"] = config
            r = subprocess.run([*UNDER_TEST], cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, timeout=300)
            return r.stdout
        check("the project's session variable selects this session's PRs through its pr-tools.json",
              has(r"^#42  develop-qzapp/me \(me\)  commits=", run_as_project(tools_cfg)))
        check("…and without that file it selects nothing: the control that shows the alias did it",
              not has(r"^#42", run_as_project(None)))

        print("gh failing")
        put("graphql_fail", "")
        rc, out = run()
        check("a failed graphql read: exit 2, no invented BLOCKED row",
              rc == 2 and "could not read pull request #42 from GitHub" in out, f"rc={rc}\n{out}")
        drop("graphql_fail")

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
                                        "headRefOid": "0" * 40, "baseRefName": "main", "state": "MERGED"},
                                       {"number": 41, "title": "dropped", "headRefName": "develop-qzapp/me/fix/dropped",
                                        "headRefOid": "0" * 40, "baseRefName": "main", "state": "CLOSED"}]))
        # graphql fails: a MERGED row reads nothing from GitHub's graphql, so
        # it must answer all the same; a gated row would exit 2.
        put("graphql_fail", "")
        rc, out = run("40", "41")
        drop("graphql_fail")
        # Owner's decision of 2026-10-09 (request 01a12005): a merged PR is a row of its own, so a
        # landing is reported with counts; a closed-unmerged one is skipped as before.
        check("a merged PR given by number is one MERGED row, never gated; with no merge commit its commits cannot be counted",
              rc == 0 and has(r"^#40  develop-qzapp/me \(me\)  commits=cannot be counted  state=MERGED", out)
              and "MERGED — not at any gate" in out and not has(r"^#40.*checks=", out), f"rc={rc}\n{out}")
        check("a closed-unmerged PR given by number is said and skipped, never gated",
              "#41 is CLOSED — not at any gate; skipped" in out and not has(r"^#41", out), f"rc={rc}\n{out}")
        rc, out = run("42abc")
        check("a non-numeric argument is a usage error, not a silently dropped PR", rc == 2, f"rc={rc}\n{out}")
        rc, out = run("999")
        check("a number that is no PR is said", rc == 0 and "#999 is not a pull request" in out, f"rc={rc}\n{out}")
        # The body is the PR's own text read from gh: its unmet AWAITING-SUPPLY is a field of the row.
        prs([{**one[0], "body": "waiting\n\nAWAITING-SUPPLY: develop-qzapp/db-admin\n"}, one[1]])
        rows = as_json(run("--json")[1]) or [{}]
        check("--json carries the row as data: the split, fix_subjects, awaiting_supply, the verdict",
              len(rows) == 1 and rows[0].get("work_commits") == 3 and len(rows[0].get("fix_subjects") or []) == 2
              and rows[0].get("awaiting_supply") == ["db-admin"]
              and str(rows[0].get("verdict", "")).startswith("BLOCKED: awaiting supply"), json.dumps(rows)[:400])
        prs([])
        out = run()[1]
        check("none of mine: said", "no open pull request from develop-qzapp/me" in out, out)
        out = run("--json")[1]
        check("…and --json prints an empty list", "".join(out.split()) == "[]", out)

        print("a head the clone does not have is 'unknown', never a zero (review F2 on #886)")
        prs([{**r, "headRefOid": "deadbeef" * 5} for r in one])
        rc, out = run("--json")
        r0 = (as_json(out) or [{}])[0]
        check("--json: commits_known false and the three counts null",
              rc == 0 and [r0.get(k, "missing") for k in ("commits_known", "work_commits", "fix_commits",
                                                          "merge_commits")] == [False, None, None, None],
              f"rc={rc}\n{out}")
        prs(one)

        print("a failed fetch makes every count unknown, not stale (re-review risk on #886)")
        route(f"{sandbox}/no-such-remote.git")
        out = run("--json")[1]
        check("the failure is said", "git fetch origin failed" in out, out)
        r0 = (as_json("\n".join(ln for ln in out.split("\n") if not ln.startswith("pr-gate:"))) or [{}])[0]
        check("commits_known false when origin cannot be fetched", r0.get("commits_known") is False, out)
        route(origin)

        print("a clone whose origin is another repository counts nothing, even sharing the history (review F3 on #300)")
        git("remote", "set-url", "origin", fork_url)
        rc, out = run("--json")
        git("remote", "set-url", "origin", gh_url)
        r0 = (as_json("\n".join(ln for ln in out.split("\n") if not ln.startswith("pr-gate:"))) or [{}])[0]
        check("a fork's clone: commits_known false and the counts null, never the fork's base's count",
              r0.get("commits_known") is False and r0.get("work_commits") is None, out)
        check("…and the reason is said: this clone's origin is not testorg/testrepo",
              "this clone's origin is not testorg/testrepo on github.com" in out and "git fetch origin failed" not in out, out)

        # An alias origin names the repository only once url.<x>.insteadOf resolves it, as gh.this_repo reads it;
        # the configured URL alone read "not testorg/testrepo" (review on #300, round 2). Asked in-process: the
        # alias resolves to github.com itself, which a gate run would fetch from.
        sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
        from github import landed
        alias = f"{sandbox}/alias"
        subprocess.run(["git", "init", "-q", alias], env=git_env(base_env), check=True, timeout=30)
        git("remote", "add", "origin", "gh:testorg/testrepo", cwd=alias)
        git("config", "url.git@github.com:.insteadOf", "gh:", cwd=alias)
        check("landed.origin_is: an alias origin (gh:testorg/testrepo) is testorg/testrepo, resolved through insteadOf",
              landed.origin_is("testorg/testrepo", alias) and not landed.origin_is("testorg/fork", alias))
        check("…and the routed GitHub URL of this clone still is, as configured",
              landed.origin_is("testorg/testrepo", repo))

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
        check("--overlap says that no shared path does not mean compatible",
              "no shared path is not the same as compatible" in out, out)
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
        # The branches are the clone's origin's: from another repository's clone they would be listed as
        # testorg/testrepo's, mostly as "no PR" (review on #300, round 2).
        git("remote", "set-url", "origin", fork_url)
        rcs = [run(*a) for a in (("--in-flight",), ("--overlap", "42"), ("--in-flight", "--json"))]
        git("remote", "set-url", "origin", gh_url)
        check("a fork's clone: --in-flight and --overlap refuse, exit 2, naming the clone, with no row",
              all(rc == 2 and "this clone's origin is not testorg/testrepo on github.com" in out
                  and "feat/parked" not in out and "in flight on" not in out for rc, out in rcs),
              "\n".join(f"rc={rc}\n{out}" for rc, out in rcs))
        route(f"{sandbox}/nowhere.git")
        rc, out = run("--in-flight", "--json")
        route(origin)
        check("a failed fetch is said first, fetch_ok false, exit 2 — the rows are marked as what origin last showed",
              rc == 2 and "git fetch origin failed" in out and has(r"at its last fetch \([0-9]{4}-", out)
              and '"fetch_ok": false' in out, f"rc={rc}\n{out}")

    print(f"\ntest_pr_gate_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
