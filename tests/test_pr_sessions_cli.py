#!/usr/bin/env python3
"""fabric-pr sessions, driven through the real script with a
mocked `gh` on PATH, so the assertions are about observable output, not
internals. Ported from runtime/github/test_pr-sessions.sh (ADR-040
Wave 6).

One smoke case per OUTCOME of the process: the exit status and the stream
and mode it writes, the argument refusal, a gh failure surfaced to the
caller, and what only exists when the process runs (the PATH lookup of gh,
GH_REPO, the working copy and hostname that name "this session", the role
binding read from the state directory). WHY a PR is listed, hidden,
disclosed or refused is verdict logic and lives in tests/test_pr_sessions.py,
which asserts it in-process, in a fraction of the time; a case added here
for a new reason that ends in an existing exit status and stream belongs
there.

The script shipped across five PRs with no automated coverage, and review
found four defects a test would have caught on the way in — the author
comparison that always rendered "!", the `/unresolved` filter that
reported "none" after a FAILED lookup, an argument parser that spun
forever on a missing operand, and bot branches attributed to a session
named after the bot.

Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import datetime
import json
import os
import pwd
import subprocess
import sys
import tempfile
from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory
scrub_process_env()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNDER_TEST = [os.path.join(ROOT, "bin", "fabric-pr"), "sessions"]
LOGIN = pwd.getpwuid(os.geteuid()).pw_name

GH_MOCK = r'''#!{python}
import json, os, sys
d, a = os.environ["GH_MOCK_DIR"], sys.argv[1:]
if a[:1] == ["pr"]:
    if os.environ.get("GH_MOCK_PRLIST_FAIL"):
        sys.exit(1)
    sys.stdout.write(open(os.path.join(d, "pr-list.json")).read())
    sys.exit(0)
if a[:1] == ["api"]:
    if os.environ.get("GH_MOCK_GRAPHQL_FAIL"):
        sys.exit(1)
    query = ""
    if "--input" in a:
        src = a[a.index("--input") + 1]
        query = json.load(sys.stdin if src == "-" else open(src)).get("query", "")
    if "reviewThreads" not in query:
        print("mock gh: no thread query on --input", file=sys.stderr)
        sys.exit(1)
    doc = json.load(open(os.path.join(d, "graphql.json")))
    print(json.dumps(doc))
    sys.exit(0)
print("mock gh: unhandled " + (a[0] if a else ""), file=sys.stderr)
sys.exit(1)
'''


def ago(**delta: float) -> str:
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(**delta)).strftime("%Y-%m-%dT%H:%M:%SZ")


def thread(resolved: bool, author: str) -> dict:
    return {"isResolved": resolved, "comments": {"nodes": [{"author": {"login": author}}]}}


def gql(prs: dict) -> dict:
    """{"data": {"repository": {"p<n>": …}}} from {n: (author, [threads])}."""
    repo = {}
    for n, (author, threads) in prs.items():
        repo[f"p{n}"] = {"number": n, "author": {"login": author}, "reviewThreads": {"nodes": threads}}
    return {"data": {"repository": repo}}


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    host = subprocess.run(["hostname", "-s"], stdout=subprocess.PIPE, text=True, check=True, timeout=10).stdout.strip()
    # The script derives "this clone" from `hostname -s` and the git
    # toplevel's basename, so the sandbox is a real repository with a known
    # directory name and the fixtures are written against that identity.
    clone_name = "legacy-testclone"
    me, other = f"{host}/{clone_name}", f"{host}/legacy-otherclone"

    with tempfile.TemporaryDirectory() as sandbox:
        clone, fixtures = f"{sandbox}/{clone_name}", f"{sandbox}/fixtures"
        for d in (clone, f"{sandbox}/bin", fixtures, f"{sandbox}/state-none"):
            os.makedirs(d)
        subprocess.run(["git", "-C", clone, "init", "-q"], check=True, timeout=30, stderr=subprocess.DEVNULL, env=git_env())
        with open(f"{sandbox}/bin/gh", "w", encoding="utf-8") as fh:
            fh.write(GH_MOCK.replace("{python}", sys.executable, 1))
        os.chmod(f"{sandbox}/bin/gh", 0o755)
        # No role unless a case plants one: the session running the suite
        # must not decide a bot row through its own binding.
        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_")) and k != "GIT_DIR"}
        # The repository the mock serves (gh.this_repo never reads gh's default).
        base["GH_REPO"] = "gzapi-org/gzapp"
        base.update(PATH=f"{sandbox}/bin:{base.get('PATH', '')}", GH_MOCK_DIR=fixtures,
                    AGENT_FABRIC_STATE_DIR=f"{sandbox}/state-none")

        def run(*args: str, **env: str) -> tuple[int, str]:
            r = subprocess.run(["timeout", "20", *UNDER_TEST, *args], cwd=clone, env={**base, **env},
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
            return r.returncode, r.stdout

        def write(name: str, doc) -> None:
            with open(f"{fixtures}/{name}", "w", encoding="utf-8") as fh:
                json.dump(doc, fh)

        def pr(n: int, state: str, branch: str, title: str, at: str) -> dict:
            return {"number": n, "state": state, "headRefName": branch, "title": title, "updatedAt": at,
                    "isDraft": False, "mergedAt": at if state == "MERGED" else None}

        def row(out: str, n: int) -> str:
            return "\n".join(ln for ln in out.split("\n") if f"#{n}" in ln)

        def default_pr_list() -> None:
            # Three PRs: two this session's, one another session's.
            write("pr-list.json", [pr(30, "OPEN", f"{me}/feat/alpha", "alpha", ago(hours=1)),
                                   pr(29, "MERGED", f"{other}/fix/beta", "beta", ago(hours=2)),
                                   pr(28, "MERGED", f"{me}/docs/gamma", "gamma", ago(hours=3))])

        def default_graphql() -> None:
            # #30 — one unresolved thread, reviewer spoke last  → "1!"
            # #29 — one unresolved thread, PR AUTHOR spoke last → "1" (no bang)
            # #28 — threads exist but all resolved              → "-"
            write("graphql.json", gql({30: ("andreabenetton", [thread(False, "some-reviewer")]),
                                       29: ("andreabenetton", [thread(False, "andreabenetton")]),
                                       28: ("andreabenetton", [thread(True, "some-reviewer")])}))

        print("pr-sessions: default scope, the text table")
        default_pr_list()
        default_graphql()
        rc, out = run()
        check("exits 0", rc == 0, out)
        check("shows this session's PRs, marked mine", row(out, 30).startswith("*") and "#28" in out, out)
        check("hides another session's PR", "#29" not in out, out)
        check("says it defaulted to this session", "Scoped to this session" in out, out)
        # The THR column is the thread lookup's whole round trip: the query on
        # stdin, the mock's answer, the bang. Each reason it reads otherwise
        # is the unit suite's.
        rc, out = run("/all")
        check("/all lists the other session's PR too, with the thread lookup's bang", "#29" in out and "1!" in row(out, 30), out)

        print("pr-sessions: --by-session groups the table")
        rc, out = run("/all", "--by-session")
        check("exits 0", rc == 0, out)
        check("groups under this session", me in out and "this session" in out, out)

        print("pr-sessions: --help lists every documented flag")
        rc, out = run("--help")
        check("exits 0", rc == 0, out)
        for flag in ("/all", "--by-session", "/lastItem", "/lastDate", "/unresolved"):
            check(f"documents {flag}", flag in out, out)

        print("pr-sessions: an argument refusal exits 2 — a missing operand is refused, not looped on")
        # `timeout` turns a regression here into exit 124 rather than a hung
        # suite; in-process it would hang the unit suite instead.
        rc, out = run("-n")
        check("bare -n exits 2", rc == 2, out)
        check("names the flag", "-n" in out, out)

        print("pr-sessions: a failed pr list is an invocation error")
        rc, out = run("/all", GH_MOCK_PRLIST_FAIL="1")
        check("exits 2", rc == 2, out)
        check("names the likely cause", "could not list PRs" in out, out)

        print("pr-sessions: a failed thread lookup reads as unknown, never zero")
        rc, out = run("/all", GH_MOCK_GRAPHQL_FAIL="1")
        check("listing still succeeds", rc == 0, out)
        check("THR shows unknown", "?" in out, out)
        rc, out = run("/all", "/unresolved", GH_MOCK_GRAPHQL_FAIL="1")
        check("/unresolved refuses to guess", rc == 2, out)
        check("says the lookup failed", "could not" in out, out)
        check("never claims there are none", "no PRs with unresolved review threads" not in out, out)

        print("pr-sessions: without GH_REPO the repository comes from the working copy")
        # The sandbox clone has no origin: gh.this_repo never reads gh's default.
        check("/unresolved refuses to guess without a repo", run("/all", "/unresolved", GH_REPO="")[0] == 2)

        print("pr-sessions: a Dependabot row is the devex-tooling ROLE's, read from the session's binding")
        # The binding is what identity.py --role reads, for this login, in
        # the state directory the environment names.
        write("pr-list.json", [
            pr(40, "OPEN", "dependabot/github_actions/actions-minor-patch-5c7bcdc794", "bump", ago(hours=1)),
            pr(41, "OPEN", "dependabot/nuget/apps/backend_dotnet/dotnet-minor-patch-04e2", "bump", ago(hours=2)),
            pr(42, "OPEN", f"{me}/feat/real", "real", ago(hours=3)),
            pr(43, "OPEN", "renovate/npm/vite-6.x", "bump", ago(hours=4))])
        write("graphql.json", gql({40: ("app/dependabot", []),
                                   41: ("app/dependabot", [thread(False, "reviewer[bot]")]),
                                   42: ("andreabenetton", []), 43: ("app/renovate", [])}))

        def plant_role(role: str) -> str:
            d = f"{sandbox}/state-{role}"
            os.makedirs(f"{d}/agents/{LOGIN}", exist_ok=True)
            with open(f"{d}/agents/{LOGIN}/binding.json", "w", encoding="utf-8") as fh:
                json.dump({"agent": LOGIN, "role": role}, fh)
            return d
        rc, out = run(AGENT_FABRIC_STATE_DIR=plant_role("devex-tooling"))
        check("exits 0", rc == 0, out)
        check("the bound role's default scope lists the Dependabot rows, marked mine",
              "#40" in out and row(out, 41).startswith("*"), out)
        check("and not the renovate row, which has no owner", "#43" not in out, out)

    print(f"\ntest_pr_sessions_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
