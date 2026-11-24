"""The mocks of tests/test_arm_cli.py: gh, the readers and the other programs fabric-pr arm calls, as functions of
(state dir, argv, stdin) -> (exit, stdout, stderr). The suite calls them in process, in place of gh and the readers, and the
stand-in scripts on the CLI layer's PATH call them as programs (serve), so the two layers answer alike.

A module of its own, importing only what the mocks use: a stand-in is started about 175 times in a run, and importing the
whole suite (its fixtures, git_env, unittest.mock) for each cost four times the mocks' own time."""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _state(s: str, n: str, d: str | None = None) -> str | None:
    p = os.path.join(s, n)
    return open(p).read() if os.path.exists(p) else d


def _log(s: str, text: str) -> None:
    with open(os.path.join(s, "calls"), "a") as fh:
        fh.write(text)


def gh_mock(s: str, a: list[str], stdin: str) -> tuple[int, str, str]:
    line = " ".join(a)
    has = lambda n: os.path.exists(os.path.join(s, n))
    _log(s, line + "\n")
    if line.startswith("pr comment ") and line.endswith("--body-file -"):
        if has("commentfail"):
            return 1, "", "gh: Bad Gateway (HTTP 502)"
        _log(s, f"pr comment {a[2]} --body {stdin}\n")
        return 0, "", ""
    pr = json.load(open(os.path.join(s, "pr.json")))
    # Whom gh acts as (`viewer`, "pusher" without it; `viewer_fail` a failed call): asked only on an app's PR.
    if line.startswith("api user "):
        if has("viewer_fail"):
            return 1, "", "gh: Bad Gateway (HTTP 502)"
        return 0, json.dumps({"login": _state(s, "viewer", "pusher")}), ""
    if line.startswith("api repos/gzapi-org/gzapp/pulls/7/files") and "--paginate --slurp" in line:
        def entry(f):
            old, _, new = f.rpartition("->")
            return {"filename": new, "previous_filename": old} if old else {"filename": f}
        return 0, json.dumps([[entry(f) for f in pr["files"]]]), ""
    # The arming policy's reads (arming step C), which only the CLI layer makes: the repository's commits (no
    # Fabric-Role trailer, so no role), its client's settings repository with no
    # file for it (the fleet policy), and GitHub's side as that policy renders it.
    if line.startswith("api repos/gzapi-org/gzapp/pulls/7/commits"):
        return 0, json.dumps([[{"parents": [{}], "commit": {"message": "a commit"}}]]), ""
    if line.startswith("api repos/gzapi-org/agent-fabric-settings/contents/"):
        return 1, "", "gh: Not Found (HTTP 404)"
    if line.startswith("api repos/gzapi-org/agent-fabric-settings "):
        return 0, json.dumps({"full_name": "gzapi-org/agent-fabric-settings"}), ""
    # The head's tree, one directory a call (arm_rules.head_modes), built from the PR's files: the head itself is the
    # root, "tree:<dir>" a directory; `modes.json` {path: mode} overrides a file's 100644. Each read is a call;
    # `trees_fail` fails every one.
    if line.startswith("api repos/gzapi-org/gzapp/git/trees/"):
        if has("trees_fail"):
            return 1, "", "gh: Bad Gateway (HTTP 502)"
        sha = a[1].rsplit("/", 1)[1]
        at = "" if sha == pr["headRefOid"] else sha[len("tree:"):] + "/"
        modes = json.loads(_state(s, "modes.json", "{}"))
        names = {f.rpartition("->")[2] for f in pr["files"]}
        entries = {}
        for f in sorted(names):
            if f.startswith(at):
                part, _, rest = f[len(at):].partition("/")
                entries[part] = ({"path": part, "type": "tree", "mode": "040000", "sha": f"tree:{at}{part}"} if rest
                                 else {"path": part, "type": "blob", "mode": modes.get(f, "100644"), "sha": "b" * 40})
        return 0, json.dumps({"sha": sha, "truncated": False, "tree": list(entries.values())}), ""
    # Gate 4c's read: every review object of the PR (`reviews.json`, none without it; `reviews_fail` a failed call).
    if line.startswith("api repos/gzapi-org/gzapp/pulls/7/reviews") and "--paginate --slurp" in line:
        if has("reviews_fail"):
            return 1, "", "gh: Bad Gateway (HTTP 502)"
        return 0, json.dumps([json.loads(_state(s, "reviews.json", "[]"))]), ""
    # The armed status (arming policy armed_status): its body on stdin, logged as one line; `statusfail` a refusal.
    if line.startswith("api repos/gzapi-org/gzapp/statuses/") and line.endswith(" --method POST --input -"):
        if has("statusfail"):
            return 1, "", "gh: Resource not accessible by integration (HTTP 403)"
        _log(s, f"status {a[1].rsplit('/', 1)[1]} {stdin}\n")
        return 0, json.dumps({"state": "success"}), ""
    # The head's combined status (disarm): `armed_status` the fabric/armed state on it, none without it;
    # `status_read_fail` a failed read.
    if line.startswith("api repos/gzapi-org/gzapp/commits/") and "/status?" in line:
        if has("status_read_fail"):
            return 1, "", "gh: Bad Gateway (HTTP 502)"
        st = _state(s, "armed_status")
        return 0, json.dumps({"statuses": [{"context": "ci", "state": "success"}]
                             + ([{"context": "fabric/armed", "state": st}] if st else [])}), ""
    if line.startswith("api repos/gzapi-org/gzapp"):
        sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
        from github import arm_policy
        want = arm_policy.render(arm_policy.default())
        if line.startswith("api repos/gzapi-org/gzapp/rulesets?"):
            return 0, json.dumps([[{"id": 1, "name": want["ruleset"]["name"]}]]), ""
        if line.startswith("api repos/gzapi-org/gzapp/rulesets/1"):
            return 0, json.dumps(want["ruleset"]), ""
        if line.startswith("api repos/gzapi-org/gzapp --method GET"):
            return 0, json.dumps(want["repository"]), ""
    # disarm's two mutations, logged by name; `sticky` an arming that a mutation answered and did not take off;
    # `mutationfail` names the one that fails; `merges_on_disarm` a PR merged while it was disarmed (reads MERGED after).
    if line == "api graphql --input -" and "mutation" in stdin:
        for verb, n in (("disablePullRequestAutoMerge", "armed"), ("dequeuePullRequest", "queued")):
            if verb in stdin:
                if _state(s, "mutationfail") == verb:
                    return 1, "", "gh: GraphQL: Something went wrong (HTTP 502)"
                if has("merges_on_disarm"):
                    open(os.path.join(s, "merged"), "w").close()
                _log(s, f"mutation {verb} {json.loads(stdin)['variables']}\n")
                if not has("sticky") and has(n):
                    os.remove(os.path.join(s, n))
                return 0, json.dumps({"data": {verb: {"clientMutationId": None}}}), ""
    if line == "api graphql --input -":
        p = {"id": "PR_node7", "state": "OPEN", "headRefName": pr["headRefName"], "title": pr["title"],
             "headRefOid": pr["headRefOid"], "autoMergeRequest": None, "mergeQueueEntry": None}
        if has("pushed"):
            p["headRefOid"] = "0123456789abcdef0123456789abcdef01234567"
        if has("closed"):
            p["state"] = "CLOSED"
        elif has("merged"):
            p["state"] = "MERGED"
            p["headRefOid"] = open(os.path.join(s, "merged")).read() or p["headRefOid"]
        elif has("queued"):
            p["mergeQueueEntry"] = {"position": 2}
        elif has("armed"):
            p["autoMergeRequest"] = {"enabledAt": "x"}
        if has("nohead"):
            del p["headRefOid"]
        return 0, json.dumps({"data": {"repository": {"pullRequest": p}}}), ""
    if line == "pr view 7 --json headRefOid" and has("moved"):
        # The head read again after the gates: a push landed while they ran.
        return 0, json.dumps({"headRefOid": "fedcba9876543210fedcba9876543210fedcba98"}), ""
    if line.startswith("pr view "):
        if has("viewfail"):
            return 1, "", ""
        return 0, json.dumps({k: v for k, v in pr.items() if k != "files"}), ""
    if line == "pr merge 7 --merge --auto --match-head-commit abcdef0123456789abcdef0123456789abcdef01":
        if has("mergefail"):
            # gh's failure on a PR GitHub merges anyway (agent-fabric #237): the state files say what reads back.
            return 1, "", "GraphQL: Merge already in progress (mergePullRequest)"
        if has("cleanrefuse"):
            # GitHub 2026-11-24 (#696): a CLEAN green PR refuses --auto and merges nothing.
            return 1, "", "GraphQL: Pull request Pull request is in clean status (enablePullRequestAutoMerge)"
        if not has("noarm"):
            open(os.path.join(s, "armed"), "w").close()
        return 0, "", ""
    # A direct repository's merge (no --auto): it lands at once and reads merged, or with `direct_reads_armed` a
    # PR the API still reads armed (the read-back must not take that for a merge).
    if line == "pr merge 7 --merge --match-head-commit abcdef0123456789abcdef0123456789abcdef01":
        if has("directfail"):
            return 1, "", "GraphQL: base branch policy prohibits the merge"
        open(os.path.join(s, "armed" if has("direct_reads_armed") else "merged"), "w").close()
        return 0, "", ""
    return 1, "", "mock gh: unhandled: " + line


