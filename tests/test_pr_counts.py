#!/usr/bin/env python3
"""tools/fabric/github/pr_counts.py (fabric-pr counts): the counts equal the
gate's for the same commits, refs resolve through the registry, every line
shape, and every way a ref fails to be read. GitHub is a fake `gh.graphql` and
`gh.api` over fixtures; the parity cases build a real repository and answer the
query from its log. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import gh  # noqa: E402
from github import pr_counts, pr_split  # noqa: E402

REGISTRY = {
    "gzapp": {"remotes": ["git@github.com:gzapi-org/gzapp.git", "https://github.com/gzapi-org/gzapp"]},
    "gzapp.decks": {"remotes": ["git@github.com:gzapi-org/gzapp.decks.git"]},
    "interweave": {"remotes": ["git@github.com:gzapi-org/InterWeave.git"]},
    "herdr": {"remotes": ["git@github.com:BlueTeam-OU/agent-fabric-herdr.git"]},
    "agent-fabric": {"remotes": ["git@github.com:BlueTeam-OU/agent-fabric.git", "git@github.com:gzapi-org/agent-fabric.git"]},
    "twin-a": {"remotes": ["git@github.com:o/same.git"]},
    "twin-b": {"remotes": ["git@github.com:p/same.git"]},
    "no-remote": {"remotes": []},
}


def load_registry() -> dict:
    return REGISTRY


def commit(oid: str, message: str, parents: int = 1) -> dict:
    return {"commit": {"oid": oid, "message": message, "parents": {"totalCount": parents}}}


def pr_doc(number: int, commits: list, *, state: str = "OPEN", draft: bool = False, merged: bool = False, armed: bool = False,
           queued: bool = False, rollup: str | None = "SUCCESS", head: str = "h" * 40, reviews: list | None = None,
           more: bool = False) -> dict:
    return {"number": number, "state": state, "isDraft": draft, "mergedAt": "2026-10-10T00:00:00Z" if merged else None,
            "headRefOid": head, "baseRefName": "main",
            "mergeCommit": {"parents": {"nodes": [{"oid": "b" * 40}, {"oid": head}]}} if merged else None,
            "autoMergeRequest": {"enabledAt": "x"} if armed else None, "mergeQueueEntry": {"state": "QUEUED"} if queued else None,
            "commits": {"totalCount": len(commits), "pageInfo": {"hasNextPage": more}, "nodes": commits},
            "tip": {"nodes": [{"commit": {"statusCheckRollup": {"state": rollup} if rollup else None}}]},
            "reviews": {"nodes": reviews or []}}


class Hub:
    """gh.graphql and gh.api as fixtures: repos[owner/name][number] -> a PR document."""

    def __init__(self, repos: dict, rest: dict | None = None, fail_batches: bool = False):
        self.repos, self.rest, self.graphql_calls, self.api_calls, self.fail_batches = repos, rest or {}, [], [], fail_batches

    def graphql(self, query, *, timeout=None, **variables):
        numbers = [int(n) for n in re.findall(r"\bp(\d+): pullRequest", query)]
        repo = f"{variables['owner']}/{variables['name']}"
        self.graphql_calls.append((repo, numbers, timeout))
        if repo not in self.repos:
            raise gh.GhError("gh api graphql", f"Could not resolve to a Repository with the name '{repo}'.")
        known = self.repos[repo]
        if any(n not in known for n in numbers):
            raise gh.GhError("gh api graphql", f"Could not resolve to a PullRequest with the number of {[n for n in numbers if n not in known][0]}.")
        if self.fail_batches and len(numbers) > 1:
            raise gh.GhError("gh api graphql", "something broke in the batch")
        return {"repository": {f"p{n}": known[n] for n in numbers}}

    def api(self, path, *, paginate=False, timeout=None, **kw):
        self.api_calls.append(path)
        if path in self.rest:
            return self.rest[path]
        raise gh.GhError("gh api", "HTTP 404")


# The arming policies a line is read under, modelled here: the live fleet file and settings repositories change
# what the engines are, and a count's test must not follow them (#242's platform-smoke).
BOTH = pr_counts.arm_policy.validate({"reviews": ["claude", "codex"], "boundary_reviews": ["claude", "codex"], "additional_reviews": []})
CLAUDE = pr_counts.arm_policy.validate({"reviews": ["claude"], "boundary_reviews": ["claude"], "additional_reviews": []})


def run_counts(refs: list[str], hub: Hub, timeout: float = 20.0, cwd_repo: str = "o/this", policy=BOTH) -> list[dict]:
    """count_rows over `hub`, every repository's arming policy `policy`: a document, or a loader (repo, **kw)."""
    saved = (gh.graphql, gh.api, gh.this_repo, pr_counts.arm_policy.load)
    gh.graphql, gh.api, gh.this_repo = hub.graphql, hub.api, lambda cwd=None: cwd_repo
    pr_counts.arm_policy.load = policy if callable(policy) else (lambda repo, **kw: policy)
    try:
        return pr_counts.count_rows(refs, timeout, projects_loader=load_registry)
    finally:
        gh.graphql, gh.api, gh.this_repo, pr_counts.arm_policy.load = saved


