#!/usr/bin/env python3
"""fabric-pr arm with gh, pr-gate and pr-review-status mocked. The decision
logic — each gate has a case that trips it and one that passes; the arming
path posts the basis (on stdin) and runs gh pr merge --auto exactly once, and
a dry run posts and runs nothing — is asserted IN PROCESS: arm.main() with
gh.run and the readers replaced by the same mock functions the subprocess
shims serve, over gzapp's arm.json (tests/fixtures/gzapp-gh/), then
InterWeave's, which has no classes, and a project with none. Ported from
gzapp's tools/gh/test_arm.sh, case for case. The CLI layer is one smoke case
per command and outcome, through bin/fabric-pr with the mocks on PATH: usage
refusal, --help, a refusal (exit 1, stderr, no gh write), a question gh could
not answer (exit 2), GH_REPO, the arming and the dry run, a PR merged on the
arming, a waiver read by the relay and fabric-ctl programs, an arm.json read
from disk and rules found from the clone's remote. Plain script: prints
ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from unittest import mock
from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory
scrub_process_env()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# gzapp's and InterWeave's files as the projects hold them, frozen (tests/fixtures/gzapp-gh/README.md):
# a project's integration directory is the operator's instance data.
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
GZAPP_CONFIG = os.path.join(FIXTURES, "gzapp-gh", "arm.json")
SHIM = os.path.join(ROOT, "bin", "fabric-pr")
IW_CONFIG = os.path.join(FIXTURES, "interweave-gh", "arm.json")

# The mocks are functions of (state dir, argv, stdin) -> (exit, stdout, stderr): the in-process run calls them in
# place of gh and the readers, and the shims on the CLI's PATH call them as programs (serve), so the two layers
# answer alike.


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
        _log(s, f"pr comment {a[2]} --body {stdin}\n")
        return 0, "", ""
    pr = json.load(open(os.path.join(s, "pr.json")))
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
    if line == "api graphql --input -":
        p = {"state": "OPEN", "headRefOid": pr["headRefOid"], "autoMergeRequest": None, "mergeQueueEntry": None}
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
    if line.startswith("pr view "):
        if has("viewfail"):
            return 1, "", ""
        return 0, json.dumps({k: v for k, v in pr.items() if k != "files"}), ""
    if line == "pr merge 7 --merge --auto --match-head-commit abcdef0123456789abcdef0123456789abcdef01":
        if has("mergefail"):
            # gh's failure on a PR GitHub merges anyway (agent-fabric #237): the state files say what reads back.
            return 1, "", "GraphQL: Merge already in progress (mergePullRequest)"
        if not has("noarm"):
            open(os.path.join(s, "armed"), "w").close()
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


MOCKS = {"gh": gh_mock, "pr-gate": gate_mock, "pr-review-status": review_mock,
         "gzcoord-inbox": inbox_mock, "fabric-ctl": ctl_mock}

SHIM_TEXT = '''#!/usr/bin/env python3
import os, sys
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.environ["ARM_ROOT"], "tests"))
import test_arm_cli
sys.exit(test_arm_cli.serve({name!r}))
'''


def serve(name: str) -> int:
    """The mock `name` as a program on PATH: what the CLI layer runs."""
    rc, out, err = MOCKS[name](os.environ["MOCK_STATE"], sys.argv[1:], sys.stdin.read() if name == "gh" else "")
    sys.stdout.write(out)
    sys.stderr.write(err + ("\n" if err else ""))
    return rc


HEAD = "abcdef0123456789abcdef0123456789abcdef01"


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
    import gh
    from github import arm, arm_policy, repo_policy

    base_env = {k: v for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_", "GZAPP_")) and k != "GIT_DIR"}
    # The repository the mock serves (gh.this_repo never reads gh's default).
    base_env["GH_REPO"] = "gzapi-org/gzapp"
    # The role catalogue a waiver is checked against is the operator's instance file: a fixture one.
    base_env["AGENT_FABRIC_OPERATOR"] = os.path.join(FIXTURES, "gzcoord-operator")

    with tempfile.TemporaryDirectory() as sandbox:
        state, bindir = f"{sandbox}/state", f"{sandbox}/bin"
        os.makedirs(state)
        os.makedirs(bindir)
        for name in MOCKS:
            with open(f"{bindir}/{name}", "w") as fh:
                fh.write(SHIM_TEXT.format(name=name))
            os.chmod(f"{bindir}/{name}", 0o755)

        def put(name: str, text: str) -> None:
            with open(f"{state}/{name}", "w") as fh:
                fh.write(text)

        def reset(reviewed: bool = True) -> None:
            """A clean slate; `reviewed` (the default) a review-class review of the head, which every PR needs under
            claude_only (gate 4b): a case about a missing review says reviewed=False."""
            for n in ("calls", "armed", "queued", "merged", "closed", "noarm", "nohead", "pushed", "viewfail", "blind", "independent", "unresolved", "no_blind_field", "unavailable",
                      "mergefail", "inbase", "unasked",
                      "waiver.out", "waiver_rc", "presence.out", "ctl_rc"):
                if os.path.exists(f"{state}/{n}"):
                    os.remove(f"{state}/{n}")
            put("review_rc", "0" if reviewed else "1")

        def set_pr(branch: str, body: str, files: list[str], st: str = "OPEN", draft: bool = False) -> None:
            put("pr.json", json.dumps({"number": 7, "state": st, "isDraft": draft, "headRefName": branch,
                                       "headRefOid": HEAD, "baseRefName": "main", "body": body, "files": files,
                                       "title": "the pr"}))

        def set_gate(n: int | None, known: bool | None = True) -> None:
            row: dict = {"number": 7, "checks": "green"}
            if n is not None or known is not None:
                row["work_commits"] = n
            if known is not None:
                row["commits_known"] = known
            put("gate.json", json.dumps([row]))

        def calls() -> str:
            p = f"{state}/calls"
            return open(p).read() if os.path.exists(p) else ""

        def environment(fixture_rules: bool, env: dict | None) -> dict:
            e = dict(base_env, MOCK_STATE=state, ARM_ROOT=ROOT, PATH=f"{bindir}:{base_env.get('PATH', '')}",
                     AGENT_FABRIC_PR_GATE=f"{bindir}/pr-gate", AGENT_FABRIC_PR_REVIEW_STATUS=f"{bindir}/pr-review-status",
                     AGENT_FABRIC_PR_SESSION="develop-qzapp/me", AGENT_FABRIC_GZCOORD_INBOX=f"{bindir}/gzcoord-inbox",
                     AGENT_FABRIC_CTL=f"{bindir}/fabric-ctl")
            if fixture_rules:
                # Rules named, not found from the clone's remote; the legacy marker is the one the reader counts.
                e.update(AGENT_FABRIC_ARM_CONFIG=GZAPP_CONFIG,
                         AGENT_FABRIC_LEGACY_REVIEW_MARKERS="<!-- gzapp-substitute-review v1 -->")
            e.update(env or {})
            return e

        def cli(*args: str, fixture_rules: bool = True, env: dict | None = None, cwd: str = sandbox,
                split: bool = False) -> tuple:
            """bin/fabric-pr arm as a process, the mocks on its PATH: (exit, stdout and stderr), or with `split`
            (exit, stdout, stderr)."""
            r = subprocess.run([SHIM, "arm", *args], env=environment(fixture_rules, env), stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE if split else subprocess.STDOUT, stdin=subprocess.DEVNULL,
                               text=True, timeout=120, cwd=cwd)
            return (r.returncode, r.stdout, r.stderr) if split else (r.returncode, r.stdout)

        def gh_run(args: list[str], *, input: str | None = None, timeout: float = 0, what: str | None = None) -> str:
            rc, out, err = gh_mock(state, list(args), input or "")
            if rc:
                raise gh.GhError(what or "gh " + " ".join(args[:2]), err.strip() or "failed")
            return out

        def in_base(repo: str, head: str, base: str, cwd: str = ".", note=lambda _: None) -> bool | None:
            """landed.head_in_base in process: the `inbase` state file is git's yes, `unasked` a git it could not
            ask (said through `note`); each question is a call."""
            _log(state, f"landed {repo} {head} {base}\n")
            if os.path.exists(f"{state}/unasked"):
                note("could not ask git: the fake's reason")
                return None
            return os.path.exists(f"{state}/inbase")

        def reader(head: list[str], args: list[str], timeout: int = 600) -> tuple[int, str]:
            rc, out, _ = MOCKS[os.path.basename(head[0])](state, list(args), "")
            return rc, out

        # The fleet default with the review class's review alone required and no additional engine: the mocks
        # simulate that one review of the head, and the cases outside the engines' section are about the gates. That
        # section names its engines.
        claude_only = dict(arm_policy.default(), reviews=["claude"], boundary_reviews=["claude"], additional_reviews=[])

        def run(*args: str, fixture_rules: bool = True, env: dict | None = None, policy: dict | None = None) -> tuple[int, str]:
            """arm.main() in this process, the same environment as the CLI's: gh and the readers are the mocks'
            functions, and the arming policy and GitHub's side (read by the CLI layer) are claude_only with no
            drift. (exit, stdout and stderr in the order written.)"""
            buf = io.StringIO()
            with contextlib.ExitStack() as st:
                st.enter_context(mock.patch.dict(os.environ, environment(fixture_rules, env), clear=True))
                st.enter_context(mock.patch.object(arm.common, "apply_project_env"))
                st.enter_context(mock.patch.object(gh, "run", gh_run))
                st.enter_context(mock.patch.object(arm, "run_reader", reader))
                st.enter_context(mock.patch.object(arm.landed, "head_in_base", in_base))
                st.enter_context(mock.patch.object(arm_policy, "load", lambda repo, **kw: policy or claude_only))
                st.enter_context(mock.patch.object(repo_policy, "check", lambda repo, policy, api=None: []))
                st.enter_context(contextlib.redirect_stdout(buf))
                st.enter_context(contextlib.redirect_stderr(buf))
                rc = arm.main(list(args))
            return rc, buf.getvalue()

        me = "develop-qzapp/me/feat/x"
        owner = "reviewed; the owner's word given"
        mig = ["infra/db/migrations/0053_x.sql"]

        print("arm: usage")
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9)
        rc, out = run("7"); check("no --basis: exit 2, says so", rc == 2 and "--basis" in out, out)
        rc, out = run("--basis", "x"); check("no number: exit 2", rc == 2, out)
        rc, out = run("7", "--basis", "x", "--boundary", "--no-boundary", "why")
        check("--boundary with --no-boundary: exit 2", rc == 2, out)
        rc, out = run("--help"); check("--help prints the gates, exit 0", rc == 0 and "SECURITY-BOUNDARY" in out, out)
        check("…and the merge command as the run issues it", "--merge --auto\n--match-head-commit <head>" in out, out)
        check("…and the boundary sentence the comment carries at 8 or more",
              "a security boundary armed at 8 or more\nwithout the owner's word adds a sentence saying so" in out, out)

        print("arm: gate 1 — open and not a draft")
        reset(); set_pr(me, "plain", ["docs/a.md"], "MERGED"); set_gate(9)
        rc, out = run("7", "--basis", "b"); check("a merged PR is refused", rc == 1 and "MERGED, not open" in out, out)
        reset(); set_pr(me, "plain", ["docs/a.md"], "OPEN", True)
        rc, out = run("7", "--basis", "b"); check("a draft is refused", rc == 1 and "draft" in out, out)

        print("arm: gate 2 — another session's PR")
        reset(); set_pr("develop-qzapp/other/feat/x", "plain", ["docs/a.md"]); set_gate(9)
        rc, out = run("7", "--basis", "b"); check("refused by branch prefix", rc == 1 and "not this session's" in out, out)
        check("nothing armed on a refusal", "pr merge" not in calls(), calls())
        rc, out = run("7", "--basis", "b", "--any-owner"); check("--any-owner overrides", rc == 0 and "ARMED #7" in out, out)

        print("arm: gate 3 — AWAITING-SUPPLY without its range line")
        reset(); set_pr(me, "AWAITING-SUPPLY: develop-qzapp/db-admin\nAWAITING-SUPPLY: web-dev-01\n\n"
                            "aaaaaaa1..bbbbbbb2: web-dev-01 (web-dev)", ["docs/a.md"]); set_gate(9)
        rc, out = run("7", "--basis", "b")
        check("the unmet login is named", rc == 1 and "AWAITING-SUPPLY db-admin with no range line" in out, out)
        check("the login with a range line passes", "web-dev-01 with no range" not in out, out)
        reset(); set_pr(me, "AWAITING-SUPPLY: db-admin\n\n3ebdb83a..9f00aa11: db-admin (db-admin)", ["docs/a.md"])
        rc, out = run("7", "--basis", "b"); check("with its range line the PR arms", rc == 0, out)

        print("arm: gate 4 — the security boundary needs a review of the head")
        reset(reviewed=False); set_pr(me, "plain", mig + ["docs/a.md"]); set_gate(9)
        rc, out = run("7", "--basis", "b")
        check("a migration with no review: refused", rc == 1 and "no review-class review of the current head" in out, out)
        check("asked pr-review-status for the PR as --json", "7 -q --json" in calls().splitlines(), calls())
        reset(); set_pr(me, "plain", ["apps/backend_dotnet/src/Gzapp.Infrastructure/Auth/DriverIdentity.cs"]); put("review_rc", "0")
        rc, out = run("7", "--basis", "b")
        check("an Auth/ change reviewed, 9 work commits, no owner's word: armed",
              rc == 0 and "has the review class's review, and no unresolved thread" in out and "ARMED #7" in out, out)
        marked = "armed on the count rule (8 or more work commits) without the owner's word."
        check("…and the comment says it is a boundary armed without the owner's word",
              f"pr comment 7 --body Arming basis: b — 9 work commits, head abcdef01. Security boundary, {marked}"
              in calls(), calls())
        set_gate(17); rc, out = run("7", "--basis", "b")
        check("…at 17, no owner's word: armed", rc == 0 and "ARMED #7" in out, out)
        set_gate(8); reset(); put("review_rc", "0"); rc, out = run("7", "--basis", "b")
        check("…at 8, no owner's word: armed, and marked", rc == 0 and "ARMED #7" in out and marked in calls(), calls())
        reset(); put("review_rc", "0"); rc, out = run("7", "--basis", owner)
        check("…at 8 WITH the owner's word: armed, not marked as without it",
              rc == 0 and "ARMED #7" in out and "Security boundary" not in calls(), calls())
        set_gate(7); reset(); put("review_rc", "0"); rc, out = run("7", "--basis", "b")
        check("…at 7, no owner's word: refused, the count named",
              rc == 1 and "7 work commits — a security-boundary change under 8 arms only on the owner's word" in out, out)
        check("…and nothing armed", "pr merge" not in calls(), calls())
        rc, out = run("7", "--basis", owner)
        check("…at 7 with the review AND the owner's word: armed",
              rc == 0 and "has the review class's review, and no unresolved thread" in out and "ARMED #7" in out, out)
        check("…and not marked as armed without it", "Security boundary" not in calls(), calls())
        for n in (3, 20):
            reset(reviewed=False); set_gate(n); rc, out = run("7", "--basis", owner)
            check(f"…at {n} with the owner's word but no review: refused",
                  rc == 1 and "no review-class review of the current head" in out, out)
            reset(); set_gate(n); put("review_rc", "0"); put("unresolved", "1"); rc, out = run("7", "--basis", owner)
            check(f"…at {n} with the owner's word, reviewed, one thread open: refused",
                  rc == 1 and "with 1 unresolved review thread(s)" in out, out)
        set_gate(9)
        for path, label in (("apps/backend_dotnet/src/Gzapp.Admin/Drivers/AdminDriverDirectoryRepository.cs", "Drivers/"),
                            ("packages/web-shared/src/auth/refresh.ts", "a lowercase client auth/ (case-insensitive)"),
                            ("apps/backend_dotnet/src/Gzapp.Persistence/Consent/ConsentRepository.cs", "Consent/")):
            reset(reviewed=False); set_pr(me, "plain", [path])
            rc, out = run("7", "--basis", "b")
            check(f"{label} with no review: refused", rc == 1 and "no review-class review of the current head" in out, out)
        reset(); set_pr(me, "plain", ["apps/backend_dotnet/src/Gzapp.Persistence/DriverPositions/Store.cs"]); put("review_rc", "5")
        rc, out = run("7", "--basis", "b"); check("Regime 3 positions with no review coming (exit 5): refused", rc == 1, out)
        reset(); set_pr(me, "plain", mig); put("review_rc", "0"); put("blind", ""); put("independent", "abcdef01")
        rc, out = run("7", "--basis", owner)
        check("an independent review of the head, reader exit 0: not the boundary's review",
              rc == 1 and "no review-class review of the current head" in out, out)
        reset(); set_pr(me, "plain", mig); put("review_rc", "0"); put("blind", "1234abcd")
        rc, out = run("7", "--basis", owner)
        check("a blind review of an EARLIER commit: refused", rc == 1 and "no review-class review of the current head" in out, out)
        reset(); set_pr(me, "plain", mig); put("review_rc", "0"); put("unresolved", "2")
        rc, out = run("7", "--basis", owner)
        check("2 threads open: refused, the count named", rc == 1 and "with 2 unresolved review thread(s)" in out, out)
        reset(); set_pr(me, "plain", mig); put("review_rc", "0"); put("unresolved", "null")
        rc, out = run("7", "--basis", owner)
        check("unresolved_threads null: exit 2, never read as zero", rc == 2 and "no unresolved_threads count" in out, out)
        reset(); set_pr(me, "plain", mig); put("review_rc", "0"); put("no_blind_field", "")
        rc, out = run("7", "--basis", owner)
        check("no blind.rows: exit 2", rc == 2 and "carried no blind.rows" in out, out)
        reset(); put("review_rc", "2")
        rc, out = run("7", "--basis", "b"); check("pr-review-status exit 2: exit 2", rc == 2, out)
        # Outside the boundary the review-class gate is not applied; gate 4b still asks the policy's engines (claude).
        reset(); set_pr(me, "plain", ["docs/adr/ADR-054-privacy-regime-separation-four-regimes.md",
                                      "infra/local/grafana/provisioning/dashboards/x.json", "docs/devices/eye-beacon.md"])
        rc, out = run("7", "--basis", "b")
        check("docs and local-infra paths matching a boundary word still pass", rc == 0 and "not a security-boundary change" in out
              and "has the review class's review" not in out and "review=head reviewed: claude ✓ (head abcdef01)" in out, out)
        reset(); set_pr(me, "plain", ["docs/a.md", "product/i18n/ka-GE.json"])
        rc, out = run("7", "--basis", "b")
        check("docs + i18n pass on the engines' review alone", rc == 0 and "not a security-boundary change" in out
              and "has the review class's review" not in out and "review=head reviewed: claude ✓ (head abcdef01)" in out, out)
        check("…and the review status was asked once, by gate 4b", calls().splitlines().count("7 -q --json") == 1, calls())
        reset(reviewed=False); set_pr(me, "plain", ["docs/a.md"])
        rc, out = run("7", "--basis", "b", "--boundary")
        check("--boundary forces the gate on a docs PR", rc == 1 and "no review-class review" in out, out)
        reset(reviewed=False); set_pr(me, "plain", ["apps/backend_dotnet/src/Gzapp.Infrastructure/Auth/Tokens.cs->docs/tokens.md"]); set_gate(9)
        rc, out = run("7", "--basis", "b")
        check("a file renamed OUT of a boundary directory is judged by its old name too",
              rc == 1 and "no review-class review" in out, out)

        print("arm: gate 4 — a waiver, read from the relay and checked against the fabric")
        cto, mid = "develop-qzapp/architect-cto-01", "01a10593-0000-7000-8000-00000000c7f0"
        with open(os.path.join(FIXTURES, "gzapp-gh", "arm.json")) as fh:
            rules = json.load(fh)
        rules["waiver_role"] = "architect-cto"
        put("waiver-rules.json", json.dumps(rules))
        rules.pop("waiver_role")
        put("no-waiver-rules.json", json.dumps(rules))
        wenv = {"AGENT_FABRIC_ARM_CONFIG": f"{state}/waiver-rules.json"}

        waives = f"gzapi-org/gzapp#7@{HEAD[:8]}"

        def set_waiver(addressed: bool = True, typ: str = "DECISION", sender: str = cto, frm: str | None = None,
                       role_line: str = "architect-cto", text: str = "Waived for #7: comment-only DDL.",
                       line: str | None = waives, to: str | None = "develop-qzapp/me", extra: dict | None = None,
                       message_id: str | None = mid) -> None:
            if not addressed:
                put("waiver.out", json.dumps({"addressed": False, "seq": 4242}) + "\n"); put("waiver_rc", "2"); return
            meta = {"FROM": frm if frm is not None else sender, "ROLE": role_line, "PROJECT": "gzapp"}
            if to is not None:
                meta["TO"] = to
            if message_id is not None:
                meta["MESSAGE-ID"] = message_id
            if line is not None:
                meta["WAIVES"] = line
            meta.update(extra or {})
            put("waiver.out", json.dumps({"addressed": True, "seq": 4242, "sender": sender, "when": "t", "type": typ,
                                          "metadata": meta, "text": f"[GZCOORD/1] {typ}\n" + text}) + "\n")
            put("waiver_rc", "0")

        def set_presence(role: str | None = "architect-cto", account: str = "architect-cto-01",
                         host: str = "develop-qzapp", status: str = "ok", pstatus: str = "ok") -> None:
            put("presence.out", json.dumps({"account": account, "host": host, "status": status, "op": "presence",
                                            "presence": {"status": pstatus, "online": True, "role": role}}) + "\n")

        why = "comment-only DDL"

        def waive(*extra: str, basis: str = "nine at the gate", env: dict | None = None) -> tuple[int, str]:
            return run("7", "--basis", basis, "--no-boundary", why, "--waiver", mid, *extra, env=env or wenv)

        reset(); set_pr(me, "plain", mig); set_gate(9)
        rc, out = run("7", "--basis", "the owner's word", "--no-boundary", why, env=wenv)
        check("--no-boundary without --waiver: exit 2, nothing armed", rc == 2 and "come together" in out
              and "pr merge" not in calls(), out)
        rc, out = run("7", "--basis", "b", "--waiver", mid, env=wenv)
        check("--waiver without --no-boundary: exit 2", rc == 2 and "come together" in out, out)
        rc, out = run("7", "--basis", "b", "--no-boundary", why, "--waiver", env=wenv)
        check("--waiver with no value: exit 2", rc == 2 and "--waiver needs" in out, out)

        reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(); set_presence()
        rc, out = waive()
        check("a waiver from the role's holder, addressed here, naming the PR: armed",
              rc == 0 and "boundary gate WAIVED by architect-cto-01" in out and "ARMED #7" in out, out)
        check("…the comment records the login, the message and the reason",
              f"Boundary gate waived by architect-cto-01 ({mid}): {why}." in calls(), calls())
        check("…and a waived boundary is not marked as armed without the owner's word",
              "Security boundary" not in calls(), calls())
        check("…the replay asked by the id given, the role asked of fabric-ctl for the sender's login",
              f"replay --replay {mid} --json" in calls() and "ctl architect-cto-01 presence --json" in calls(), calls())
        check("…the review class's gate lifted (only gate 4b's engines asked) and no owner's word needed",
              calls().splitlines().count("7 -q --json") == 1 and "has the review class's review" not in out
              and "owner's word" not in out, calls())
        reset(reviewed=False); set_pr(me, "plain", mig); set_gate(9); set_waiver(); set_presence()
        rc, out = waive()
        check("…but a waived boundary with no review at all: refused, naming claude (the waiver lifts gate 4, not 4b)",
              rc == 1 and "boundary gate WAIVED" in out and "by the claude engine" in out and "pr merge" not in calls(), out)
        reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(); set_presence()
        rc, out = run("7", "--basis", "b", "--no-boundary", why, "--waiver", "4242", env=wenv)
        check("a waiver named by relay seq: the comment records its MESSAGE-ID", rc == 0
              and f"waived by architect-cto-01 ({mid})" in calls(), calls())
        reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(line=f"GZAPI-ORG/GZAPP#7@{HEAD[:16].upper()}"); set_presence()
        rc, out = waive(); check("WAIVES: the repository case-insensitive, a longer head prefix in capitals", rc == 0, out)
        reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(); set_presence()
        rc, out = waive("--dry-run")
        check("a dry run checks the waiver and posts nothing", rc == 0 and "WAIVED" in out and "pr comment" not in calls()
              and "replay --replay" in calls(), out)

        for label, setup, said in (
                ("not addressed to this session", lambda: set_waiver(addressed=False), "not addressed to this session"),
                ("an INFO, not a DECISION or REPLY", lambda: set_waiver(typ="INFO"), "not a DECISION or REPLY"),
                ("a REQUEST", lambda: set_waiver(typ="REQUEST"), "not a DECISION or REPLY"),
                ("a FROM other than the relay's sender", lambda: set_waiver(frm="develop-qzapp/me"), "says FROM"),
                ("declining #7, with no WAIVES line", lambda: set_waiver(text="I do NOT waive #7.", line=None), "has no WAIVES"),
                ("whose WAIVES line names another PR", lambda: set_waiver(line=f"gzapi-org/gzapp#70@{HEAD[:8]}"),
                 "WAIVES gzapi-org/gzapp#70, not gzapi-org/gzapp#7"),
                ("whose WAIVES line names another repository", lambda: set_waiver(line=f"gzapi-org/other#7@{HEAD[:8]}"),
                 "WAIVES gzapi-org/other#7, not"),
                ("for an earlier head", lambda: set_waiver(line="gzapi-org/gzapp#7@12345678"),
                 "WAIVES head 12345678, and #7's head is now abcdef012345"),
                ("whose head is under 8 hex", lambda: set_waiver(line=f"gzapi-org/gzapp#7@{HEAD[:7]}"), "has no WAIVES"),
                ("with the WAIVES text in its body only", lambda: set_waiver(text=f"WAIVES: {waives}", line=None), "has no WAIVES"),
                ("sent to the role, not to this login", lambda: set_waiver(to=None, extra={"TO-ROLE": "python-dev"}),
                 "not sent TO develop-qzapp/me (a broadcast or a role address)"),
                ("broadcast", lambda: set_waiver(to=None, extra={"BROADCAST": "true"}), "a broadcast or a role address"),
                ("sent TO another login", lambda: set_waiver(to="develop-qzapp/other"), "(TO develop-qzapp/other)"),
                ("from the arming session itself", lambda: set_waiver(sender="develop-qzapp/me"), "the login arming"),
                ("from the arming login on another host", lambda: set_waiver(sender="far-host/me"), "the login arming")):
            reset(); set_pr(me, "plain", mig); set_gate(9); set_presence(); setup()
            rc, out = waive()
            check(f"a waiver {label}: refused, nothing armed", rc == 1 and said in out and "pr merge" not in calls()
                  and "pr comment" not in calls(), out)
        reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(sender="develop-qzapp/backend-dev-01")
        set_presence(role="backend-dev", account="backend-dev-01")
        rc, out = waive()
        check("a sender holding another role, its ROLE line claiming architect-cto: refused — the fabric's record wins",
              rc == 1 and "who holds backend-dev, not architect-cto" in out and "pr merge" not in calls(), out)
        reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(); set_presence(role=None)
        rc, out = waive(); check("a sender holding no role: refused", rc == 1 and "holds no role" in out, out)

        for label, setup in (
                ("the replay finds no message (exit 1, no JSON)", lambda: (put("waiver.out", ""), put("waiver_rc", "1"))),
                ("the relay is down (exit 0, no JSON)", lambda: (put("waiver.out", "gzcoord: relay unreachable\n"), put("waiver_rc", "0"))),
                ("a refused token (exit 4)", lambda: (put("waiver.out", ""), put("waiver_rc", "4"))),
                ("JSON with no addressed field", lambda: (put("waiver.out", '{"seq": 1}'), put("waiver_rc", "0"))),
                ("addressed, with a failing exit", lambda: (set_waiver(), put("waiver_rc", "1"))),
                ("not addressed, with exit 0", lambda: (set_waiver(addressed=False), put("waiver_rc", "0")))):
            reset(); set_pr(me, "plain", mig); set_gate(9); set_presence(); setup()
            rc, out = waive()
            check(f"{label}: exit 2, nothing posted", rc == 2 and "could not be read from the relay" in out
                  and "pr comment" not in calls() and "pr merge" not in calls(), out)
        for label, setup in (
                ("fabric-ctl fails", lambda: (set_presence(), put("ctl_rc", "3"))),
                ("fabric-ctl says no answer", lambda: set_presence(status="no answer")),
                ("presence could not be read", lambda: set_presence(pstatus="error")),
                ("presence for another host", lambda: set_presence(host="far-host")),
                ("presence for another account", lambda: set_presence(account="architect-cto-02")),
                ("fabric-ctl prints nothing", lambda: put("presence.out", ""))):
            reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(); setup()
            rc, out = waive()
            check(f"{label}: exit 2, the role unread is not a refusal nor a pass", rc == 2
                  and "could not say which role" in out and "pr merge" not in calls(), out)
        reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(); set_presence()
        rc, out = waive(env={"AGENT_FABRIC_ARM_CONFIG": f"{state}/no-waiver-rules.json"})
        check("an arm.json with no waiver_role: exit 2, and the relay not asked", rc == 2 and "names no waiver_role" in out
              and "replay" not in calls() and "pr merge" not in calls(), out)
        put("bad-role.json", json.dumps(dict(rules, waiver_role="")))
        rc, out = waive(env={"AGENT_FABRIC_ARM_CONFIG": f"{state}/bad-role.json"})
        check("a waiver_role that is not a slug: exit 2", rc == 2 and "not a usable arm.json" in out, out)
        for bad in (" architect-cto", "Architect CTO", "ghost-role"):
            reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(); set_presence()
            put("bad-role.json", json.dumps(dict(rules, waiver_role=bad)))
            rc, out = waive(env={"AGENT_FABRIC_ARM_CONFIG": f"{state}/bad-role.json"})
            check(f"waiver_role {bad!r}, not a catalogue slug: exit 2, the relay not asked",
                  rc == 2 and "is not a role of identities/roles/catalog.json" in out and "replay" not in calls(), out)
        reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(message_id=None); set_presence()
        rc, out = run("7", "--basis", "b", "--no-boundary", why, "--waiver", "4242", env=wenv)
        check("a waiver with no MESSAGE-ID: exit 2, never recorded under the seq typed",
              rc == 2 and "carries no MESSAGE-ID" in out and "pr comment" not in calls(), out)

        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); set_waiver(addressed=False)
        rc, out = waive()
        check("a waiver on a PR that matched no boundary: armed, said, not read", rc == 0
              and "the waiver " + mid + " is not needed, not read, and not recorded" in out
              and "replay" not in calls() and "ctl " not in calls(), out)
        check("…and the comment carries no waiver", "pr comment 7 --body Arming basis: nine at the gate — 9 work commits,"
              " head abcdef01.\n" in calls() and "waived" not in calls(), calls())
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); set_waiver(); set_presence()
        rc, out = run("7", "--basis", "b", "--boundary", "--no-boundary", why, "--waiver", mid, env=wenv)
        check("--boundary with a waiver still contradicts: exit 2", rc == 2 and "contradict" in out, out)

        # A waived boundary is judged as no boundary at the count rule too:
        # under 8, a class the files confirm arms it without the owner's word,
        # where the same PR reviewed but unwaived needs that word.
        put("ddl-rules.json", json.dumps(dict(rules, waiver_role="architect-cto",
                                              classes=dict(rules.get("classes") or {}, ddl="^infra/db/migrations/"))))
        denv = {"AGENT_FABRIC_ARM_CONFIG": f"{state}/ddl-rules.json"}
        reset(); set_pr(me, "Class: ddl", mig); set_gate(2); set_waiver(); set_presence()
        rc, out = waive(basis="two commits", env=denv)
        check("a waived boundary at 2 under a confirmed class: armed at the gate as the class",
              rc == 0 and "under 8, arms at the gate as ddl" in out and "ARMED #7" in out, out)
        reset(); set_pr(me, "Class: ddl", mig); set_gate(2); put("review_rc", "0")
        rc, out = run("7", "--basis", "two commits", env=denv)
        check("…the same PR reviewed but not waived: refused without the owner's word",
              rc == 1 and "whatever class is stated" in out, out)

        print("arm: the policy's reviews — each required engine has reviewed the current head (ADR-053 rule 6)")
        d = arm_policy.default()
        check("the built-in default requires claude and asks codex as an additional review",
              (d["reviews"], d["boundary_reviews"], d["additional_reviews"]) == (["claude"], ["claude"], ["codex"]), str(d))
        both = dict(claude_only, reviews=["claude", "codex"], boundary_reviews=["claude", "codex"])
        # Gate 4 asks a review only of a boundary or a direct repository; a plain PR's review is gate 4b's, whatever
        # engines the policy names (#235, Codex finding 1: ["claude"] alone once skipped it and armed with none).
        reset(reviewed=False); set_pr(me, "plain", ["docs/a.md"]); set_gate(9)
        rc, out = run("7", "--basis", "b")
        check("a claude-only policy, a plain PR with no review: refused, naming claude",
              rc == 1 and "by the claude engine" in out and "engines required: claude)" in out and "pr merge" not in calls(), out)
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9)
        rc, out = run("7", "--basis", "b")
        check("…with the claude review of the head: armed", rc == 0 and "ARMED #7" in out
              and "review=head reviewed: claude ✓ (head abcdef01)" in out, out)
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); put("review_rc", "0")
        rc, out = run("7", "--basis", "b", policy=both)
        check("a policy requiring claude and codex, only the claude review of the head: refused, naming codex",
              rc == 1 and "by the codex engine" in out and "review=claude ✓ codex ✗ (head abcdef01)" in out
              and "pr merge" not in calls(), out)
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); put("review_rc", "0"); put("blind", "abcdef01:codex")
        rc, out = run("7", "--basis", "b", policy=both)
        check("codex required, only the codex review: refused, naming claude", rc == 1 and "by the claude engine" in out, out)
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); put("review_rc", "0"); put("blind", "abcdef01 abcdef01:codex")
        rc, out = run("7", "--basis", "b", policy=both)
        check("both engines reviewed the head: armed", rc == 0 and "ARMED #7" in out
              and "review=head reviewed: claude ✓ codex ✓ (head abcdef01)" in out, out)
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); put("review_rc", "0"); put("blind", "abcdef01 12345678:codex")
        rc, out = run("7", "--basis", "b", policy=both)
        check("a codex review of an older head does not count", rc == 1 and "by the codex engine" in out, out)
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); put("review_rc", "0"); put("blind", "abcdef01 abcdef01:codex")
        put("unresolved", "1")
        rc, out = run("7", "--basis", "b", policy=both)
        check("both reviewed but a thread (a P1 or P2 of either engine) is open: refused",
              rc == 1 and "unresolved review thread" in out and "pr merge" not in calls(), out)
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); put("review_rc", "0"); put("blind", "abcdef01:codex")
        rc, out = run("7", "--basis", "b", policy=dict(claude_only, reviews=["codex"]))
        check("a policy naming only codex needs only codex", rc == 0 and "ARMED #7" in out, out)
        bnd = dict(claude_only, boundary_reviews=["claude", "codex"])
        reset(); set_pr(me, "plain", mig); set_gate(9); put("review_rc", "0")
        rc, out = run("7", "--basis", "b", policy=bnd)
        check("boundary_reviews: a boundary change reviewed by claude alone is refused for codex", rc == 1 and "by the codex engine" in out, out)
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9)
        rc, out = run("7", "--basis", "b", policy=bnd)
        check("…and a PR outside the boundary is not asked for it", rc == 0 and "ARMED #7" in out, out)
        reset(); set_pr(me, "plain", mig); set_gate(9); put("review_rc", "0"); put("blind", "abcdef01:codex")
        rc, out = run("7", "--basis", "b")
        check("a claude-only policy: a codex review of the head is not the boundary's review-class review (review of #220, F1)",
              rc == 1 and "no review-class review" in out and "pr merge" not in calls(), out)
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); put("review_rc", "0"); put("blind", "abcdef01:codex")
        rc, out = run("7", "--basis", "b", policy=dict(claude_only, mode="direct"))
        check("…nor a direct repository's", rc == 1 and "no review-class review" in out and "pr merge" not in calls(), out)
        reset(); set_pr(me, "plain", mig); set_gate(9); put("review_rc", "0"); put("blind", "abcdef01 abcdef01:codex")
        rc, out = run("7", "--basis", "b")
        check("…while the review class's own review of the head, beside a codex one, still arms", rc == 0 and "ARMED #7" in out, out)

        print("arm: an additional engine (additional_reviews) — its review, its unavailable marker, or absent: never blocking")
        extra = dict(claude_only, reviews=["claude"], boundary_reviews=["claude"], additional_reviews=["codex"])
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); put("review_rc", "0"); put("blind", "abcdef01 abcdef01:codex")
        rc, out = run("7", "--basis", "b", policy=extra)
        check("codex ✓: armed, and the basis says nothing of an engine that ran", rc == 0 and "ARMED #7" in out
              and "review=head reviewed: claude ✓ codex ✓ (head abcdef01)" in out and "could not run" not in calls(), out)
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); put("review_rc", "0"); put("unavailable", f"{HEAD}@abcdef01:allowance")
        rc, out = run("7", "--basis", "b", policy=extra)
        check("codex unavailable for the head: armed on claude alone, said in the output and in the basis", rc == 0 and "ARMED #7" in out
              and "review=head reviewed: claude ✓ codex unavailable (allowance) (head abcdef01)" in out
              and "the codex engine could not run on abcdef01 (allowance)" in out
              and "pr comment 7 --body Arming basis: b — 9 work commits, head abcdef01. The codex engine could not run on head"
                  " abcdef01 (allowance): armed on the claude review alone." in calls(), out + calls())
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); put("review_rc", "0")
        rc, out = run("7", "--basis", "b", policy=extra)
        absent = ("pr comment 7 --body Arming basis: b — 9 work commits, head abcdef01. codex: absent, no review or marker on"
                  " abcdef01: armed on the claude review alone.")
        check("codex with neither review nor marker: absent, armed on claude alone, said in the output and in the basis",
              rc == 0 and "ARMED #7" in out and "review=head reviewed: claude ✓ codex absent (head abcdef01)" in out
              and "codex: absent, no review or marker on abcdef01" in out and absent in calls()
              and calls().count(f"pr merge 7 --merge --auto --match-head-commit {HEAD}") == 1, out + calls())
        other = "0123456789abcdef0123456789abcdef01234567"
        for mark, what in ((f"{other}@01234567:allowance", "a marker for another head"),
                           (f"{other}@abcdef01:allowance", "…one naming another head on a review of this one"),
                           (f"{HEAD}@01234567:allowance", "…one naming this head on a review of another commit")):
            reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); put("review_rc", "0"); put("unavailable", mark)
            rc, out = run("7", "--basis", "b", policy=extra)
            check(f"{what} is no marker of this head: codex absent, armed", rc == 0 and "codex absent (head" in out
                  and "could not run" not in out and absent in calls(), out + calls())
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); put("review_rc", "0"); put("blind", ""); put("unavailable", f"{HEAD}@abcdef01:allowance")
        rc, out = run("7", "--basis", "b", policy=extra)
        check("the required engine is still required: codex unavailable, no claude review, refused naming claude",
              rc == 1 and "by the claude engine" in out and "pr merge" not in calls(), out)
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); put("review_rc", "0"); put("unavailable", f"{HEAD}@abcdef01:allowance")
        put("unresolved", "1")
        rc, out = run("7", "--basis", "b", policy=extra)
        check("an open thread (codex's P1 or P2 of an earlier head included) still blocks", rc == 1 and "unresolved review thread" in out, out)
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); put("review_rc", "0"); put("unavailable", f"{HEAD}@abcdef01:allowance")
        rc, out = run("7", "--basis", "b", policy=both)
        check("where codex is required its marker stands in for nothing", rc == 1 and "by the codex engine" in out, out)
        bnd_extra = dict(extra, boundary_reviews=["claude", "codex"])
        reset(); set_pr(me, "plain", mig); set_gate(9); put("review_rc", "0"); put("unavailable", f"{HEAD}@abcdef01:allowance")
        rc, out = run("7", "--basis", "b", policy=bnd_extra)
        check("…as on a boundary that requires it", rc == 1 and "by the codex engine" in out and "pr merge" not in calls(), out)

        print("arm: gate 5 — the classes that arm under 8 without asking")
        reset(); set_pr("develop-qzapp/me/docs/x", "Wording.\n\nClass: docs-only",
                        ["docs/adr/ADR-054-x.md", ".claude/skills/pr-gate/SKILL.md", "apps/backend_dotnet/CLAUDE.md"]); set_gate(2)
        rc, out = run("7", "--basis", "two wording commits")
        check("docs-only stated and true: 2 work commits arm", rc == 0 and "arms at the gate as docs-only" in out, out)
        check("…and the comment records the class",
              "pr comment 7 --body Arming basis: two wording commits — 2 work commits, class: docs-only, head" in calls(), calls())
        reset(); set_pr("develop-qzapp/me/docs/x", "- **Class: single-check tooling** fix\n",
                        ["tools/gh/arm.sh", "tools/gh/test_arm.sh", ".github/workflows/_ban-checks.yml"]); set_gate(1)
        rc, out = run("7", "--basis", "one check")
        check("single-check tooling stated (bold, in a list) and true: arms",
              rc == 0 and "arms at the gate as single-check tooling" in out, out)
        for files, named, label in ((["docs/a.md", "product/i18n/ka-GE.json"], "product/i18n/ka-GE.json", "an i18n dictionary"),
                                    (["docs/a.md", ".claude/settings.json"], ".claude/settings.json", ".claude/settings.json")):
            reset(); set_pr("develop-qzapp/me/docs/x", "Class: docs-only", files); set_gate(2)
            rc, out = run("7", "--basis", "b"); check(f"{label} is NOT docs-only: refused, named", rc == 1 and named in out, out)
        reset(); set_pr("develop-qzapp/me/docs/x", "Class: single-check tooling", [".claude/settings.json", "tools/gh/arm.sh"]); set_gate(1)
        rc, out = run("7", "--basis", "b"); check("…but settings.json IS tooling: arms", rc == 0, out)
        reset(); set_pr("develop-qzapp/me/docs/x", "Class: docs-only", ["docs/a.md", "apps/backend_dotnet/src/Gzapp.Core/Thing.cs"]); set_gate(2)
        rc, out = run("7", "--basis", "b")
        check("a stated class the files contradict is refused",
              rc == 1 and "states Class: docs-only but the changed files are not that class" in out, out)
        check("…naming the file outside the class", "Gzapp.Core/Thing.cs" in out, out)
        reset(); set_pr("develop-qzapp/me/docs/x", "Class: docs-only", ["docs/a.md"]); set_gate(20)
        rc, out = run("7", "--basis", "b")
        check("over 16 under a class: armed with the advice said", rc == 0 and "over 16: smaller batches next time" in out, out)
        reset(); set_pr(me, "Class: docs-only", ["apps/backend_dotnet/src/Gzapp.Infrastructure/Auth/DriverIdentity.cs"]); set_gate(2)
        put("review_rc", "0")
        rc, out = run("7", "--basis", "b"); check("a boundary file under a stated docs-only class: refused", rc == 1, out)
        reset(); set_pr(me, "Class: docs-only", ["docs/a.md"]); set_gate(2); put("review_rc", "0")
        rc, out = run("7", "--basis", "b", "--boundary")
        check("a boundary under 8 whose files ARE the stated class: refused without the owner's word",
              rc == 1 and "whatever class is stated" in out, out)
        rc, out = run("7", "--basis", owner, "--boundary")
        check("…and armed on it, said as the owner's word, not the class",
              rc == 0 and "under 8, on the owner's word" in out, out)

        print("arm: gate 5 — the count rule")
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(17)
        rc, out = run("7", "--basis", "b")
        check("17 work commits: armed with the advice said",
              rc == 0 and "17 work commits — over 16: smaller batches next time; arming on the basis given" in out, out)
        check("…and the comment carries the count", "pr comment 7 --body Arming basis: b — 17 work commits, head" in calls(), calls())
        reset(); set_gate(5)
        rc, out = run("7", "--basis", "five commits, all docs")
        check("5 work commits with no owner's word: refused", rc == 1 and "owner's word" in out, out)
        rc, out = run("7", "--basis", "the owner has not been asked yet")
        check("a basis that merely mentions the owner is not the owner's word", rc == 1, out)
        rc, out = run("7", "--basis", "on the owner’s word (curly apostrophe)")
        check("the phrase with a curly apostrophe counts", rc == 0, out)
        rc, out = run("7", "--basis", "five commits; the owner's word given today")
        check("5 work commits on the owner's word: armed", rc == 0 and "under 8, on the owner's word" in out, out)
        reset(); put("gate.json", '[{"number":7}]')
        rc, out = run("7", "--basis", "b"); check("no commit count from pr-gate: exit 2", rc == 2, out)
        reset(); set_gate(None, False)
        rc, out = run("7", "--basis", "on the owner's word")
        check("commits_known false: exit 2, never 'under 8'", rc == 2 and "could not count" in out, out)
        check("…and nothing was armed", "pr merge" not in calls(), calls())
        reset(); set_gate(0, None)
        rc, out = run("7", "--basis", "on the owner's word")
        check("a row with no commits_known field is not trusted either", rc == 2, out)

        print("arm: the arming path and the dry run")
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9)
        rc, out = run("7", "--basis", "nine work commits at the review gate")
        check("exits 0", rc == 0, out)
        check("gh pr merge --auto ran once, pinned to the head the gates read",
              calls().count(f"pr merge 7 --merge --auto --match-head-commit {HEAD}") == 1, calls())
        check("the basis comment carries the count and the head, on stdin",
              "pr comment 7 --body Arming basis: nine work commits at the review gate — 9 work commits, head abcdef01." in calls(), calls())
        check("prints the watcher line for the session", "fabric-pr wait-merged 7 &" in out, out)
        reset(); put("queued", "")
        rc, out = run("7", "--basis", "b")
        check("a PR that went straight into the queue reads as armed", rc == 0 and "queued at 2" in out, out)
        # On GitHub a merged PR reads autoMergeRequest and mergeQueueEntry
        # null, as an unarmed one does (agent-fabric #118, checks green).
        reset(); put("merged", "")
        rc, out = run("7", "--basis", "b")
        check("a PR merged on the arming, on the head the gates read: exit 0, said merged",
              rc == 0 and "MERGED #7" in out and "merged on head abcdef01" in out, out)
        check("…with no watcher line, since nothing is left to wait for", "wait-merged" not in out, out)
        reset(); put("merged", "0123456789abcdef0123456789abcdef01234567")
        rc, out = run("7", "--basis", "b")
        check("merged on another head: exit 2, the two heads named",
              rc == 2 and "merged at 01234567, not abcdef01" in out and "MERGED #7" not in out, out)
        reset(); put("closed", "")
        rc, out = run("7", "--basis", "b"); check("closed after the arming: exit 2, said closed", rc == 2 and "reads 'state CLOSED'" in out, out)
        reset(); put("merged", ""); put("nohead", "")
        rc, out = run("7", "--basis", "b")
        check("merged with no head in the answer: exit 2, 'unknown', never merged",
              rc == 2 and "reads 'unknown'" in out and "MERGED #7" not in out, out)
        for flag in ("armed", "queued"):
            reset(); put("pushed", "")
            if flag == "queued": put("queued", "")
            rc, out = run("7", "--basis", "b")
            check(f"{flag} on another head than the gates read: exit 2, the two heads named",
                  rc == 2 and "open at 01234567, not abcdef01" in out and "ARMED #7" not in out, out)
        reset(); put("noarm", "")
        rc, out = run("7", "--basis", "b")
        check("open, neither armed nor queued after gh pr merge --auto: exit 2, 'idle'",
              rc == 2 and "reads 'idle'" in out, out)
        check("…its head asked of git first, on the base the PR names", f"landed gzapi-org/gzapp {HEAD} main" in calls(),
              calls())
        reset()
        rc, out = run("7", "--basis", "b")
        check("an armed read-back asks git nothing: the common path costs no fetch", rc == 0 and "landed" not in calls(),
              calls())

        print("arm: a merge call that fails on a PR GitHub merges (agent-fabric #237)")
        reset(); put("mergefail", ""); put("merged", "")
        rc, out = run("7", "--basis", "b")
        check("gh pr merge fails and the read-back is MERGED on the head: exit 0, said MERGED",
              rc == 0 and "MERGED #7" in out and "merged on head abcdef01" in out, out)
        check("…the failure said, not hidden", "gh pr merge failed on #7 (GraphQL: Merge already in progress" in out, out)
        reset(); put("mergefail", ""); put("armed", "")
        rc, out = run("7", "--basis", "b")
        check("gh pr merge fails and the PR reads armed on the head: exit 0, armed", rc == 0 and "ARMED #7" in out, out)
        reset(); put("mergefail", ""); put("inbase", "")
        rc, out = run("7", "--basis", "b")
        check("gh pr merge fails, the PR reads open and idle, its head is in the base: exit 0, merged, the API lagging",
              rc == 0 and "MERGED #7" in out and "is in origin/main" in out and "PR API is lagging" in out
              and "reads 'idle'" in out, out)
        check("…with no watcher line", "wait-merged" not in out, out)
        reset(); put("noarm", ""); put("inbase", "")
        rc, out = run("7", "--basis", "b")
        check("a merge call that succeeded, read back open while the head is in the base: exit 0, merged",
              rc == 0 and "MERGED #7" in out and "PR API is lagging" in out, out)
        reset(); put("mergefail", "")
        rc, out = run("7", "--basis", "b")
        check("gh pr merge fails, idle, the head not in the base: exit 2, the failure named",
              rc == 2 and "reads 'idle'" in out and "failed: GraphQL: Merge already in progress" in out
              and "MERGED #7" not in out, out)
        reset(); put("mergefail", ""); put("unasked", "")
        rc, out = run("7", "--basis", "b")
        check("…and when git could not be asked, that is said beside the exit 2",
              rc == 2 and "arm: could not ask git: the fake's reason" in out, out)
        reset(); put("mergefail", ""); put("nohead", "")
        rc, out = run("7", "--basis", "b")
        check("…a read-back that fails is asked of git too", rc == 2 and "landed" in calls(), calls())
        reset(); put("mergefail", ""); put("nohead", ""); put("inbase", "")
        rc, out = run("7", "--basis", "b")
        check("…and is merged when git says so", rc == 0 and "MERGED #7" in out and "reads 'unknown'" in out, out)
        reset(); put("inbase", ""); put("merged", "0123456789abcdef0123456789abcdef01234567")
        rc, out = run("7", "--basis", "b")
        check("merged on another head is not a lag: exit 2 whatever git says, git not asked",
              rc == 2 and "merged at 01234567" in out and "landed" not in calls(), out + calls())
        reset(); put("inbase", ""); put("closed", "")
        rc, out = run("7", "--basis", "b")
        check("closed is not a lag either", rc == 2 and "state CLOSED" in out and "landed" not in calls(), out + calls())
        reset(); put("inbase", ""); put("pushed", "")
        rc, out = run("7", "--basis", "b")
        check("…nor open on another head", rc == 2 and "open at 01234567" in out and "landed" not in calls(), out + calls())
        reset()
        rc, out = run("7", "--basis", "b", "--dry-run")
        check("dry run exits 0", rc == 0 and "DRY RUN" in out, out)
        check("…and names the command the run issues, pinned to the head",
              f"would run: gh pr merge 7 --merge --auto --match-head-commit {HEAD}" in out, out)
        check("dry run posts and arms nothing", "pr merge" not in calls() and "pr comment" not in calls(), calls())
        reset(); put("viewfail", "")
        rc, out = run("7", "--basis", "b"); check("unreadable PR: exit 2", rc == 2, out)
        print("arm: landed.head_in_base, on real git")
        from github import landed
        origin, clone = f"{sandbox}/origin.git", f"{sandbox}/clone"
        g = lambda repo, *a: subprocess.run(["git", "-C", repo, *a], env=git_env(), check=True, capture_output=True,
                                           text=True).stdout.strip()
        os.makedirs(clone)
        g(sandbox, "init", "-q", "--bare", "-b", "main", origin)
        g(clone, "init", "-q", "-b", "main")
        # origin says github.com, as a real clone's does; the bytes come from the bare repository beside it.
        g(clone, "remote", "add", "origin", "https://github.com/o/r.git")
        g(clone, "config", f"url.{origin}.insteadOf", "https://github.com/o/r.git")
        g(clone, "commit", "-q", "--allow-empty", "-m", "base")
        g(clone, "checkout", "-q", "-b", "feat")
        g(clone, "commit", "-q", "--allow-empty", "-m", "the pr's head")
        pr_head = g(clone, "rev-parse", "HEAD")
        g(clone, "commit", "-q", "--allow-empty", "-m", "never merged")
        unmerged = g(clone, "rev-parse", "HEAD")
        g(clone, "push", "-q", "origin", "main")
        with mock.patch.dict(os.environ, git_env(), clear=True):
            check("a head not yet in the base: False", landed.head_in_base("o/r", pr_head, "main", clone) is False)
            # GitHub's merge, made behind the clone's back: the clone learns of it only by the fetch.
            other = f"{sandbox}/other"
            g(sandbox, "clone", "-q", "-b", "main", origin, other)
            g(other, "fetch", "-q", clone, f"{pr_head}:refs/heads/feat")
            g(other, "merge", "-q", "--no-ff", "-m", "Merge pull request #7", "feat")
            g(other, "push", "-q", "origin", "main")
            check("the head merged on origin, the clone's origin/main stale: fetched, True",
                  landed.head_in_base("o/r", pr_head, "main", clone) is True)
            check("…the remote-tracking branch moved, FETCH_HEAD left alone",
                  g(clone, "rev-parse", "origin/main") == g(other, "rev-parse", "HEAD")
                  and not os.path.exists(f"{clone}/.git/FETCH_HEAD"))
            check("a later commit of the branch, never merged: False",
                  landed.head_in_base("o/r", unmerged, "main", clone) is False)
            check("a head this clone has never seen: False",
                  landed.head_in_base("o/r", "0" * 40, "main", clone) is False)
            check("the case of the repository's name does not matter", landed.head_in_base("O/R", pr_head, "main", clone) is True)
            said: list[str] = []
            check("origin is another repository (GH_REPO named this one): None, never asked",
                  landed.head_in_base("o/other", pr_head, "main", clone, note=said.append) is None)
            check("…and said, without the URL", said == [f"could not ask git whether {pr_head[:8]} is in origin/main:"
                                                         " this directory's origin is not o/other on github.com"], str(said))
            check("a base the remote does not have: None", landed.head_in_base("o/r", pr_head, "nope", clone) is None)
            check("an abbreviated head: None", landed.head_in_base("o/r", pr_head[:8], "main", clone) is None)
            check("a base that reads as an option: None", landed.head_in_base("o/r", pr_head, "--all", clone) is None)
            check("not a clone: None", landed.head_in_base("o/r", pr_head, "main", sandbox) is None)
            g(clone, "config", f"url.{sandbox}/gone.git.insteadOf", "https://github.com/o/r.git")
            g(clone, "config", "--unset", f"url.{origin}.insteadOf")
            said = []
            check("a fetch that fails: None, never the stale answer",
                  landed.head_in_base("o/r", pr_head, "main", clone, note=said.append) is None)
            check("…and said", said == [f"could not ask git whether {pr_head[:8]} is in origin/main: git fetch origin"
                                        " main failed"], str(said))
            said = []
            landed.head_in_base("o/r", pr_head, "main", sandbox, note=said.append)
            check("not a clone: said too", len(said) == 1 and said[0].startswith("could not ask git"), str(said))
            said = []
            landed.head_in_base("o/r", "", "main", clone, note=said.append)
            check("an unread head: said", said == ["could not ask git whether ? is in origin/main: the PR's head or"
                                                   " base was not read"], str(said))
        shutil.rmtree(clone); shutil.rmtree(other); shutil.rmtree(origin)

        print("arm: another project's rules — InterWeave's arm.json, through the shim")
        iw = {"AGENT_FABRIC_ARM_CONFIG": IW_CONFIG}
        for path in ("crates/identity/profile-identity/src/lib.rs", "crates/human/store/src/lib.rs",
                     "architecture/contracts/schemas/human-chat/envelope.schema.json",
                     "crates/transport/libp2p/src/dialing.rs", "apps/transportctl/src/phrase.rs",
                     "crates/discovery/kademlia/src/budgets.rs", "crates/discovery/cache/src/record.rs",
                     "crates/human/core/src/retention.rs", "architecture/config/config.schema.yaml",
                     "architecture/config/examples/kademlia-enabled.yaml",
                     "fixtures/identity/ed25519-bip39-entropy-v1.json", "Cargo.toml", ".cargo/config.toml",
                     ".cargo/config", "crates/human/ui-slint/.cargo/config.toml",
                     "tools/foo/.cargo/config.toml", "xtask/.cargo/config", "tools/foo/.Cargo/config.toml",
                     "deny.toml", "crates/claude/channel-core/src/lib.rs", "apps/claude-channel/src/main.rs",
                     "apps/human-desktop/src/recovery_seed.rs"):
            reset(reviewed=False); set_pr(me, "plain", [path]); set_gate(9)
            rc, out = run("7", "--basis", "b", fixture_rules=False, env=iw)
            check(f"InterWeave: {path} is a boundary", rc == 1 and "no review-class review" in out, out)
        reset(); set_pr(me, "plain", ["infra/db/migrations/0053_x.sql", "architecture/adr/0050-x.md",
                                      "crates/identity/profile-identity/README.md", "tools/checks/check_x.sh",
                                      "crates/human/ui-slint/Cargo.toml", "Cargo.lock", "fixtures/README.md", "crates/human/client-api/src/lib.rs",
                                      "crates/human/ui-slint/src/lib.rs"]); set_gate(9)
        rc, out = run("7", "--basis", "b", fixture_rules=False, env=iw)
        check("InterWeave: gzapp's migrations, prose, a crate README, tooling, the UI, a crate manifest, the lockfile and the fixtures' README are not",
              rc == 0 and "not a security-boundary change" in out, out)
        reset(); set_pr(me, "Class: docs-only", ["architecture/adr/0050-x.md"]); set_gate(2)
        rc, out = run("7", "--basis", "b", fixture_rules=False, env=iw)
        check("InterWeave has no classes: a stated docs-only under 8 still asks the owner",
              rc == 1 and "none in this project" in out, out)

        print("arm: a project whose arm.json cannot be used")
        reset(); put("narrowed.json", json.dumps({"boundary": {"paths": "^src/", "cases": ["src/a.rs", "keys/k.rs"]}}))
        set_pr(me, "plain", ["docs/a.md"]); set_gate(9)
        rc, out = run("7", "--basis", "b", fixture_rules=False, env={"AGENT_FABRIC_ARM_CONFIG": f"{state}/narrowed.json"})
        check("a boundary case its own patterns miss: exit 2, nothing armed, the case named",
              rc == 2 and "keys/k.rs" in out and "pr merge" not in calls(), out)
        reset(); put("bad.json", '{"boundary": {"paths": "("}}')
        rc, out = run("7", "--basis", "b", fixture_rules=False, env={"AGENT_FABRIC_ARM_CONFIG": f"{state}/bad.json"})
        check("an arm.json whose pattern does not compile: exit 2", rc == 2 and "not a usable arm.json" in out, out)
        reset(); set_pr("develop-qzapp/other/feat/x", "plain", ["docs/a.md"])
        rc, out = run("7", "--basis", "b", fixture_rules=False, env={"AGENT_FABRIC_ARM_CONFIG": f"{sandbox}/none.json"})
        check("…but gates 1–3 refuse without one", rc == 1 and "not this session's" in out, out)

        # ── the CLI layer: one smoke case per command and outcome ──────────
        # What the process adds to arm.main(): the exit status and the stream, the PATH lookup, the environment, the
        # working directory, the files read from disk, the arming policy and GitHub's settings as the process reads them,
        # and the readers run as programs. Which gate refuses, and why, is asserted above, in process.

        print("arm (CLI): usage and --help")
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9)
        rc, out, err = cli("7", split=True)
        check("usage: exit 2, on stderr", rc == 2 and "--basis" in err and out == "", err)
        rc, out, err = cli("--help", split=True)
        check("--help: exit 0, on stdout", rc == 0 and "SECURITY-BOUNDARY" in out and err == "", out)

        print("arm (CLI): a refusal, and a question gh could not answer")
        reset(reviewed=False); set_pr(me, "plain", mig); set_gate(9)
        rc, out, err = cli("7", "--basis", "b", split=True)
        check("a refusal: exit 1, on stderr, nothing armed or posted",
              rc == 1 and "arm: REFUSED #7 — a security-boundary change with no review-class review" in err and "REFUSED" not in out
              and "pr merge" not in calls() and "pr comment" not in calls(), err)
        check("…the review reader run as a program, asked for the PR as --json", "7 -q --json" in calls().splitlines(), calls())
        reset(); put("viewfail", "")
        rc, out, err = cli("7", "--basis", "b", split=True)
        check("unreadable PR: exit 2, on stderr", rc == 2 and "cannot read #7" in err and out == "" and "pr merge" not in calls(), err)
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9)
        rc, out = cli("7", "--basis", "b", env={"GH_REPO": "noslash"})
        check("GH_REPO with no owner: exit 2, never 1, nothing armed",
              rc == 2 and "cannot read the repository" in out and "pr merge" not in calls(), out)

        # The process reads the fleet policy file itself (no repository file in the settings repository), which
        # requires claude and asks codex as an additional review: the PRs it arms carry the claude review, and codex's
        # review, its unavailable marker for the head, or a basis saying it is absent.
        def both_reviewed() -> None:
            put("review_rc", "0"); put("blind", "abcdef01 abcdef01:codex")

        print("arm (CLI): the fleet policy file, read by the process")
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); put("review_rc", "0")
        rc, out, err = cli("7", "--basis", "b", split=True)
        check("only the claude review of the head: codex absent, armed on claude alone, the basis says so",
              rc == 0 and "codex: absent, no review or marker on abcdef01" in out and err == ""
              and calls().count(f"pr merge 7 --merge --auto --match-head-commit {HEAD}") == 1
              and "codex: absent, no review or marker on abcdef01: armed on the claude review alone." in calls(), out + err + calls())
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); put("review_rc", "0"); put("unavailable", f"{HEAD}@abcdef01:allowance")
        rc, out = cli("7", "--basis", "b", "--dry-run")
        check("…with codex's unavailable marker for the head: the claude review alone arms (dry run)",
              rc == 0 and "DRY RUN" in out and "codex unavailable (allowance)" in out and "pr merge" not in calls(), out + calls())

        print("arm (CLI): the arming path, the dry run, a merge on the arming")
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); both_reviewed()
        rc, out, err = cli("7", "--basis", "nine work commits at the review gate", split=True)
        check("exits 0, on stdout", rc == 0 and "ARMED #7" in out and err == "", out + err)
        check("gh pr merge --auto ran once, pinned to the head the gates read",
              calls().count(f"pr merge 7 --merge --auto --match-head-commit {HEAD}") == 1, calls())
        check("the basis comment carries the count and the head, on stdin",
              "pr comment 7 --body Arming basis: nine work commits at the review gate — 9 work commits, head abcdef01." in calls(), calls())
        check("prints the watcher line for the session", "fabric-pr wait-merged 7 &" in out, out)
        reset(); both_reviewed()
        rc, out = cli("7", "--basis", "b", "--dry-run")
        check("dry run: exit 0, names the command the run issues, posts and arms nothing",
              rc == 0 and "DRY RUN" in out and f"would run: gh pr merge 7 --merge --auto --match-head-commit {HEAD}" in out
              and "pr merge" not in calls() and "pr comment" not in calls(), out + calls())
        reset(); put("merged", ""); both_reviewed()
        rc, out = cli("7", "--basis", "b")
        check("a PR merged on the arming: exit 0, said merged, with no watcher line",
              rc == 0 and "MERGED #7" in out and "wait-merged" not in out, out)

        print("arm (CLI): a waiver, read by the relay and fabric-ctl as programs")
        reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(); set_presence(); both_reviewed()
        rc, out = cli("7", "--basis", "nine at the gate", "--no-boundary", why, "--waiver", mid, env=wenv)
        check("a waiver from the role's holder: armed, the comment records it, the readers run with their argv",
              rc == 0 and "boundary gate WAIVED by architect-cto-01" in out and "ARMED #7" in out
              and f"Boundary gate waived by architect-cto-01 ({mid}): {why}." in calls()
              and f"replay --replay {mid} --json" in calls() and "ctl architect-cto-01 presence --json" in calls(), out + calls())

        print("arm (CLI): the rules read from disk, and found from the clone's remote")
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9)
        rc, out = cli("7", "--basis", "b", fixture_rules=False, env={"AGENT_FABRIC_ARM_CONFIG": f"{sandbox}/none.json"})
        check("no arm.json on disk: exit 2, the boundary never judged absent",
              rc == 2 and "declares no arm.json" in out and "pr merge" not in calls(), out)
        # The operator the tool finds a clone's project in: a fixture registry and
        # InterWeave's arm.json at their places in a tree of its own.
        operator = f"{sandbox}/operator"
        os.makedirs(f"{operator}/projects/interweave/integration/gh")
        iw_remote = "git@github.com:fixture-org/interweave.git"
        # A registered project with no arm.json of its own: found, then refused, never judged by another's rules.
        bare_remote = "git@github.com:fixture-org/bare.git"
        with open(f"{operator}/projects/registry.json", "w") as fh:
            json.dump({"projects": {"interweave": {"remotes": [iw_remote]}, "bare": {"remotes": [bare_remote]}}}, fh)
        shutil.copy(IW_CONFIG, f"{operator}/projects/interweave/integration/gh/arm.json")
        os.makedirs(f"{operator}/identities/roles")
        shutil.copy(os.path.join(FIXTURES, "gzcoord-operator", "identities", "roles", "catalog.json"), f"{operator}/identities/roles/catalog.json")
        by_remote = {"AGENT_FABRIC_OPERATOR": operator}
        clones = {}
        for name, url in (("iw", iw_remote), ("bare", bare_remote), ("stranger", "git@github.com:nobody/unregistered.git")):
            d = f"{sandbox}/{name}"
            subprocess.run(["git", "init", "-q", d], env=git_env(base_env), check=True, timeout=30)
            subprocess.run(["git", "-C", d, "remote", "add", "origin", url], env=git_env(base_env), check=True, timeout=30)
            clones[name] = d
        reset(reviewed=False); set_pr(me, "plain", ["crates/transport/libp2p/src/dialing.rs"]); set_gate(9)
        rc, out = cli("7", "--basis", "b", fixture_rules=False, cwd=clones["iw"], env=by_remote)
        check("a clone of InterWeave is judged by InterWeave's rules (transport is a boundary there, not in gzapp's)",
              rc == 1 and "no review-class review" in out, out)
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9)
        rc, out = cli("7", "--basis", "b", fixture_rules=False, cwd=clones["stranger"], env=by_remote)
        check("a clone of an unregistered remote: exit 2, nothing armed",
              rc == 2 and "no project found" in out and "pr merge" not in calls(), out)
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9)
        rc, out = cli("7", "--basis", "b", fixture_rules=False, cwd=clones["bare"], env=by_remote)
        check("a clone of a registered project with no arm.json: exit 2, the file named, nothing armed",
              rc == 2 and "declares no arm.json" in out and "projects/bare/integration/gh/arm.json" in out
              and "pr merge" not in calls(), out)

    print("test_arm_cli: " + ("OK" if not fails else f"FAILED — {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