def gate_mock(s: str, a: list[str], stdin: str) -> tuple[int, str, str]:
    return 0, _state(s, "gate.json") + "\n", ""


# The --json object agent-fabric's reader prints (the fields arm reads),
# from state files: `blind` and `independent` list commits (sha8),
# `unresolved` the thread count ("null" for a failed lookup). review_rc 0
# with no `blind` file stands for a review-class review of the head.
# `no_blind_field` drops blind.rows. `unavailable` lists codex's unavailable
# markers as <head>@<review's sha8>:<reason>; without the file the key is absent.
def review_mock(s: str, a: list[str], stdin: str) -> tuple[int, str, str]:
    def rd(n, d=None):
        v = _state(s, n)
        return v.strip() if v is not None else d
    _log(s, " ".join(a) + "\n")
    if "--json" not in a:
        return 2, "", "mock pr-review-status: arm must ask for --json"
    rc = int(rd("review_rc", "1"))
    if rc == 2:
        return 2, "", ""
    blind = rd("blind") if rd("blind") is not None else ("abcdef01" if rc == 0 else "")
    # An entry is a sha8, or <sha8>:<engine> for a review posted by that engine (none: the review class's).
    rows = lambda t: [{"login": "someone", "commit_sha8": x.split(":")[0], "at": "2026-09-25T00:00:00Z",
                       **({"engine": x.split(":")[1]} if ":" in x else {})} for x in (t or "").split() if x]
    out = {"state": "OPEN", "head": "abcdef0123456789", "head_reviewed": rc == 0,
           "independent": {"count": len(rows(rd("independent"))), "rows": rows(rd("independent"))},
           "unresolved_threads": json.loads(rd("unresolved", "0")),
           "blind": {"count": 0} if rd("no_blind_field") is not None else {"count": len(rows(blind)), "rows": rows(blind)}}
    if rd("unavailable") is not None:
        gone = [x.replace("@", ":").split(":") for x in rd("unavailable").split()]
        out["unavailable"] = {"count": len(gone), "rows": [{"login": "someone", "commit_sha8": c, "at": "2026-10-13T19:00:00Z",
                                                            "engine": "codex", "head": h, "reason": why} for h, c, why in gone]}
    return rc, json.dumps(out) + "\n", ""