def git_fixture() -> tuple[str, str, list[str]]:
    """(repo dir, base sha, the commits' shas oldest first): plain work, a
    declared fix, an Answers: fix, a revert pair, a merge."""
    repo = tempfile.mkdtemp(prefix="test_pr_counts.")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True).stdout.strip()

    def make(n: int, *msg: str) -> str:
        with open(os.path.join(repo, f"f{n}"), "w") as fh:
            fh.write(str(n))
        git("add", "-A")
        git("commit", "-q", *[a for m in msg for a in ("-m", m)])
        return git("rev-parse", "HEAD")

    git("init", "-q", "-b", "main")
    base = make(0, "base")
    git("checkout", "-q", "-b", "feat")
    shas = [make(1, "first piece", "Kind: work"),
            make(2, "tidy the probe", "Answers: F1"),
            make(3, "review fix (#7 F2): the probe", "Kind: review-fix"),
            make(8, "plain subject, declared fix", "Kind: review-fix"),
            make(9, "review fix (#7 F3): reads as a fix, declared work", "Kind: work"),
            make(4, "a change later undone", "Kind: work")]
    git("revert", "--no-edit", shas[-1])
    shas.append(git("rev-parse", "HEAD"))
    # A chain: feature B, its revert, the revert reverted. The reapply nets the
    # revert and B stays work; walked oldest first the revert would net B instead.
    shas.append(make(6, "feature B", "Kind: work"))
    git("revert", "--no-edit", shas[-1])
    shas.append(git("rev-parse", "HEAD"))
    git("revert", "--no-edit", shas[-1])
    shas.append(git("rev-parse", "HEAD"))
    git("checkout", "-q", "main")
    make(5, "main moves")
    git("checkout", "-q", "feat")
    git("merge", "-q", "--no-ff", "-m", "Merge main into feat", "main")
    shas.append(git("rev-parse", "HEAD"))
    return repo, base, shas


def api_commits(repo: str, base: str, head: str) -> list:
    """What GitHub's commit list for base..head says, from the clone's log, oldest first."""
    out = subprocess.run(["git", "log", "--reverse", "--format=%H%x00%P%x00%B%x01", f"{base}..{head}"], cwd=repo,
                         capture_output=True, text=True, check=True).stdout
    nodes = []
    for rec in out.split("\x01"):
        rec = rec.strip("\n")
        if rec:
            sha, parents, message = rec.split("\x00", 2)
            nodes.append(commit(sha, message.rstrip("\n"), len(parents.split())))
    return nodes


