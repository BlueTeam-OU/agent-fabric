#!/usr/bin/env python3
"""fabric-pr sessions, driven through the real script with a
mocked `gh` on PATH, so the assertions are about observable output, not
internals. Ported from runtime/github/test_pr-sessions.sh (ADR-040
Wave 6), case for case.

The script shipped across five PRs with no automated coverage, and review
found four defects a test would have caught on the way in — the author
comparison that always rendered "!", the `/unresolved` filter that
reported "none" after a FAILED lookup, an argument parser that spun
forever on a missing operand, and bot branches attributed to a session
named after the bot.

The mock is faithful where it matters: GraphQL returns only what the
query asked for, so a fixture's pageInfo is served only to a query that
selects hasNextPage. Fixture timestamps are relative to now: the script
derives a /lastDate cutoff from the real clock, and a pinned fixture ages
out of its window on a date certain, failing a required check with
nothing in the diff to explain why. Plain script: prints ok/FAIL, exit 1
on any failure."""
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
    # The --limit actually requested, recorded on every call, so a case can
    # assert about the fetch that went out rather than the rendered page.
    if "--limit" in a:
        with open(os.path.join(d, "last-limit"), "w") as fh:
            fh.write(a[a.index("--limit") + 1] + "\n")
    sys.stdout.write(open(os.path.join(d, "pr-list.json")).read())
    sys.exit(0)
if a[:1] == ["api"]:
    if os.environ.get("GH_MOCK_GRAPHQL_FAIL"):
        sys.exit(1)
    query = ""
    if "--input" in a:
        src = a[a.index("--input") + 1]
        query = json.load(sys.stdin if src == "-" else open(src)).get("query", "")
    doc = json.load(open(os.path.join(d, "graphql.json")))
    # GRAPHQL RETURNS ONLY WHAT THE QUERY ASKED FOR: a fixture that
    # volunteers pageInfo the query never requested lets the script pass
    # while asking the real API for a field it then reads as absent.
    if "hasNextPage" not in query:
        for pr in ((doc.get("data") or {}).get("repository") or {}).values():
            if isinstance(pr, dict) and isinstance(pr.get("reviewThreads"), dict):
                pr["reviewThreads"].pop("pageInfo", None)
    print(json.dumps(doc))
    sys.exit(0)
