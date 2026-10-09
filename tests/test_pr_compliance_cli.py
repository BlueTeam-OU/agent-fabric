#!/usr/bin/env python3
"""fabric-pr compliance, through the shim with gh mocked on PATH
and a scratch git history whose merge commits carry each pull request's
commits on their second parent. Ported case for case from a managed
project's tools/gh/test_pr-compliance.sh (its script the oracle, ADR-040
§5), but for its two cases about a classifier sourced from outside, which
the port has no longer: the fabric's commit_class runs in process, and
that it is told the pull request and the repository for every commit is
pinned here instead. Then what the port adds: the project's numbers from
compliance.json, owed-supply in process, a run count that cannot be read,
jq's rounding and jq's lines. Plain script: prints ok/FAIL, exit 1 on any
failure."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = [os.path.join(ROOT, "bin", "fabric-pr"), "compliance"]
GZAPP_CONFIG = os.path.join(ROOT, "tests", "fixtures", "gzapp-gh", "compliance.json")
REPO = "gzapi-org/gzapp"

# gh as gh.py calls it. State in $MOCK_STATE: merged.json (gh pr list
# --state merged), open.json (--state open, for owed-supply in process),
# branches.json, runs.json ({branch: count}), runs_fail (branches whose
# run list fails), fail (prs); calls (every call, appended).
GH = r'''#!@PYTHON@
import json, os, sys
S = os.environ["MOCK_STATE"]
args = sys.argv[1:]
with open(os.path.join(S, "calls"), "a", encoding="utf-8") as fh:
    fh.write(" ".join(args) + "\n")
def read(name, default=""):
    try:
        with open(os.path.join(S, name), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return default
def opt(name):
    return args[args.index(name) + 1] if name in args else ""
fail = read("fail").strip()
R = "repos/gzapi-org/gzapp"
if args[:2] == ["pr", "list"]:
    if opt("--state") == "merged":
        if fail == "prs":
            sys.exit(1)
        print(read("merged.json", "[]")); sys.exit(0)
    print(read("open.json", "[]")); sys.exit(0)
if args[:2] == ["run", "list"]:
    b = opt("--branch")
    if b in read("runs_fail").split():
        print("gh: Server Error (HTTP 502)", file=sys.stderr); sys.exit(1)
    # A count is that many runs inside the fixtures' window; a list names
    # each run's createdAt.
    v = json.loads(read("runs.json", "{}")).get(b, 0)
    at = v if isinstance(v, list) else ["2026-09-18T09:00:00Z"] * v
    print(json.dumps([{"databaseId": i, "createdAt": c} for i, c in enumerate(at)])); sys.exit(0)
if args[:1] == ["api"]:
    path = args[1]
    if path.startswith(R + "/branches?"):
        print(json.dumps([json.loads(read("branches.json", "[]"))])); sys.exit(0)
    if path == R:
        print('{"default_branch":"main"}'); sys.exit(0)
    if path.startswith(R + "/compare/"):
        print('{"behind_by":3}'); sys.exit(0)
    if path.startswith(R + "/commits/"):
        print(json.dumps({"commit": {"committer": {"date": "2026-01-01T00:00:00Z"}}})); sys.exit(0)
print("mock gh: unhandled: " + " ".join(args), file=sys.stderr)
sys.exit(1)
'''


# owed-supply --json, as supply.json says; supply_fail makes it refuse.
STUB = r'''#!/usr/bin/env bash
[[ -f "$MOCK_STATE/supply_fail" ]] && { echo "owed-supply: gh is required" >&2; exit 2; }
printf '%s\n' "$(<"$MOCK_STATE/supply.json")"
'''


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as sandbox:
        bin_, state, repo = (os.path.join(sandbox, d) for d in ("bin", "state", "repo"))
        for d in (bin_, state, repo):
            os.makedirs(d)
        # git runs in a scratch identity: its own HOME and no global or
        # system config, nothing of the runner's GIT_* — the fixture's
        # calls and the tool's alike.
        genv = {k: v for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_", "GH_", "GIT_"))}
        genv.update(HOME=sandbox, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", LC_ALL="C")

        def git(*args: str) -> str:
            r = subprocess.run(["git", "-C", repo, *args], env=genv, capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                raise RuntimeError(f"fixture git {args}: {r.stderr}")
            return r.stdout.strip()

        git("init", "-q", "-b", "main")
        for k, v in (("user.email", "t@t"), ("user.name", "t"), ("commit.gpgsign", "false")):
            git("config", k, v)
        with open(os.path.join(repo, "f"), "w") as fh:
            fh.write("a\n")
        git("add", "f")
        git("commit", "-q", "-m", "base")
        seq = [0]

        def mk_pr(branch: str, *subjects: str, revert_last: bool = False) -> str:
            git("checkout", "-q", "-b", branch, "main")
            for s in subjects:
                seq[0] += 1
                with open(os.path.join(repo, branch.replace("/", "_") + ".txt"), "a") as fh:
                    fh.write(f"{s}{seq[0]}\n")
                git("add", "-A")
                git("commit", "-q", "-m", s)
            if revert_last:
                git("revert", "--no-edit", "HEAD")
            git("checkout", "-q", "main")
            git("merge", "-q", "--no-ff", "-m", f"Merge pull request from {branch}", branch)
            return git("rev-parse", "HEAD")

        mc1 = mk_pr("pr-1", "feat: one", "feat: two", "review F1: the nit")
        mc2 = mk_pr("pr-2", *[f"w{i}" for i in range(1, 10)])
        mc3 = mk_pr("pr-3", "i18n: copy")
        mc5 = mk_pr("pr-5", "feat: kept", "feat: dropped", revert_last=True)
        mc7 = mk_pr("pr-7", "feat: x", "review fix (#7 F1): the nit")

        with open(os.path.join(bin_, "gh"), "w", encoding="utf-8") as fh:
            fh.write(GH.replace("@PYTHON@", sys.executable))
        os.chmod(os.path.join(bin_, "gh"), 0o755)
        stub = os.path.join(bin_, "owed-supply-stub.sh")
        with open(stub, "w", encoding="utf-8") as fh:
            # Builtins only: PATH holds no cat.
            fh.write(STUB)
        os.chmod(stub, 0o755)
        for tool in ("bash", "git", "dirname", "readlink"):
            os.symlink(shutil.which(tool), os.path.join(bin_, tool))
        # PATH is the sandbox alone (bash, git, the mock gh): no jq.
        base = dict(genv, PATH=bin_, MOCK_STATE=state, GH_REPO=REPO, AGENT_FABRIC_COMPLIANCE_CONFIG=GZAPP_CONFIG,
                    AGENT_FABRIC_OWED_SUPPLY=stub)
        if os.environ.get("AGENT_FABRIC_PYTHON"):
            base["AGENT_FABRIC_PYTHON"] = os.environ["AGENT_FABRIC_PYTHON"]
        out = {"text": "", "rc": -1, "stdout": "", "stderr": ""}

        def put(name: str, text: str) -> None:
            with open(os.path.join(state, name), "w", encoding="utf-8") as fh:
                fh.write(text)

        def drop(name: str) -> None:
            if os.path.exists(os.path.join(state, name)):
                os.remove(os.path.join(state, name))

        def run(*args: str, unset: tuple[str, ...] = (), **env: str) -> None:
            e = {k: v for k, v in dict(base, **env).items() if k not in unset}
            r = subprocess.run([*TOOL, *args], env=e, cwd=repo, capture_output=True, text=True, timeout=300)
            out.update(text=r.stdout + r.stderr, rc=r.returncode, stdout=r.stdout, stderr=r.stderr)

        def doc() -> dict:
            try:
                return json.loads(out["stdout"])
            except ValueError:
                return {}

        def has(label: str, text: str, rc: int | None = 0) -> None:
            check(label, (rc is None or out["rc"] == rc) and text in out["text"],
                  f"want exit {rc} and {text!r}; got exit {out['rc']}\n{out['text']}")

        def lacks(label: str, text: str) -> None:
            check(label, text not in out["text"], f"output unexpectedly contained {text!r}\n{out['text']}")

        def line(prefix: str) -> str:
            return next((l for l in out["stdout"].splitlines() if l.startswith(prefix)), "")

        def pr(num: int, title: str, branch: str, mc: str, body: str = "plain", files: tuple = ("src/a.cs",),
               comments: tuple = ()) -> dict:
            return {"number": num, "title": title, "headRefName": branch, "baseRefName": "main",
                    "createdAt": "2026-09-17T10:00:00Z", "mergedAt": "2026-09-18T10:00:00Z", "mergeCommit": {"oid": mc}, "body": body,
                    "files": [{"path": f} for f in files], "comments": [{"body": c} for c in comments]}

        four = [pr(1, "two work and a review fix, no basis", "pr-1", mc1, files=("src/a.cs", "product/i18n/en-US.json")),
                pr(2, "nine work commits", "pr-2", mc2, files=("src/b.cs",),
                   comments=("Arming basis: the owner approved this one — 9 work commits, head abcdef01.",)),
                pr(3, "i18n only, with the owner's word", "pr-3", mc3, body="Opened on the owner's word — one dictionary.",
                   files=("product/i18n/ka-GE.json", "product/i18n/ru-RU.json")),
                pr(4, "armed by arm.sh", "pr-1", mc1, files=("src/c.cs",),
                   comments=("Arming basis: the owner approved this one — 2 work commits, head abcdef01.",))]
        put("merged.json", json.dumps(four))
        put("runs.json", json.dumps({"pr-1": 4, "pr-2": 2, "pr-3": 1}))
        put("supply.json", json.dumps({"owed": [{"branch": "h/s/for/c/old", "past_default_fold_by": True},
                                                {"branch": "h/s/for/c/new", "past_default_fold_by": False}],
                                       "landed": [], "awaiting": [{"number": 42, "awaiting_supply": ["db-admin"]}]}))

        print("pr-compliance: the four measures over three merged PRs")
        run("--days", "3")
        check("exits 0", out["rc"] == 0, out["text"])
        check("#1: 4 runs, the review fix counted apart, NONE, not i18n-only (one file outside)",
              line("  #1 ").split()[:9] == ["#1", "4", "2", "work,", "1", "fix,", "0", "merge", "NONE"]
              and line("  #1 ").split()[9] == "-", out["text"])
        check("#2: at 9 work commits the exemption column is n/a",
              line("  #2 ").split()[:9] == ["#2", "2", "9", "work,", "0", "fix,", "0", "merge", "n/a"], out["text"])
        check("#3: the owner's word is stated; every file under product/i18n/ is ONLY",
              line("  #3 ").split()[:10] == ["#3", "1", "1", "work,", "0", "fix,", "0", "merge", "stated", "ONLY"],
              out["text"])
        has("runs per PR averaged, the ones over 2 named",
            "pull_request runs per merged PR: 2.75 (target 2; 11 runs over 4 PR(s); over target: #1 #4)\n")
        has("under the floor with nothing stated: #1 only — #4's \"Arming basis:\" comment counts as stated",
            "under 8 work commits with no exemption stated: #1\n")
        has("i18n-only counted with the PR named",
            "standalone i18n-only PRs: 1 (#3) (target 0 — copy goes onto the caller's branch)\n")
        has("only the branch past the default FOLD-BY is listed", "supply branches past the default FOLD-BY: h/s/for/c/old\n")
        has("awaiting PRs pass through from owed-supply", "open PRs awaiting a AWAITING-SUPPLY: #42\n")
        check("the header and the first line are the bash's",
              out["stdout"].startswith(f"pr-compliance: 4 pull request(s) merged on {REPO} in the last 3 day(s) (since ")
              and "\n  PR     RUNS  COMMITS                EXEMPT    I18N      TITLE\n" in out["stdout"], out["stdout"])
        check("the run counts were asked of the project's workflow, on each head branch",
              "run list --repo gzapi-org/gzapp --workflow ci.yml --event pull_request --branch pr-1 --limit 100 "
              "--json databaseId" in open(os.path.join(state, "calls"), encoding="utf-8").read())

        print("pr-compliance: --json is the same data")
        run("--days", "3", "--json")
        d = doc()
        check("summary fields", [d.get("merged"), (d.get("pull_request_runs") or {}).get("per_pr"),
                                 d.get("under_floor_unstated"), d.get("i18n_only"), d.get("supply_past_fold_by"),
                                 d.get("awaiting_supply")] == [4, 2.75, [1], [3], ["h/s/for/c/old"], [42]], out["text"])
        one = next((r for r in d.get("prs", []) if r.get("number") == 1), {})
        check("per-PR fields", [one.get(k) for k in ("work_commits", "fix_commits", "exemption_stated", "i18n_only",
                                                       "under_floor_unstated")] == [2, 1, False, False, True], out["text"])
        # The bash's keys, in its order, and the two the scoped count added
        # (devex-tooling, 2026-10-08): each one beside the count it qualifies.
        check("the keys are the bash's, in its order, with the lower-bound flags", list(d) == [
            "window_days", "since", "origin_fetched", "merged", "pull_request_runs", "under_floor_unstated", "i18n_only",
            "supply_past_fold_by", "awaiting_supply", "prs"] and list(d["pull_request_runs"]) == [
            "known", "total", "per_pr", "lower_bound", "over_target"] and list(one) == [
            "number", "title", "branch", "merged_at", "pull_request_runs", "pull_request_runs_lower_bound", "work_commits",
            "fix_commits", "merge_commits", "netted_commits", "commits_known", "exemption_stated", "bot", "i18n_only",
            "under_floor_unstated"] and d.get("window_days") == 3, out["stdout"][:400])
        check("--json is stdout alone, indented as jq printed it",
              out["stdout"].startswith('{\n  "window_days": 3,\n') and "git fetch" not in out["stdout"], out["stdout"][:200])

        print("pr-compliance: a failed fetch is said, never silent")
        run("--days", "3")
        check("failed fetch: said on stderr, the measure still runs",
              out["rc"] == 0 and "pr-compliance: git fetch origin failed — commit counts come from the origin this clone "
              "last fetched and may be stale; a merge commit it never saw reads 'unknown'\n" == out["stderr"], out["text"])
        run("--days", "3", "--json")
        check("--json carries origin_fetched: false", doc().get("origin_fetched") is False, out["text"])
        subprocess.run(["git", "clone", "-q", "--bare", repo, os.path.join(sandbox, "origin.git")], env=genv,
                       capture_output=True, timeout=60, check=True)
        git("remote", "add", "origin", os.path.join(sandbox, "origin.git"))
        run("--days", "3")
        check("a working fetch: nothing said", out["rc"] == 0 and out["stderr"] == "", out["text"])
        run("--days", "3", "--json")
        check("--json carries origin_fetched: true", doc().get("origin_fetched") is True, out["text"])
        git("remote", "remove", "origin")

        print("pr-compliance: the classifier is told the PR and the repository, for every commit")
        put("merged.json", json.dumps([pr(7, "answers its own review", "pr-7", mc7),
                                       pr(8, "carries #7's review fix", "pr-7", mc7)]))
        run("--days", "3", "--json")
        split = {r["number"]: (r["work_commits"], r["fix_commits"]) for r in doc().get("prs", [])}
        check("a commit answering THIS PR's review is a fix; one answering ANOTHER PR's review is work",
              split == {7: (1, 1), 8: (2, 0)}, out["text"])
        sys.path.insert(0, os.path.join(ROOT, "tools", "fabric", "github"))
        sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
        import pr_compliance
        # The classifier pr_gate imports, the one the split calls.
        commit_class = pr_compliance.pr_gate.commit_class
        asked: list[tuple] = []
        looks: list = []
        real = commit_class.classify

        def spy(parents: str, subject: str, answers: str = "", num: str = "", repo_: str = "", kind: str = "",
                folded=None) -> str:
            asked.append((subject, num, repo_))
            looks.append(folded)
            return real(parents, subject, answers, num, repo_, kind, folded)
        commit_class.classify = spy
        cwd = os.getcwd()
        saved_env = dict(os.environ)
        try:
            os.chdir(repo)
            os.environ.clear()
            os.environ.update(genv)
            pr_compliance.commit_split(1, REPO, mc1)
        finally:
            os.chdir(cwd)
            os.environ.clear()
            os.environ.update(saved_env)
            commit_class.classify = real
        check("…each of #1's three commits was classed with PR 1 and the repository",
              sorted(asked) == sorted([("feat: one", "1", REPO), ("feat: two", "1", REPO),
                                       ("review F1: the nit", "1", REPO)]), repr(asked))
        # The range is <merge>^1..<merge>^2: fold reading needs that head and
        # that base, or it is silently off and every count above still holds.
        check("…with fold reading on <merge>^2 over the base <merge>^1",
              bool(looks) and all(isinstance(f, commit_class.Folds) and f.head == f"{mc1}^2"
                                  and f.base == f"{mc1}^1" for f in looks),
              repr([(getattr(f, "head", f), getattr(f, "base", None)) for f in looks]))

        print("pr-compliance: an unfetched merge commit is 'unknown', not a crash or a zero")
        gone = dict(four[0], mergeCommit={"oid": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"})
        put("merged.json", json.dumps([gone] + four[1:]))
        run("--days", "3")
        check("commits unknown, said", out["rc"] == 0 and line("  #1 ").split()[:4] == ["#1", "4", "unknown", "(fetch)"],
              out["text"])
        has("…and an unknown count is not counted under the floor", "under 8 work commits with no exemption stated: none\n")
        put("merged.json", json.dumps([dict(four[0], mergeCommit=None), dict(four[1], mergeCommit={"oid": "not-a-revision"}),
                                       dict(four[2], mergeCommit={"oid": git("rev-list", "--max-parents=0", "main")})]))
        run("--days", "3", "--json")
        check("no merge commit, a bad one, or one with no second parent: unknown each",
              [r["commits_known"] for r in doc().get("prs", [])] == [False, False, False], out["text"])

        print("pr-compliance: a revert and the commit it reverts net to nothing, as pr-gate nets them")
        put("merged.json", json.dumps([pr(5, "a revert of its own commit", "pr-5", mc5, files=("src/d.cs",))]))
        run("--days", "3", "--json")
        p5 = (doc().get("prs") or [{}])[0]
        check("feat + feat + revert of the second: 1 work, 2 netted (not 3 work)",
              (p5.get("work_commits"), p5.get("fix_commits"), p5.get("netted_commits")) == (1, 0, 2), out["text"])
        run("--days", "3")
        row5, hdr = line("  #5 "), line("  PR ")
        check("…and the row says it", "1 work, 0 fix, 0 merge, 2 netted" in row5, out["text"])
        check("…and its EXEMPT cell stays under the EXEMPT header", hdr.find("EXEMPT") == row5.find("NONE") > 0,
              hdr + "\n" + row5)

        print("pr-compliance: a Dependabot PR is a bot, not a session's PR under the floor")
        put("merged.json", json.dumps([
            pr(6, "chore(deps): bump x", "dependabot/npm_and_yarn/x-1.2.3", mc3, body="Bumps x.", files=("pnpm-lock.yaml",)),
            pr(7, "a session PR, one work commit", "h/s/fix/y", mc3, files=("src/y.cs",))]))
        run("--days", "3")
        check("#6 (dependabot/…): the EXEMPT column says bot", line("  #6 ").split()[8:9] == ["bot"], out["text"])
        has("…and only the session's PR is listed under the floor", "under 8 work commits with no exemption stated: #7\n")
        run("--days", "3", "--json")
        check("…and --json carries bot per PR",
              [(r["number"], r["bot"]) for r in doc().get("prs", [])] == [(6, True), (7, False)], out["text"])

        print("pr-compliance: a pull request with no head branch is an unknown count, never the unfiltered one")
        put("merged.json", json.dumps([dict(four[0], headRefName="")]))
        put("runs.json", json.dumps({"": 7}))
        run("--days", "3", "--json")
        check("no headRefName: null, where gh would have counted 7 unfiltered runs",
              [r["pull_request_runs"] for r in doc().get("prs", [])] == [None], out["text"])
        put("runs.json", json.dumps({"pr-1": 4, "pr-2": 2, "pr-3": 1}))

        print("pr-compliance: a pull request's runs are its own: on its branch, while it was open")
        reused = [dict(four[0], createdAt="2026-09-10T00:00:00Z", mergedAt="2026-09-11T00:00:00Z"),
                  dict(four[3], createdAt="2026-09-17T00:00:00Z", mergedAt="2026-09-18T00:00:00Z")]
        put("merged.json", json.dumps(reused))
        put("runs.json", json.dumps({"pr-1": ["2026-09-10T01:00:00Z", "2026-09-17T01:00:00Z", "2026-09-17T02:00:00Z",
                                              "2026-09-19T00:00:00Z", "2026-09-01T00:00:00Z"]}))
        run("--days", "3", "--json")
        check("two PRs on one branch name: one run and two, not five each",
              [r["pull_request_runs"] for r in doc().get("prs", [])] == [1, 2], out["text"])
        put("merged.json", json.dumps([dict(four[0], createdAt=None)]))
        run("--days", "3", "--json")
        check("no createdAt: no window, so an unknown count", [r["pull_request_runs"] for r in doc().get("prs", [])] == [None],
              out["text"])
        put("merged.json", json.dumps([four[0], four[1]]))
        put("runs.json", json.dumps({"pr-1": 100, "pr-2": 2}))
        run("--days", "3")
        check("a full read is a lower bound in its row", line("  #1 ").split()[1] == "100+", out["text"])
        has("…and in the aggregate", "pull_request runs per merged PR: ≥51 (target 2; ≥102 runs over 2 PR(s); over target: #1)\n")
        run("--days", "3", "--json")
        check("…and in --json", doc()["pull_request_runs"]["lower_bound"] is True
              and [r["pull_request_runs_lower_bound"] for r in doc()["prs"]] == [True, False], out["text"])
        put("runs.json", json.dumps({"pr-1": 4, "pr-2": 2, "pr-3": 1}))

        print("pr-compliance: the empty window is said; a failing gh is exit 2")
        put("merged.json", "[]")
        run("--days", "1")
        has("no merged PR: said", "pr-compliance: 0 pull request(s) merged on")
        lacks("…with no table", "  PR ")
        has("…and the runs measure is unknown, not zero", "pull_request runs per merged PR: unknown (target 2; 0 runs over 0 PR(s);"
            " over target: none)")
        put("fail", "prs")
        run()
        has("pr list failing: exit 2", "pr-compliance: could not list merged pull requests", rc=2)
        drop("fail")
        for bad in (["--days", "0"], ["--days", "x"], ["--days"], ["--days", "-3"], ["--days", "٣"]):
            run(*bad)
            has(f"--days {bad[1:]!r} is refused", "pr-compliance: --days needs a whole number of 1 or more", rc=2)
        run("--days", "03")
        has("--days 03 is 3 days, printed as written", "in the last 03 day(s)")
        run("--bogus")
        has("an unknown option is refused", "pr-compliance: unknown option '--bogus' (try --help)", rc=2)
        run("--help")
        check("--help is the docstring, naming no project's literals",
              out["rc"] == 0 and out["stdout"].startswith("fabric-pr compliance [--days N] [--json]")
              and "compliance.json" in out["stdout"] and "product/i18n" not in out["stdout"]
              and "#886" not in out["stdout"], out["text"])

        print("pr-compliance: what the port decides that the bash did not")
        put("merged.json", json.dumps(four))
        put("runs_fail", "pr-2 pr-3\n")
        run("--days", "3")
        check("a run count that cannot be read is '?'", line("  #2 ").split()[1] == "?", out["text"])
        has("…and is never counted as zero: the mean is over the PRs it could read",
            "pull_request runs per merged PR: 4 (target 2; 8 runs over 2 PR(s); over target: #1 #4)\n")
        run("--days", "3", "--json")
        check("…and is null in --json", [r["pull_request_runs"] for r in doc().get("prs", [])] == [4, None, None, 4]
              and doc()["pull_request_runs"]["per_pr"] == 4, out["text"])
        drop("runs_fail")
        cfg = json.load(open(GZAPP_CONFIG, encoding="utf-8"))
        other = os.path.join(sandbox, "other.json")
        with open(other, "w", encoding="utf-8") as fh:
            json.dump(dict(cfg, workflow="build.yml", floor=2, runs_target=3, i18n_prefix=None, bot_prefix="h/"), fh)
        run("--days", "3", AGENT_FABRIC_COMPLIANCE_CONFIG=other)
        has("the floor printed is the project's", "under 2 work commits with no exemption stated: none\n")
        has("…and so is the runs target", "(target 3; 11 runs over 4 PR(s); over target: #1 #4)\n")
        lacks("a null i18n_prefix drops the i18n line", "standalone i18n-only")
        check("…and the I18N column", line("  PR ").split() == ["PR", "RUNS", "COMMITS", "EXEMPT", "TITLE"], out["text"])
        check("the workflow asked is the project's", "--workflow build.yml" in open(os.path.join(state, "calls")).read())
        quiet = {k: v for k, v in cfg.items() if k != "i18n_target_note"}
        quiet_path = os.path.join(sandbox, "quiet.json")
        with open(quiet_path, "w", encoding="utf-8") as fh:
            json.dump(quiet, fh)
        run("--days", "3", AGENT_FABRIC_COMPLIANCE_CONFIG=quiet_path)
        has("a project with no i18n_target_note gets the count alone, never another's policy",
            "standalone i18n-only PRs: 1 (#3)\n")
        run("--days", "3", AGENT_FABRIC_COMPLIANCE_CONFIG=os.path.join(sandbox, "none.json"))
        has("a project with no compliance.json: exit 2, before anything is read",
            f"pr-compliance: this project declares no compliance.json ({sandbox}/none.json)", rc=2)
        for broken, why in (({**cfg, "floor": 0}, "floor"), ({**cfg, "exemption": "("}, "error"),
                            ({k: v for k, v in cfg.items() if k != "workflow"}, "KeyError"), ("[]", "TypeError")):
            with open(other, "w", encoding="utf-8") as fh:
                fh.write(broken if isinstance(broken, str) else json.dumps(broken))
            run("--days", "3", AGENT_FABRIC_COMPLIANCE_CONFIG=other)
            has(f"a compliance.json that is not usable ({why}): exit 2", "is not a usable compliance.json", rc=2)
        run("--days", "3", unset=("AGENT_FABRIC_COMPLIANCE_CONFIG",))
        has("a working copy no project claims, with no override: exit 2",
            "pr-compliance: no project found for this working copy, so no compliance.json", rc=2)
        run("--days", "3", unset=("GH_REPO",))
        has("no GH_REPO and no github.com origin: the repository cannot be read",
            "pr-compliance: cannot read the repository: ", rc=2)
        put("supply_fail", "")
        run("--days", "3")
        has("owed-supply failing: exit 2, with its line", "pr-compliance: owed-supply could not run: owed-supply: gh is required",
            rc=2)
        lacks("…and no measure printed", "pull request(s) merged")
        drop("supply_fail")
        put("branches.json", json.dumps([{"name": "h/sx/for/cx/w", "commit": {"sha": "a" * 40}}]))
        put("open.json", json.dumps([{"number": 9, "headRefName": "h/a/feat/x", "headRefOid": "b" * 40, "title": "t",
                                      "body": "AWAITING-SUPPLY: dx"}]))
        run("--days", "3", unset=("AGENT_FABRIC_OWED_SUPPLY",))
        has("with no seam, owed-supply runs in process: its past-FOLD-BY branch", "supply branches past the default FOLD-BY:"
            " h/sx/for/cx/w\n")
        has("…and its awaiting PR", "open PRs awaiting a AWAITING-SUPPLY: #9\n")
        title = "tab\there, back\\slash, half \ud800 a pair, and a title well past sixty characters long"
        put("merged.json", json.dumps([pr(1, title, "pr-1", mc1)]))
        run("--days", "3")
        check("a title is GitHub's: a tab and a backslash carried, a lone surrogate replaced, cut at 60",
              line("  #1 ").endswith(" " + title.replace("\ud800", "\ufffd")[:60]), line("  #1 "))
        os.remove(os.path.join(bin_, "git"))
        run("--days", "3")
        has("no git: exit 2", "pr-compliance: git is required", rc=2)

    print("pr-compliance: jq's round, in process")
    check("half away from zero, an integral mean an int",
          pr_compliance.per_pr(1, 8) == 0.13 and pr_compliance.per_pr(11, 4) == 2.75
          and pr_compliance.per_pr(6, 2) == 3 and type(pr_compliance.per_pr(6, 2)) is int
          and pr_compliance.per_pr(0, 0) is None)

    print(f"\ntest_pr_compliance_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