def main() -> int:
    fails = 0
    cleanup: list[str] = []

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail!r}"))
        fails += not good

    print("the counts are the gate's")
    repo, base, shas = git_fixture()
    saved_cwd = os.getcwd()
    cleanup.append(repo)
    os.chdir(repo)
    try:
        want = pr_split.split_range(7, "o/this", f"{base}..{shas[-1]}", shas[-1], base)
    finally:
        os.chdir(saved_cwd)
    hub = Hub({"o/this": {7: pr_doc(7, api_commits(repo, base, shas[-1]), head=shas[-1])}})
    row = run_counts(["7"], hub)[0]
    check("the clone's split is 4 work, 3 fix, 1 merge, 4 netted (the fixture is not trivial)",
          (want["work"], want["fix"], want["merge"], want["netted"]) == (4, 3, 1, 4), want)
    check("GitHub's commit list gives the same split: work, fix, merge and netted",
          (row["work"], row["fix"], row["merge"], row["netted"]) == (want["work"], want["fix"], want["merge"], want["netted"]), row)
    check("…and nets the same commits: which of a chain's three is netted shows in the subjects",
          (sorted(row["fix_subjects"]), sorted(row["netted_subjects"])) == (sorted(want["fix_subjects"]), sorted(want["netted_subjects"])),
          (row.get("fix_subjects"), row.get("netted_subjects"), want["netted_subjects"]))
    check("the line says it, in the hook's words", row["line"].startswith("#7 (4 work, 3 fix) open, unarmed, checks green"), row["line"])

    print("the line, by state")
    docs = {
        1: pr_doc(1, [commit("a" * 40, "x")], armed=True, rollup="PENDING", reviews=[{"body": "<!-- agent-fabric-review v1 -->\nok", "commit": {"oid": "h" * 40}}]),
        2: pr_doc(2, [commit("b" * 40, "x"), commit("c" * 40, "y", parents=2)], rollup="FAILURE"),
        3: pr_doc(3, [commit("d" * 40, "x")], state="MERGED", merged=True),
        4: pr_doc(4, [commit("e" * 40, "x")], state="CLOSED"),
        5: pr_doc(5, [commit("f" * 40, "x")], draft=True, queued=True, rollup=None),
        6: pr_doc(6, [commit("1" * 40, "x")], reviews=[{"body": "<!-- agent-fabric-review v1 -->", "commit": {"oid": "z" * 40}}]),
        8: pr_doc(8, [commit("2" * 40, "x")], rollup="ERROR"),
        9: pr_doc(9, [commit("3" * 40, "x")], rollup="EXPECTED"),
    }
    rows = {r["number"]: r for r in run_counts([str(n) for n in docs], Hub({"o/this": docs}))}
    check("open, armed, pending, a marked review on the head", rows[1]["line"] == "#1 (1 work, 0 fix) open, armed, checks pending, review claude ✓ codex ✗ (head hhhhhhhh)", rows[1]["line"])
    check("open, unarmed, red, a merge commit is not work", rows[2]["line"] == "#2 (1 work, 0 fix) open, unarmed, checks red, review claude ✗ codex ✗ (head hhhhhhhh)", rows[2]["line"])
    check("merged says only merged", rows[3]["line"] == "#3 (1 work, 0 fix) merged", rows[3]["line"])
    check("closed unmerged says closed", rows[4]["line"] == "#4 (1 work, 0 fix) closed", rows[4]["line"])
    check("a draft, queued, no checks yet", rows[5]["line"] == "#5 (1 work, 0 fix) draft, queued, checks none yet, review claude ✗ codex ✗ (head hhhhhhhh)", rows[5]["line"])
    check("a review on another commit than the head is not the head's", "review claude ✗ codex ✗" in rows[6]["line"], rows[6]["line"])
    check("ERROR reads red, EXPECTED pending", "checks red" in rows[8]["line"] and "checks pending" in rows[9]["line"], (rows[8]["line"], rows[9]["line"]))
    saved = (gh.graphql, gh.api, gh.this_repo, pr_counts.arm_policy.load)
    h = Hub({"o/this": docs})
    gh.graphql, gh.api, gh.this_repo = h.graphql, h.api, lambda cwd=None: "o/this"
    pr_counts.arm_policy.load = lambda repo, **kw: BOTH
    try:
        lines = pr_counts.count_lines(["3", "#1"], 5)
    finally:
        gh.graphql, gh.api, gh.this_repo, pr_counts.arm_policy.load = saved
    check("…also by `#N`", lines == ["#3 (1 work, 0 fix) merged", "#1 (1 work, 0 fix) open, armed, checks pending, review claude ✓ codex ✗ (head hhhhhhhh)"], lines)

    print("each required engine's review of the head (REQUEST 01a13693)")
    claude_r = {"body": "<!-- agent-fabric-review v1 -->\n<!-- model: fable -->\nok", "commit": {"oid": "h" * 40}}
    codex_r = {"body": "<!-- agent-fabric-review v1 -->\n<!-- model: codex -->\nok", "commit": {"oid": "h" * 40}}
    by = {"claude only": [claude_r], "codex only": [codex_r], "both": [claude_r, codex_r], "neither": []}
    want = {("both", "claude only"): "review claude ✓ codex ✗", ("both", "codex only"): "review claude ✗ codex ✓",
            ("both", "both"): "head reviewed: claude ✓ codex ✓", ("both", "neither"): "review claude ✗ codex ✗",
            ("claude", "claude only"): "head reviewed: claude ✓", ("claude", "codex only"): "review claude ✗",
            ("claude", "both"): "head reviewed: claude ✓", ("claude", "neither"): "review claude ✗"}
    for policy, doc in (("both", BOTH), ("claude", CLAUDE)):
        for what, reviewed in by.items():
            line = run_counts(["4"], Hub({"o/this": {4: pr_doc(4, [commit("a" * 40, "x")], reviews=reviewed)}}), policy=doc)[0]["line"]
            check(f"policy {policy}, reviewed by {what}: {want[policy, what]}",
                  line == f"#4 (1 work, 0 fix) open, unarmed, checks green, {want[policy, what]} (head hhhhhhhh)", line)

    def unreadable(repo, **kw):
        raise pr_counts.arm_policy.PolicyUnavailable("HTTP 500")
    # A claude-only default, pinned so the case does not follow the fleet's file, tells "every engine" from "the
    # default's" (supplier review F2).
    real_default, real_fleet = pr_counts.arm_policy.default, pr_counts.arm_policy.fleet_policy
    pr_counts.arm_policy.default = pr_counts.arm_policy.fleet_policy = lambda *a, **kw: CLAUDE
    try:
        line = run_counts(["4"], Hub({"o/this": {4: pr_doc(4, [commit("a" * 40, "x")], reviews=[claude_r])}}), policy=unreadable)[0]["line"]
    finally:
        pr_counts.arm_policy.default, pr_counts.arm_policy.fleet_policy = real_default, real_fleet
    check("an unreadable policy requires every engine, never the default's, and says why",
          line.endswith("review claude ✓ codex ✗ (head hhhhhhhh; policy unread, every engine required: HTTP 500)"), line)
    asked = []
    merged_only = run_counts(["3"], Hub({"o/this": {3: docs[3]}}), policy=lambda repo, **kw: asked.append(repo) or BOTH)[0]["line"]
    check("a merged pull request reads no policy (the Stop hook pays for open ones only)", asked == [] and merged_only.endswith("merged"), (asked, merged_only))

    print("an additional engine: its review, or its unavailable marker for the head (REQUEST 01a136d2)")
    hx = "abcdef12" + "3" * 32
    gone_line = f"<!-- agent-fabric-engine-unavailable v1 engine=codex head={hx} reason=allowance at=2026-10-13T19:00:00Z -->"
    extra = pr_counts.arm_policy.validate({"reviews": ["claude"], "boundary_reviews": ["claude"], "additional_reviews": ["codex"]})

    def rv(body, oid=hx, login="me"):
        return {"body": body, "commit": {"oid": oid}, "author": {"login": login}}

    def line_of(reviews, author="me"):
        doc = dict(pr_doc(4, [commit("a" * 40, "x")], head=hx, reviews=reviews), author={"login": author})
        return run_counts(["4"], Hub({"o/this": {4: doc}}), policy=extra)[0]["line"]
    cases = [("codex ✓", [rv(claude_r["body"]), rv(codex_r["body"])], "head reviewed: claude ✓ codex ✓"),
             ("codex unavailable", [rv(claude_r["body"]), rv(gone_line + "\nspent")], "head reviewed: claude ✓ codex unavailable (allowance)"),
             ("codex absent", [rv(claude_r["body"])], "head reviewed: claude ✓ codex absent"),
             ("a marker for another head", [rv(claude_r["body"]), rv(gone_line.replace(hx, "0" * 40))], "head reviewed: claude ✓ codex absent"),
             ("a marker on a review of another commit", [rv(claude_r["body"]), rv(gone_line, oid="0" * 40)], "head reviewed: claude ✓ codex absent"),
             ("a marker from another login", [rv(claude_r["body"]), rv(gone_line, login="rando")], "head reviewed: claude ✓ codex absent"),
             ("the required engine is still required", [rv(gone_line)], "review claude ✗ codex unavailable (allowance)")]
    for what, reviewed, want_line in cases:
        line = line_of(reviewed)
        check(f"{what}: {want_line}", line == f"#4 (1 work, 0 fix) open, unarmed, checks green, {want_line} (head abcdef12)", line)
    os.environ["AGENT_FABRIC_REVIEW_POSTERS"] = '["ci"]'
    try:
        line = line_of([rv(claude_r["body"]), rv(gone_line, login="ci")])
    finally:
        del os.environ["AGENT_FABRIC_REVIEW_POSTERS"]
    check("…unless AGENT_FABRIC_REVIEW_POSTERS names it", "codex unavailable (allowance)" in line, line)

    print("legacy markers")
    old = {"body": "<!-- agent-fabric-substitute-review v1 -->", "commit": {"oid": "h" * 40}}
    rows = run_counts(["4"], Hub({"o/this": {4: pr_doc(4, [commit("a" * 40, "x")], reviews=[old])}}))
    check("the built-in earlier marker counts", "review claude ✓" in rows[0]["line"], rows[0]["line"])
    mine = {"body": "<!-- mine v1 -->", "commit": {"oid": "h" * 40}}
    rows = run_counts(["4"], Hub({"o/this": {4: pr_doc(4, [commit("a" * 40, "x")], reviews=[mine])}}))
    check("a marker nobody listed does not", "review claude ✗" in rows[0]["line"], rows[0]["line"])
    os.environ["AGENT_FABRIC_LEGACY_REVIEW_MARKERS"] = "<!-- mine v1 -->"
    try:
        rows = run_counts(["4"], Hub({"o/this": {4: pr_doc(4, [commit("a" * 40, "x")], reviews=[mine])}}))
    finally:
        del os.environ["AGENT_FABRIC_LEGACY_REVIEW_MARKERS"]
    check("…unless the environment lists it", "review claude ✓" in rows[0]["line"], rows[0]["line"])

    print("v2 reviews: the gate's reader (review_coverage) decides, as for the gate")
    h2 = "a" * 40

    def v2_review(*statuses: str, head: str = h2, engine: str = "") -> dict:
        paths = {f"p{i}": ({"status": st} if st == "read" else {"status": st, "reason": "r"}) for i, st in enumerate(statuses)}
        marker = f"<!-- agent-fabric-review v2 base={'b' * 40} head={head} card={'c' * 40} config={'d' * 64} -->"
        model = f"\n<!-- model: {engine} -->" if engine else ""
        return {"body": f"{marker}{model}\n**Blind review**\n\n```agent-fabric-coverage v1\n{json.dumps({'paths': paths, 'lenses': {}})}\n```\n",
                "commit": {"oid": h2}}

    for what, rev, want in (("a complete v2 review of the head counts", v2_review("read", "read"), "review claude ✓"),
                            ("a v2 review with a path not read does not", v2_review("read", "not read"), "review claude ✗"),
                            ("a v2 review whose marker names another head does not", v2_review("read", head="c" * 40), "review claude ✗"),
                            ("a v2 review of codex counts as codex's", v2_review("read", engine="codex"), "review claude ✗")):
        rows = run_counts(["4"], Hub({"o/this": {4: pr_doc(4, [commit("a" * 40, "x")], head=h2, reviews=[rev])}}))
        check(what, want in rows[0]["line"], rows[0]["line"])

    print("refs")
    two = {"gzapi-org/gzapp": {1075: docs[1]}, "gzapi-org/InterWeave": {3: docs[3]}, "BlueTeam-OU/agent-fabric-herdr": {4: docs[4]},
           "x/y": {9: docs[9]}, "o/this": {5: docs[5]}}
    hub = Hub(two)
    rows = run_counts(["gzapp#1075", "InterWeave#3", "herdr#4", "x/y#9", "5", "GZAPP#1075"], hub)
    check("a project id, a repository's name (any case), owner/repo#N and a bare number each resolve",
          [r["ok"] for r in rows] == [True] * 6 and rows[0]["line"].startswith("gzapp#1075 (") and rows[1]["line"].startswith("InterWeave#3 (")
          and rows[2]["line"].startswith("herdr#4 (") and rows[3]["line"].startswith("x/y#9 (") and rows[4]["line"].startswith("#5 (")
          and rows[5]["line"].startswith("GZAPP#1075 ("), [r["line"] for r in rows])
    check("each repository is asked once, however many of its pull requests are named",
          sorted(c[0] for c in hub.graphql_calls) == sorted(["gzapi-org/gzapp", "gzapi-org/InterWeave", "BlueTeam-OU/agent-fabric-herdr", "x/y", "o/this"]),
          hub.graphql_calls)
    hub = Hub({"o/this": {1: docs[1], 2: docs[2], 3: docs[3]}})
    run_counts(["1", "2", "3", "#1"], hub)
    check("four refs in one repository are one query", len(hub.graphql_calls) == 1 and hub.graphql_calls[0][1] == [1, 2, 3], hub.graphql_calls)
    hub = Hub({"o/this": {n: pr_doc(n, [commit(f"{n:040x}", "x")]) for n in range(1, 26)}})
    run_counts([str(n) for n in range(1, 26)], hub)
    check("25 pull requests are three queries of at most ten", [len(c[1]) for c in hub.graphql_calls] == [10, 10, 5], hub.graphql_calls)

    print("a ref that cannot be read says why")
    hub = Hub({"o/this": {1: docs[1]}, "gzapi-org/gzapp": {}})
    rows = run_counts(["1", "999", "nope", "ghost#4", "same#1", "no-remote#2", "gzapp#5", "o/p/q#1", "#0", "0"], hub)
    by = {r["ref"]: r for r in rows}
    check("the readable ref is read beside the failures", by["#1"]["ok"] and by["#1"]["line"].startswith("#1 (1 work"), by["#1"])
    check("a missing pull request: its number, from GitHub's words", by["#999"]["line"].startswith("#999 cannot be read: ") and "999" in by["#999"]["line"], by["#999"]["line"])
    check("not a ref", by["nope"]["line"] == "nope cannot be read: 'nope' is not a ref: 167, project#167 or owner/repo#167", by["nope"]["line"])
    check("an unknown project", "'ghost' is no project id or repository name" in by["ghost#4"]["line"], by["ghost#4"]["line"])
    check("a name two projects answer to is refused, both named", "twin-a" in by["same#1"]["line"] and "twin-b" in by["same#1"]["line"], by["same#1"]["line"])
    check("a project with no GitHub remote is no repository", "no-remote#2" in by and not by["no-remote#2"]["ok"], by["no-remote#2"])
    check("a repository GitHub does not know", not by["gzapp#5"]["ok"] and "cannot be read" in by["gzapp#5"]["line"], by["gzapp#5"]["line"])
    check("owner/repo/extra is not a ref; #0 and 0 are not numbers",
          all(not by[k]["ok"] and "is not a ref" in by[k]["line"] or "is not owner/repo" in by[k]["line"] for k in ("o/p/q#1", "0", "#0")),
          [by[k]["line"] for k in ("o/p/q#1", "0", "#0")])
    check("every failure has ok False and a line that names the ref", all((not r["ok"]) and r["line"].startswith(r["ref"] + " cannot be read: ")
                                                                           for r in rows if not r["ok"]))
    hub = Hub({"o/this": {1: docs[1], 2: docs[2]}}, fail_batches=True)
    rows = run_counts(["1", "2", "77"], hub)
    check("a batch GitHub refuses is asked again one number at a time: the good ones still read",
          [r["ok"] for r in rows] == [True, True, False] and len(hub.graphql_calls) > 2, [r["line"] for r in rows])
    class NoGh(Hub):
        def graphql(self, *a, **k):
            raise gh.GhError("gh api graphql", "gh is not installed")
    rows = run_counts(["1"], NoGh({}))
    check("gh missing: named, not a traceback", rows[0]["line"] == "#1 cannot be read: gh is not installed", rows[0]["line"])

    def broken(*a, **k):
        return {"repository": {"p1": {"state": "OPEN", "commits": {"nodes": [{"commit": None}]}}}}
    saved_g = gh.graphql
    gh.graphql, saved_t = broken, gh.this_repo
    gh.this_repo = lambda cwd=None: "o/this"
    try:
        rows = pr_counts.count_rows(["1"], 5, projects_loader=load_registry)
    finally:
        gh.graphql, gh.this_repo = saved_g, saved_t
    check("an answer of an unexpected shape: named as that", not rows[0]["ok"] and "unexpected shape" in rows[0]["line"], rows[0]["line"])
    saved_t = gh.this_repo

    def no_repo(cwd=None):
        raise gh.GhError("this repository", "no origin on github.com")
    gh.this_repo = no_repo
    try:
        rows = pr_counts.count_rows(["1", "x/y#2"], 5, projects_loader=load_registry)
    finally:
        gh.this_repo = saved_t
    check("a bare number outside a checkout says so; a named repository does not need one",
          "this checkout's repository cannot be named" in rows[0]["line"] and "x/y#2" == rows[1]["ref"], [r["line"] for r in rows])

    print("long pull requests and the time allowed")
    many = [commit(f"{i:040x}", f"piece {i}", 1) for i in range(100)]
    rest = [{"sha": f"{i:040x}", "parents": [{}], "commit": {"message": f"piece {i}"}} for i in range(130)]
    hub = Hub({"o/this": {1: pr_doc(1, many, more=True)}}, rest={"repos/o/this/pulls/1/commits?per_page=100": rest})
    rows = run_counts(["1"], hub)
    check("over 100 commits: read through the REST list, all 130 counted", rows[0]["ok"] and rows[0]["work"] == 130 and hub.api_calls, rows[0])
    hub = Hub({"o/this": {1: pr_doc(1, many, more=True)}}, rest={"repos/o/this/pulls/1/commits?per_page=100": rest + rest})
    rows = run_counts(["1"], hub)
    check("250 or more: cannot be read, not a short count", not rows[0]["ok"] and "past what GitHub lists" in rows[0]["line"], rows[0]["line"])
    clock = iter([0.0, 0.1, 99.0, 99.0, 99.0, 99.0])
    budget = pr_counts.Budget(5, clock=lambda: next(clock))
    budget.left()
    try:
        budget.left()
        got = "no error"
    except pr_counts.Unreadable as e:
        got = str(e)
    check("a spent budget is a reason, not a hang", got == "the time allowed ran out", got)
    hub = Hub({"o/this": {1: docs[1]}})
    run_counts(["1"], hub, timeout=7)
    check("each gh call gets what is left of the time, at most the whole", 0 < hub.graphql_calls[0][2] <= 7, hub.graphql_calls)

    print("what the gate reads is what is read")
    wrapped = commit("w" * 40, "add parser\nfor the review findings\n\nbody text")
    r = run_counts(["1"], Hub({"o/this": {1: pr_doc(1, [wrapped])}}))[0]
    check("a subject wrapped onto a second line is one subject, as git's %s has it: \"review findings\" in its 2nd line reads it as a fix",
          r["ok"] and (r["work"], r["fix"]) == (0, 1), r)
    subj, body = pr_counts.split_message("add parser\nfor the review findings\n\nbody\n\nKind: work\n")
    check("subject and body are split as git's %s and %b", (subj, body) == ("add parser for the review findings", "body\n\nKind: work"), (subj, body))
    check("trailing space on a subject line is dropped, as git's %s drops it",
          pr_counts.split_message("add parser \nfor x\t\n\nbody")[0] == "add parser for x", pr_counts.split_message("add parser \nfor x\t\n\nbody"))
    check("only git's blanks are trimmed: a form feed and a no-break space stay (git log --format=%s keeps both)",
          pr_counts.split_message("a\f\nb\u00a0\nc")[0] == "a\f b\u00a0 c", pr_counts.split_message("a\f\nb\u00a0\nc"))
    mixed = commit("m" * 40, "small change\n\n(cherry picked from commit abcdef1)\nKind: review-fix")
    r = run_counts(["1"], Hub({"o/this": {1: pr_doc(1, [mixed])}}))[0]
    check("a trailer block that git reads and the gate's reader rejects is unreadable, not a guessed work",
          not r["ok"] and "mixes Kind:" in r["line"], r)
    spaced = commit("s" * 40, "small change\n\nbody\n\nKind : review-fix")
    r = run_counts(["1"], Hub({"o/this": {1: pr_doc(1, [spaced])}}))[0]
    check("a key written 'Kind :' is one git reads and the gate's reader does not: unreadable", not r["ok"] and "mixes Kind:" in r["line"], r)
    clean = commit("c" * 40, "small change\n\nbody\n\nKind: review-fix\nAnswers: F1")
    r = run_counts(["1"], Hub({"o/this": {1: pr_doc(1, [clean])}}))[0]
    check("…while a pure block reads: the same shape without the extra line is a fix", r["ok"] and (r["work"], r["fix"]) == (0, 1), r)
    prose = commit("p" * 40, "small change\n\nAnswers: nothing here is a trailer, it is prose\nand more prose")
    r = run_counts(["1"], Hub({"o/this": {1: pr_doc(1, [prose])}}))[0]
    check("a prose paragraph naming the key is refused too, whichever way git would read it", not r["ok"], r)

    print("folded pull requests: the base, the time, the unread")
    saved_view = gh.pr_view
    folds = commit("f" * 40, "review fix (#12 F1): the probe")
    closed12 = {"state": "CLOSED", "mergedAt": None, "headRefOid": "9" * 40}
    cmp_ahead = {"status": "ahead"}
    try:
        gh.pr_view = lambda n, fields, repo=None, timeout=None: closed12
        head = "h" * 40
        rest = {f"repos/o/this/compare/{'9' * 40}...{head}?per_page=1": cmp_ahead,
                f"repos/o/this/compare/{'9' * 40}...main?per_page=1": {"status": "diverged"}}
        r = run_counts(["1"], Hub({"o/this": {1: pr_doc(1, [folds], head=head)}}, rest=rest))[0]
        check("an open pull request: a closed one whose head is in the range is folded: the fix reads as a fix", (r["work"], r["fix"]) == (0, 1), r)
        rest[f"repos/o/this/compare/{'9' * 40}...{'b' * 40}?per_page=1"] = cmp_ahead
        r = run_counts(["1"], Hub({"o/this": {1: pr_doc(1, [folds], head=head, state="MERGED", merged=True)}}, rest=rest))[0]
        check("a merged one: a head already in the merge's first parent was folded earlier: the follow-up is work",
              r["ok"] and (r["work"], r["fix"]) == (1, 0), r)
        no_parent = pr_doc(1, [folds], head=head, state="MERGED", merged=True)
        no_parent["mergeCommit"] = {"parents": {"nodes": [{"oid": "b" * 40}]}}   # a squash: one parent
        other = pr_doc(1, [folds], head=head, state="MERGED", merged=True)
        other["mergeCommit"] = {"parents": {"nodes": [{"oid": "b" * 40}, {"oid": "e" * 40}]}}   # two parents, the second not the head
        r = run_counts(["1"], Hub({"o/this": {1: other}}, rest=rest))[0]
        check("a merge commit whose second parent is not the head is unreadable too", not r["ok"] and "not by a merge commit" in r["line"], r)
        r = run_counts(["1"], Hub({"o/this": {1: no_parent}}, rest=rest))[0]
        check("a merged one that is no merge commit of its head (a squash) is unreadable, not read against no base",
              not r["ok"] and "not by a merge commit" in r["line"], r)
        r = run_counts(["1"], Hub({"o/this": {1: pr_doc(1, [folds], head=head)}}))[0]
        check("a fold the compare cannot answer: counted as work, and the line says so",
              r["ok"] and r["work"] == 1 and r["unread_folds"] == ["12"] and "#12 could not be read" in r["line"], r)
        seen = []
        gh.pr_view = lambda n, fields, repo=None, timeout=None: (seen.append(timeout), closed12)[1]
        run_counts(["1"], Hub({"o/this": {1: pr_doc(1, [folds], head=head)}}, rest=rest), timeout=7)
        check("the fold's gh calls are bounded by the call's time, not their own 30 s", seen and all(0 < t <= 7 for t in seen), seen)
        clock = iter([0.0, 0.1, 0.2, 99.0, 99.0, 99.0, 99.0, 99.0])
        budget = pr_counts.Budget(5, clock=lambda: next(clock))
        budget.left()
        f = pr_counts.BudgetedFolds("o/this", head, "", budget)
        try:
            f(("12"))
            got = "no error"
        except pr_counts.Unreadable as e:
            got = str(e)
        check("a spent budget stops the fold check: unreadable, not a 30 s wait", got == "the time allowed ran out", got)
    finally:
        gh.pr_view = saved_view

    print("the command")
    env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "AGENT_FABRIC_PYTHON": sys.executable}
    tool = os.path.join(HERE, "bin", "fabric-pr")
    r = subprocess.run([tool, "counts"], env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    check("no ref: usage on stderr, exit 2, nothing on stdout", r.returncode == 2 and r.stdout == "" and "name at least one" in r.stderr, (r.returncode, r.stderr))
    r = subprocess.run([tool, "counts", "--bogus", "1"], env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    check("an unknown option: exit 2", r.returncode == 2 and "unknown option" in r.stderr, r.stderr)
    r = subprocess.run([tool, "counts", "--timeout", "x", "1"], env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    check("a bad --timeout: exit 2", r.returncode == 2 and "--timeout" in r.stderr, r.stderr)
    r = subprocess.run([tool, "counts", "--help"], env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    check("--help: the header, exit 0", r.returncode == 0 and "one pasteable line" in r.stdout, (r.returncode, r.stderr))
    r = subprocess.run([tool, "counts", "nope", "--json"], env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    check("--json: one object per ref; an unreadable ref exits 2 with a line, no traceback",
          r.returncode == 2 and json.loads(r.stdout.splitlines()[0])["ok"] is False and "Traceback" not in r.stderr, (r.returncode, r.stdout, r.stderr))

    for d in cleanup:
        shutil.rmtree(d, ignore_errors=True)
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