# The waiver's two readers, from state files: the relay's replay
# (`waiver.out` printed, `waiver_rc` its exit) and fabric-ctl's presence
# (`presence.out`, `ctl_rc`). Each call is recorded, prefixed, so a test
# can say whether it was asked at all.
def inbox_mock(s: str, a: list[str], stdin: str) -> tuple[int, str, str]:
    _log(s, "replay " + " ".join(a) + "\n")
    return int(_state(s, "waiver_rc", "0") or 0), _state(s, "waiver.out", ""), ""


def ctl_mock(s: str, a: list[str], stdin: str) -> tuple[int, str, str]:
    _log(s, "ctl " + " ".join(a) + "\n")
    return int(_state(s, "ctl_rc", "0") or 0), _state(s, "presence.out", ""), ""


# fabric-jobs, gate 4c's jobs half: `jobs.json` is the list (none without it), `shows.json` {id: record} what show
# answers. Each call is recorded, prefixed.
def jobs_mock(s: str, a: list[str], stdin: str) -> tuple[int, str, str]:
    _log(s, "jobs " + " ".join(a) + "\n")
    if a == ["list", "--all", "--json"]:
        return (2, "", "") if os.path.exists(os.path.join(s, "jobs_fail")) else (0, _state(s, "jobs.json", "[]"), "")
    if len(a) == 3 and a[0] == "show" and a[2] == "--json":
        shown = json.loads(_state(s, "shows.json", "{}")).get(a[1])
        return (0, json.dumps(shown), "") if shown else (1, "", f"no job {a[1]}")
    return 2, "", "mock fabric-jobs: unhandled: " + " ".join(a)


# fabric-whoami --json: `whoami.json` what it prints, this session holding devex-tooling without it.
def whoami_mock(s: str, a: list[str], stdin: str) -> tuple[int, str, str]:
    return 0, _state(s, "whoami.json", json.dumps({"address": "develop-qzapp/me", "role": "devex-tooling"})), ""


MOCKS = {"fabric-whoami": whoami_mock, "gh": gh_mock, "pr-gate": gate_mock, "pr-review-status": review_mock,
         "gzcoord-inbox": inbox_mock, "fabric-ctl": ctl_mock, "fabric-jobs": jobs_mock}

SHIM_TEXT = '''#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.join(os.environ["ARM_ROOT"], "tests"))
import arm_mocks
sys.exit(arm_mocks.serve({name!r}))
'''


def serve(name: str) -> int:
    """The mock `name` as a program on PATH: what the CLI layer runs."""
    if name == "gh":
        # The repository each gh call was pinned to: what `fabric-pr --repo` sets, asserted beside the call.
        with open(os.path.join(os.environ["MOCK_STATE"], "gh_repos"), "a") as fh:
            fh.write(os.environ.get("GH_REPO", "") + "\n")
    rc, out, err = MOCKS[name](os.environ["MOCK_STATE"], sys.argv[1:], sys.stdin.read() if name == "gh" else "")
    sys.stdout.write(out)
    sys.stderr.write(err + ("\n" if err else ""))
    return rc