print("mock gh: unhandled " + (a[0] if a else ""), file=sys.stderr)
sys.exit(1)
'''


def ago(**delta: float) -> str:
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(**delta)).strftime("%Y-%m-%dT%H:%M:%SZ")


def thread(resolved: bool, author: str) -> dict:
    return {"isResolved": resolved, "comments": {"nodes": [{"author": {"login": author}}]}}


def gql(prs: dict, paged: bool = False) -> dict:
    """{"data": {"repository": {"p<n>": …}}} from {n: (author, [threads], has_next)}."""
    repo = {}
    for n, (author, threads, has_next) in prs.items():
        rt: dict = {"nodes": threads}
        if paged:
            rt = {"pageInfo": {"hasNextPage": has_next}, "nodes": threads}
        repo[f"p{n}"] = {"number": n, "author": {"login": author}, "reviewThreads": rt}
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
            write("graphql.json", gql({30: ("andreabenetton", [thread(False, "some-reviewer")], False),
                                       29: ("andreabenetton", [thread(False, "andreabenetton")], False),
                                       28: ("andreabenetton", [thread(True, "some-reviewer")], False)}))

        print("pr-sessions: default scope")
        default_pr_list()
        default_graphql()
        rc, out = run()
        check("exits 0", rc == 0, out)
        check("shows this session's PR", "#30" in out, out)
        check("shows this session's other PR", "#28" in out, out)
        check("hides another session's PR", "#29" not in out, out)
        check("says it defaulted to this session", "Scoped to this session" in out, out)

        print("pr-sessions: /all")
        rc, out = run("/all")
        check("exits 0", rc == 0, out)
        check("includes the other session's PR", "#29" in out, out)
        check("still includes this session's", "#30" in out, out)

        print("pr-sessions: explicit session filter")
        rc, out = run("--session", "legacy-otherclone")
        check("exits 0", rc == 0, out)
        check("matches the named session", "#29" in out, out)
        check("excludes the other session", "#30" not in out, out)

        print("pr-sessions: state filter is chosen at fetch time")
        check("exits 0", run("/OPEN")[0] == 0)

        print("pr-sessions: conflicting state flags are refused")
        rc, out = run("/OPEN", "/MERGED")
        check("exits 2", rc == 2, out)
        check("names the conflict", "conflict" in out, out)

        print("pr-sessions: grouped output")
        rc, out = run("/all", "--by-session")
        check("exits 0", rc == 0, out)
        check("groups under this session", me in out, out)
        check("marks this session", "this session" in out, out)

        print("pr-sessions: empty result is a clean exit, not an error")
        write("pr-list.json", [])
        rc, out = run()
        check("exits 0", rc == 0, out)
        check("says nothing matched", "no PRs" in out, out)
        default_pr_list()

        print("pr-sessions: THR column reflects the thread lookup")
        rc, out = run("/all")
        check("exits 0", rc == 0, out)
        # "1!" — a reviewer spoke last on #30, so a reply is owed.
        check("flags a thread awaiting a reply", "1!" in out, out)
        # #29's unresolved thread was last answered by the PR AUTHOR: the
        # count stands alone, answered but not resolved — the case a
        # comparison read off the thread node (no such field) could not
        # express, giving every row a bang.
        check("no bang when the author answered last", "1!" not in row(out, 29), row(out, 29))
        # #28's threads are all resolved → "-"; a broken resolved filter
        # would read "1".
        check("shows resolved-only PRs as a dash", "-" in out, out)

        print("pr-sessions: --no-threads skips the lookup")
        rc, out = run("/all", "--no-threads")
        check("exits 0", rc == 0, out)
        check("no bang without the lookup", "1!" not in out, out)

        print("pr-sessions: /unresolved needs the lookup")
        rc, out = run("/unresolved", "--no-threads")
        check("exits 2", rc == 2, out)
        check("explains the conflict", "drop --no-threads" in out, out)

        print("pr-sessions: /unresolved keeps only PRs with open threads")
        rc, out = run("/all", "/unresolved")
        check("exits 0", rc == 0, out)
        check("keeps #30", "#30" in out, out)
        check("keeps #29", "#29" in out, out)
        check("drops the resolved-only PR", "#28" not in out, out)

        print("pr-sessions: a truncated thread page reads UNKNOWN, not zero")
        # Only the first 100 threads arrive: a PR whose open thread sits on
        # page two looks clean, which hides precisely the outstanding work
        # this command exists to surface. #30 and #29 keep their counts, so
        # the "?" can only have come from the truncated #28.
        write("graphql.json", gql({30: ("andreabenetton", [thread(False, "some-reviewer")], False),
                                   29: ("andreabenetton", [thread(False, "andreabenetton")], False),
                                   28: ("andreabenetton", [thread(True, "some-reviewer")], True)}, paged=True))
        rc, out = run("/all")
        check("exits 0", rc == 0, out)
        check("renders the truncated count as unknown", "?" in out, out)
        check("does not claim zero open threads", " -  " not in out, out)
        rc, out = run("/all", "/unresolved")
        check("exits 0", rc == 0, out)
        check("keeps the pr rather than dropping it", "#28" in out, out)
        default_graphql()

        print("pr-sessions: an older branch named for this working copy is this agent's own")
        write("pr-list.json", [{"number": 731, "state": "OPEN", "isDraft": False,
                                "headRefName": f"{host}/{clone_name}/fix/mine-under-the-old-name", "updatedAt": ago(hours=1)}])
        rc, out = run("--no-threads")
        check("exits 0", rc == 0, out)
        check("the legacy-named row is in the default (mine) scope", "#731" in out, out)
        check("and marked as this session's", "* #731" in out, out)
        write("pr-list.json", [{"number": 732, "state": "OPEN", "isDraft": False,
                                "headRefName": f"{host}/legacy-old/fix/theirs", "updatedAt": ago(hours=1)}])
        check("another working copy's older branch is not in the mine scope", "#732" not in run("--no-threads")[1])
        check("nor is it unattributed: it names a session", "#732" not in run("/unattributed", "--no-threads")[1])
        check("it is listed under /all, as that session's", "#732" in run("/all", "--no-threads")[1])
        # A clone named after its repository is every login's default clone:
        # its name is no session's, and an older branch under it is not mine.
        subprocess.run(["git", "-C", clone, "remote", "add", "origin", f"git@example.com:org/{clone_name}.git"],
                       check=True, timeout=30, env=git_env())
        write("pr-list.json", [{"number": 733, "state": "OPEN", "isDraft": False,
                                "headRefName": f"{host}/{clone_name}/fix/under-the-repo-name", "updatedAt": ago(hours=1)}])
        check("a branch named for the repository is no session's", "#733" not in run("--no-threads")[1])
        subprocess.run(["git", "-C", clone, "remote", "remove", "origin"], check=True, timeout=30, env=git_env())
        default_pr_list()

        print("pr-sessions: pool filters")
        rc, out = run("/all", "/lastItem:1")
        check("exits 0", rc == 0, out)
        check("keeps the newest PR", "#30" in out, out)
        check("drops everything older", "#29" not in out, out)
        rc, out = run("/all", "/lastDate:99d")
        check("/lastDate accepts <N>d", rc == 0, out)
        check("keeps PRs in the window", "#30" in out, out)
        # A TIGHT window keeps the fixtures honest: one day is outside a
        # pinned fixture's reach almost at once.
        rc, out = run("/all", "/lastDate:1d")
        check("/lastDate:1d exits 0", rc == 0, out)
        check("fixtures are recent enough for a tight window", "#30" in out, out)

        print("pr-sessions: /unresolved honours an explicit /lastItem")
        # The 100-row candidate cap was once applied after /lastItem: the
        # caller named a number and silently got a different one. 150 rows,
        # every thread RESOLVED but the oldest's, #151.
        t = ago(hours=1)
        write("pr-list.json", [pr(300 - i, "MERGED", f"{me}/feat/p{i}", "p", t) for i in range(150)])
        write("graphql.json", gql({300 - i: ("andreabenetton", [thread(300 - i != 151, "some-reviewer")], False)
                                   for i in range(150)}, paged=True))
        rc, out = run("/all", "-n", "200", "/lastItem:150", "/unresolved")
        check("exits 0", rc == 0, out)
        check("queries past the 100-row cap", "#151" in out, out)
        check("and still drops the resolved ones", "#300" not in out, out)
        default_pr_list()
        default_graphql()

        print("pr-sessions: malformed pool filters are refused")
        rc, out = run("/lastItem:0")
        check("/lastItem:0 exits 2", rc == 2, out)
        check("names the expectation", "positive integer" in out, out)
        check("empty /lastItem exits 2", run("/lastItem:")[0] == 2)
        rc, out = run("/lastDate:5")
        check("unit-less /lastDate exits 2", rc == 2, out)
        check("names the accepted units", "<N>d" in out, out)
        check("empty /lastDate exits 2", run("/lastDate:")[0] == 2)

        print("pr-sessions: unknown options are refused")
        rc, out = run("--nope")
        check("exits 2", rc == 2, out)
        check("points at --help", "--help" in out, out)

        print("pr-sessions: --help lists every documented flag")
        rc, out = run("--help")
        check("exits 0", rc == 0, out)
        for flag in ("/all", "--by-session", "/lastItem", "/lastDate", "/unresolved"):
            check(f"documents {flag}", flag in out, out)

        print("pr-sessions: a missing operand is refused, not looped on")
        # `timeout` turns a regression here into exit 124 rather than a hung
        # suite.
        rc, out = run("-n")
        check("bare -n exits 2", rc == 2, out)
        check("names the flag", "-n" in out, out)
        check("bare --session exits 2", run("--session")[0] == 2)

        print("pr-sessions: a non-numeric limit is refused before arithmetic")
        # An unvalidated limit in bash arithmetic was code execution: an
        # array subscript evaluates a command substitution.
        pwned = f"{sandbox}/pwned"
        rc, out = run("-n", f'x[$(touch "{pwned}")]')
        check("injected limit exits 2", rc == 2, out)
        check("arithmetic injection did not execute", not os.path.exists(pwned), out)
        rc, out = run("-n", "abc")
        check("non-numeric limit exits 2", rc == 2, out)
        check("names the expectation", "positive integer" in out, out)

        print("pr-sessions: a Dependabot branch is not a session — it is the devex-tooling ROLE's")
        # The vendor deny-list says a bot branch names no session; a
        # Dependabot row resolves to role:devex-tooling (architect-cto,
        # 2026-09-14). A bot with no owner in the map stays unattributed.
        write("pr-list.json", [
            pr(40, "OPEN", "dependabot/github_actions/actions-minor-patch-5c7bcdc794", "bump", ago(hours=1)),
            pr(41, "OPEN", "dependabot/nuget/apps/backend_dotnet/dotnet-minor-patch-04e2", "bump", ago(hours=2)),
            pr(42, "OPEN", f"{me}/feat/real", "real", ago(hours=3)),
            pr(43, "OPEN", "renovate/npm/vite-6.x", "bump", ago(hours=4))])
        write("graphql.json", gql({40: ("app/dependabot", [], False),
                                   41: ("app/dependabot", [thread(False, "reviewer[bot]")], False),
                                   42: ("andreabenetton", [], False), 43: ("app/renovate", [], False)}))
        rc, out = run("/all")
        check("exits 0", rc == 0, out)
        # The branch name shows in the WORK column too, so the claim is
        # about each row's SESSION column.
        for n in (40, 41):
            r = row(out, n)
            check(f"#{n} is the devex-tooling role's", "role:devex-tooling" in r and "(unconventional)" not in r, r)
        check("#43 (a bot with no owner in the map) stays unattributed", "(unconventional)" in row(out, 43), row(out, 43))
        check("a real session branch still resolves", me in out, out)

        # ROLE SCOPE. A session bound to devex-tooling sees the Dependabot
        # rows in its DEFAULT scope and in /unresolved; one bound to any
        # other role does not, and neither counts them as unattributed. The
        # binding is what identity.py --role reads, for this login.
        def plant_role(role: str) -> str:
            d = f"{sandbox}/state-{role}"
            os.makedirs(f"{d}/agents/{LOGIN}", exist_ok=True)
            with open(f"{d}/agents/{LOGIN}/binding.json", "w", encoding="utf-8") as fh:
                json.dump({"agent": LOGIN, "role": role}, fh)
            return d
        rc, out = run(AGENT_FABRIC_STATE_DIR=plant_role("devex-tooling"))
        check("devex-tooling default scope: exits 0", rc == 0, out)
        check("devex-tooling default scope lists the Dependabot row #40", "#40" in out, out)
        check("devex-tooling default scope lists the Dependabot row #41", "#41" in out, out)
        check("devex-tooling default scope does not list the renovate row", "#43" not in out, out)
        check("the Dependabot row is marked mine (*)", row(out, 41).startswith("*"), row(out, 41))
        rc, out = run("/unresolved", AGENT_FABRIC_STATE_DIR=plant_role("devex-tooling"))
        check("devex-tooling /unresolved: exits 0", rc == 0, out)
        check("devex-tooling /unresolved surfaces the Dependabot thread", "#41" in out, out)
        check("devex-tooling /unresolved does not surface a resolved bot row", "#40" not in out, out)
        rc, out = run(AGENT_FABRIC_STATE_DIR=plant_role("backend-dev"))
        check("backend-dev default scope: exits 0", rc == 0, out)
        check("backend-dev default scope does not list #40", "#40" not in out, out)
        check("backend-dev default scope does not list #41", "#41" not in out, out)
        check("the NOTE counts only the unowned bot row", "1 PR(s) name no live session" in out, out)
        default_pr_list()
        default_graphql()

        print("pr-sessions: a session branch is attributed by SHAPE, not a type vocabulary")
        # A <type> vocabulary once classified spike-3/, hotfix/ and stage-4/
        # branches as unconventional and the default scope then SILENTLY
        # DROPPED them. Only the shape is specified, so only it is checked.
        write("pr-list.json", [pr(50, "OPEN", f"{me}/spike-3/beacon-parse", "spike", ago(hours=1)),
                               pr(51, "OPEN", f"{me}/hotfix/regime-strip", "hotfix", ago(hours=2)),
                               pr(52, "OPEN", f"{me}/feat/known-type", "feat", ago(hours=3))])
        write("graphql.json", gql({n: ("andreabenetton", [], False) for n in (50, 51, 52)}))
        # DEFAULT scope, not /all: the drop happens in the scope filter.
        rc, out = run()
        check("exits 0", rc == 0, out)
        check("an unlisted <type> is still this session's work", "#50" in out, out)
        check("  and so is another one", "#51" in out, out)
        check("a conventional type is unaffected", "#52" in out, out)
        check("none of them read as unattributed", "(unconventional)" not in out, out)

        print("pr-sessions: a branch with too few segments is still unattributed")
        write("pr-list.json", [pr(53, "OPEN", "agent/global-event-identity", "agent", ago(hours=1))])
        write("graphql.json", gql({53: ("andreabenetton", [], False)}))
        rc, out = run("/all")
        check("exits 0", rc == 0, out)
        check("#53 is not attributed to a session", "(unconventional)" in row(out, 53), row(out, 53))
        default_pr_list()
        default_graphql()

        print("pr-sessions: PRs no scope filter can attribute are disclosed, not dropped")
        # Removing an unparsable row SILENTLY is how a listing looks complete
        # when it is not, so the count is stated on every path that exits.
        def unscopable_list() -> None:
            write("pr-list.json", [pr(60, "OPEN", "add-claude-github-actions-1785994932117", "hand-made", ago(hours=1)),
                                   pr(61, "OPEN", f"{me}/feat/real", "real", ago(hours=2))])
            write("graphql.json", gql({60: ("andreabenetton", [], False), 61: ("andreabenetton", [], False)}))
        unscopable_list()
        rc, out = run()
        check("exits 0", rc == 0, out)
        check("the footer path discloses the omission", "cannot be scoped to a" in out, out)
        check("  and counts them", "1 PR(s) name no live session" in out, out)

        print("pr-sessions: /all reports nothing omitted, because nothing was scoped away")
        rc, out = run("/all")
        check("exits 0", rc == 0, out)
        check("no disclosure when no filter acted", "cannot be scoped to a" not in out, out)

        print("pr-sessions: the disclosure survives the no-rows early exit")
        # The reassuring "no PRs" is the answer a reader acts on, so it is
        # where a footer-only disclosure would be missing.
        write("pr-list.json", [pr(62, "OPEN", "add-claude-github-actions-1785994932117", "hand-made", ago(hours=1))])
        write("graphql.json", {"data": {"repository": {}}})
        rc, out = run()
        check("exits 0", rc == 0, out)
        check("says there are no PRs for this session", "no PRs for this session" in out, out)
        check("  and still discloses the omission", "cannot be scoped to a" in out, out)

        print("pr-sessions: the disclosure survives the /unresolved-empty early exit")
        unscopable_list()
        rc, out = run("/unresolved")
        check("exits 0", rc == 0, out)
        check("says nothing is unresolved", "no PRs with unresolved" in out, out)
        check("  and still discloses the omission", "cannot be scoped to a" in out, out)

        print("pr-sessions: /unattributed lists exactly the rows no scope can reach")
        unscopable_list()
        rc, out = run("/unattributed")
        check("exits 0", rc == 0, out)
        check("lists the unscopable PR", "#60" in out, out)
        check("excludes an owned PR", "#61" not in out, out)

        print("pr-sessions: /unattributed does not warn about omitting what it just listed")
        check("no self-contradicting disclosure", "cannot be scoped to a" not in out, out)

        print("pr-sessions: /unattributed does not claim any row is this session's")
        check("drops the ownership legend", "* = " not in out, out)
        check("says the findings are unowned", "no session" in out, out)

        print("pr-sessions: the NOTE points at the flag that can actually list them")
        unscopable_list()
        rc, out = run()
        check("exits 0", rc == 0, out)
        check("names the listing flag", "/unattributed" in out, out)

        print("pr-sessions: two different scope flags are refused, not last-wins")
        rc, out = run("/unattributed", "/all")
        check("exits 2", rc == 2, out)
        check("names the conflict", "different scopes" in out, out)
        check("exits 2 the other way round too", run("/all", "/unattributed")[0] == 2)
        check("the same scope twice is fine", run("/unattributed", "/unattributed")[0] == 0)

        print("pr-sessions: --session unconventional is the same scope, not a second one")
        unscopable_list()
        rc, out = run("--session", "unconventional")
        check("exits 0", rc == 0, out)
        check("lists the unscopable PR", "#60" in out, out)
        check("no self-contradicting disclosure", "cannot be scoped to a" not in out, out)
        check("drops the ownership legend", "* = " not in out, out)
        default_pr_list()
        default_graphql()

        print("pr-sessions: /unattributed narrows BEFORE the thread lookup")
        # The pool must exceed the 100-row candidate slice or the claim is not
        # falsifiable: 150 owned rows numbered above the one unowned row put
        # it at position 151, outside the slice unless the scope came first.
        write("pr-list.json", [pr(70, "MERGED", "agent/global-event-identity", "unowned", ago(hours=1))]
              + [{**pr(200 + i, "OPEN", f"{me}/feat/w{i}", "w", ago(hours=2))} for i in range(150)])
        write("graphql.json", gql({70: ("andreabenetton", [thread(False, "reviewer[bot]"), thread(False, "reviewer[bot]")],
                                        False)}, paged=True))
        rc, out = run("/unattributed", "/unresolved")
        check("exits 0", rc == 0, out)
        check("surfaces the unowned PR", "#70" in out, out)
        check("with a real awaiting-reply count", "2!" in out, out)

        print("pr-sessions: /unattributed with nothing to show is a clean, named exit")
        default_pr_list()
        default_graphql()
        rc, out = run("/unattributed")
        check("exits 0", rc == 0, out)
        check("names this scope, not another", "without a parsable session branch" in out, out)
        check("does not claim it scoped to the session", "PRs for this session" not in out, out)

        print("pr-sessions: /unattributed and /unresolved with nothing to show names the scope")
        # The /unresolved-empty exit needs a row that EXISTS under this scope
        # and has nothing open; with none the rows-empty exit fires instead.
        write("pr-list.json", [pr(72, "MERGED", "agent/common-api-idempotency", "unowned", ago(hours=1))])
        write("graphql.json", gql({72: ("andreabenetton", [thread(True, "reviewer[bot]")], False)}, paged=True))
        rc, out = run("/unattributed", "/unresolved")
        check("exits 0", rc == 0, out)
        check("names the unowned scope", "branches no session owns" in out, out)
        check("not the session scope", "for this session" not in out, out)
        default_pr_list()
        default_graphql()

        print("pr-sessions: the count describes the NARROWED pool, not everything fetched")
        # #60 is outside a one-item pool, so there is nothing to disclose.
        unscopable_list()
        rc, out = run("/lastItem:1")
        check("exits 0", rc == 0, out)
        check("does not announce a PR outside the pool", "cannot be scoped to a" not in out, out)
        default_pr_list()
        default_graphql()

        print("pr-sessions: an invalid --session regex is an invocation error")
        # Swallowing a bad pattern printed "no matching PRs" and exited 0 —
        # the reassuring answer a genuinely empty result gives.
        rc, out = run("--session", "[")
        check("exits 2", rc == 2, out)
        check("says the filter was rejected", "session" in out, out)
        check("does not claim an empty result", "no PRs for a session" not in out, out)

        print("pr-sessions: a failed thread lookup reads as unknown, never zero")
        rc, out = run("/all", GH_MOCK_GRAPHQL_FAIL="1")
        check("listing still succeeds", rc == 0, out)
        check("THR shows unknown", "?" in out, out)
        rc, out = run("/all", "/unresolved", GH_MOCK_GRAPHQL_FAIL="1")
        check("/unresolved refuses to guess", rc == 2, out)
        check("says the lookup failed", "could not" in out, out)
        check("never claims there are none", "no PRs with unresolved review threads" not in out, out)
        check("/unresolved refuses to guess without a repo", run("/all", "/unresolved", GH_REPO="")[0] == 2)

        print("pr-sessions: a failed pr list is an invocation error")
        rc, out = run("/all", GH_MOCK_PRLIST_FAIL="1")
        check("exits 2", rc == 2, out)
        check("names the likely cause", "could not list PRs" in out, out)

        print("pr-sessions: /lastItem beyond the derived cap is honoured, not clamped")
        rc, out = run("/all", "/lastItem:600", "--no-threads")
        check("exits 0", rc == 0, out)
        try:
            with open(f"{fixtures}/last-limit", encoding="utf-8") as fh:
                requested = fh.read().strip()
        except OSError:
            requested = "missing"
        check("fetches the full 600-PR pool", requested == "600", f"gh pr list --limit was '{requested}', wanted 600")

        print("pr-sessions: a full /lastDate page warns that the window may be short")
        # The warning fires when the fetch came back full: -n 10 puts the
        # derived fetch at its 200 floor, which the fixture fills exactly.
        write("pr-list.json", [pr(500 - i, "OPEN", f"{me}/feat/w{i}", "w", ago(hours=1)) for i in range(200)])
        rc, out = run("/all", "-n", "10", "/lastDate:99d", "--no-threads")
        check("exits 0", rc == 0, out)
        check("warns that the window may be truncated", "may be" in out, out)


    print(f"\ntest_pr_sessions_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
