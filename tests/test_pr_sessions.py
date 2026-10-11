#!/usr/bin/env python3
"""Tests for tools/fabric/github/pr_sessions.py: its internals, and the
verdict logic of a whole run. The CLI suite, tests/test_pr_sessions_cli.py,
keeps one smoke case per outcome of the real script (ADR-040 §5 rule 5);
every reason a run lists, hides, discloses or refuses a PR is asserted here
instead, in-process, with gh and the identity replaced by `drive`: who owns
a branch, the /lastDate span, the THR column's "!" rule, the
unknown-is-not-zero reading of a thread page, the scope and pool filters,
the omission disclosure on every exit path."""
from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from github import pr_reply, pr_sessions as ps, pr_sessions_owner as pso  # noqa: E402


def ago(**delta: float) -> str:
    # Relative to now: a run derives its /lastDate cutoff from the real
    # clock, and a pinned fixture ages out of its window on a date certain.
    return (datetime.now(timezone.utc) - timedelta(**delta)).strftime("%Y-%m-%dT%H:%M:%SZ")


def pr(n: int, branch: str, state: str = "OPEN", at: str | None = None) -> dict:
    at = at or ago(hours=1)
    return {"number": n, "state": state, "headRefName": branch, "title": "t", "updatedAt": at,
            "isDraft": False, "mergedAt": at if state == "MERGED" else None}


def thread(resolved: bool, author: str) -> dict:
    return {"isResolved": resolved, "comments": {"nodes": [{"author": {"login": author}}]}}


def gql(prs: dict, paged: bool = False) -> dict:
    """The GraphQL `data` for {n: (author, [threads], has_next)}."""
    repo = {}
    for n, (author, threads, has_next) in prs.items():
        rt: dict = {"pageInfo": {"hasNextPage": has_next}, "nodes": threads} if paged else {"nodes": threads}
        repo[f"p{n}"] = {"number": n, "author": {"login": author}, "reviewThreads": rt}
    return {"repository": repo}


def row(out: str, n: int) -> str:
    return "\n".join(ln for ln in out.split("\n") if f"#{n}" in ln)


def drive(argv: list[str], rows: list[dict], threads: dict | None = None, who: tuple[str, str, str] = ("h/agent", "h/clonename", ""),
          list_fails: bool = False, repo: str = "o/r") -> tuple[int, str, dict]:
    """(exit status, stdout and stderr merged, what reached gh) of `fabric-pr
    sessions argv` run in-process: `gh pr list` answers rows, `gh api graphql`
    answers the `threads` data (None: the call fails), the session is `who`.
    Faithful where it matters, as the CLI suite's gh is: GraphQL returns only
    what the query asked for, so a fixture's pageInfo is served only to a query
    that selects hasNextPage, and only the PRs the query named."""
    seen: dict = {"state": None, "limit": None, "looked_up": None}

    def pr_list(fields, *, state="open", limit=1000, **_):
        seen.update(state=state, limit=limit)
        if list_fails:
            raise ps.gh.GhError("gh pr list", "boom")
        return [dict(r) for r in rows]

    def graphql(query, **variables):
        seen["looked_up"] = sorted(int(k[1:]) for k in variables if k[0] == "n" and k[1:].isdigit())
        if threads is None:
            raise ps.gh.GhError("gh api graphql", "boom")
        served = {}
        for alias, p in threads["repository"].items():
            if p["number"] in seen["looked_up"]:
                rt = dict(p["reviewThreads"])
                if "hasNextPage" not in query:
                    rt.pop("pageInfo", None)
                served[alias] = {**p, "reviewThreads": rt}
        return {"repository": served}

    patched = [(ps.gh, "pr_list", pr_list), (ps.gh, "graphql", graphql), (ps.gh, "this_repo", lambda *a, **k: repo),
               (ps, "who_am_i", lambda: who), (ps.shutil, "which", lambda name: "/bin/" + name)]
    saved = [(o, n, getattr(o, n)) for o, n, _ in patched]
    argv0, buf = sys.argv, io.StringIO()
    try:
        for o, n, v in patched:
            setattr(o, n, v)
        sys.argv = ["pr-sessions", *argv]
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = ps.main()
    finally:
        sys.argv = argv0
        for o, n, v in saved:
            setattr(o, n, v)
    return rc, buf.getvalue(), seen


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    def refused(argv: list[str]) -> str:
        try:
            ps.parse(argv)
        except ps.Die as e:
            return str(e)
        return ""

    # ── who owns a branch ────────────────────────────────────────────
    check("a four-segment branch is its first two segments' session", ps.session_of("h/l/feat/x") == "h/l")
    check("the work starts at the third segment", ps.work_of("h/l/feat/deep/er") == "feat/deep/er")
    check("any <type> word is a session's", ps.session_of("h/l/Fix/x") == "h/l" and ps.session_of("h/l/chore(gh)/x") == "h/l")
    check("three segments are unattributed, their work the whole branch",
          ps.session_of("agent/x/y") == ps.UNATTRIBUTED and ps.work_of("agent/x/y") == "agent/x/y")
    check("an empty host or clone is unattributed", ps.session_of("/l/feat/x") == ps.UNATTRIBUTED
          and ps.session_of("h//feat/x") == ps.UNATTRIBUTED)
    check("a vendor with four segments is no session", ps.session_of("renovate/npm/apps/x") == ps.UNATTRIBUTED)
    check("a Dependabot branch is the devex-tooling role's, at any depth",
          ps.session_of("dependabot/nuget/apps/x/y") == "role:devex-tooling" and ps.session_of("dependabot/x") == "role:devex-tooling")
    check("pr-reply and pr-sessions read one predicate", ps.conventional("h/l/feat/x") == pr_reply.branch_names_a_session("h/l/feat/x")
          and ps.BOT_OWNER == {"dependabot": "role:devex-tooling"})

    me = ps.Me("h/agent", "h/clonename", "devex-tooling")
    check("this agent's prefix is mine", me.owns("h/agent"))
    check("the working copy's older prefix is mine", me.owns("h/clonename"))
    check("the held role's bot rows are mine", me.owns("role:devex-tooling"))
    check("another session, another role are not", not me.owns("h/other") and not me.owns("role:backend-dev"))
    check("no legacy name and no role match nothing by emptiness",
          not ps.Me("h/agent", "", "").owns("") and not ps.Me("h/agent", "", "").owns("role:"))

    # ── /lastDate ────────────────────────────────────────────────────
    at = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    check("<N>d counts days", ps.cutoff_for("2d", at) == "2026-09-28T12:00:00Z")
    check("<N>h counts hours", ps.cutoff_for("6h", at) == "2026-09-30T06:00:00Z")
    check("<N>m counts minutes", ps.cutoff_for("90m", at) == "2026-09-30T10:30:00Z")
    check("a bare number is refused, not assumed to be days", ps.cutoff_for("5", at) is None)
    check("zero, a leading zero, an unknown unit and empty are refused",
          all(ps.cutoff_for(s, at) is None for s in ("0d", "05d", "5x", "", "d", "-1d", "1.5d", " 1d")))
    try:
        ps.cutoff_for("99999999999d", at)
        check("a span the calendar cannot hold fails, as date did", False)
    except OverflowError:
        check("a span the calendar cannot hold fails, as date did", True)

    # ── the THR column ───────────────────────────────────────────────
    data = {"repository": {
        "p1": {"number": 1, "author": {"login": "me"}, "reviewThreads": {"pageInfo": {"hasNextPage": False}, "nodes": [
            {"isResolved": False, "comments": {"nodes": [{"author": {"login": "rev"}}]}}]}},
        "p2": {"number": 2, "author": {"login": "me"}, "reviewThreads": {"nodes": [
            {"isResolved": False, "comments": {"nodes": [{"author": {"login": "me"}}]}}]}},
        "p3": {"number": 3, "author": {"login": "me"}, "reviewThreads": {"nodes": [
            {"isResolved": True, "comments": {"nodes": [{"author": {"login": "rev"}}]}}]}},
        "p4": {"number": 4, "author": {"login": "me"}, "reviewThreads": {"pageInfo": {"hasNextPage": True}, "nodes": [
            {"isResolved": True, "comments": {"nodes": []}}]}},
        "p5": {"number": 5, "author": None, "reviewThreads": {"nodes": [
            {"isResolved": False, "comments": {"nodes": []}}]}},
        "p6": {"number": 6, "author": {"login": "me"}, "reviewThreads": {"nodes": []}},
    }}
    threads = ps.thread_counts(data)
    col = lambda n, want=True, th=threads: ps.thr_column({"number": n}, th, want)  # noqa: E731
    check("the reviewer spoke last: the count and a bang", col(1) == "1!")
    check("the PR author spoke last: the count alone", col(2) == "1")
    check("only resolved threads: a dash", col(3) == "-")
    check("no threads at all: a dash", col(6) == "-")
    check("a truncated page is unknown, not zero", col(4) == "?")
    check("a PR the answer lacks is unknown", col(99) == "?")
    check("a thread with no comment and no PR author counts as awaiting no one's reply",
          col(5) == "1")
    check("a failed lookup reads ? on every row", col(1, th=None) == "?")
    check("--no-threads leaves the column empty", col(1, want=False) == "")
    check("a response that is not a repository is a failed lookup",
          ps.thread_counts({}) is None and ps.thread_counts({"repository": None}) is None
          and ps.thread_counts({"repository": {"p1": None}}) is None)
    check("untruncated threads without a nodes list are a failed lookup",
          ps.thread_counts({"repository": {"p1": {"number": 1, "reviewThreads": {}}}}) is None)
    check("/unresolved keeps unknown rows and drops clean ones",
          ps.keeps_unresolved({"number": 4}, threads) and ps.keeps_unresolved({"number": 99}, threads)
          and ps.keeps_unresolved({"number": 1}, threads) and not ps.keeps_unresolved({"number": 3}, threads))

    # ── arguments ────────────────────────────────────────────────────
    check("a value option last is refused, not looped on", refused(["-n"]) == "pr-sessions: -n needs a value (try --help)."
          and "--session needs a value" in refused(["--session"]))
    check("a value option takes the next argument whatever it is", ps.parse(["-n", "--all"]).limit == "--all")
    check("conflicting states are named", refused(["/OPEN", "/MERGED"]) == "pr-sessions: /OPEN and /MERGED conflict — pick one state.")
    check("the same state in two spellings is fine", refused(["/OPEN", "--open"]) == "")
    check("different scopes are named with the session's value",
          refused(["--session", "a", "/all"]) == "pr-sessions: --session a and /all are different scopes — pick one.")
    check("the same scope twice is fine", refused(["/all", "--all"]) == "" and refused(["--session", "a", "--session", "a"]) == "")
    check("an unknown option points at --help", refused(["--nope"]) == "pr-sessions: unknown option '--nope' (try --help)")
    check("a pool flag passed empty is still set", ps.parse(["/lastItem:"]).last_item_set and ps.parse(["/lastDate:"]).last_date_set)
    check("a pool flag's value is what follows the first colon", ps.parse(["/lastDate:5:6"]).last_date == "5:6")
    with contextlib.redirect_stdout(io.StringIO()) as printed:
        helped = ps.parse(["-h", "--nope"]) is None
    check("--help wins over a later bad flag and loses to an earlier one",
          helped and printed.getvalue() == ps.HELP + "\n" and "unknown option" in refused(["--nope", "-h"]))
    check("the help is the bash's, with its closing exit-code table", ps.HELP.startswith("Which SESSION owns which PR, newest first.")
          and ps.HELP.endswith("2  invocation problem (no gh/jq, not authenticated, bad flag)"))

    # ── scope and pool ───────────────────────────────────────────────
    rows = [{"number": n, "headRefName": b, "updatedAt": u} for n, b, u in (
        (5, "h/agent/feat/a", "2026-09-30T10:00:00Z"), (4, "dependabot/x/y/z", "2026-09-30T09:00:00Z"),
        (3, "h/other/feat/b", "2026-09-30T08:00:00Z"), (2, "agent/foo", "2026-09-29T00:00:00Z"),
        (1, "renovate/a/b/c", "2026-09-01T00:00:00Z"))]
    nums = lambda sel: [r["number"] for r in sel[0]]  # noqa: E731
    mine = ps.Me("h/agent", "", "")
    check("default scope: mine only, the unowned counted", (nums(ps.select(rows, ps.MINE, mine, "", 0, 20)), ps.select(rows, ps.MINE, mine, "", 0, 20)[1]) == ([5], 2))
    check("/all drops and counts nothing", ps.select(rows, "", mine, "", 0, 20)[1] == 0 and nums(ps.select(rows, "", mine, "", 0, 20)) == [5, 4, 3, 2, 1])
    check("/unattributed lists them and counts none", (nums(ps.select(rows, ps.UNOWNED, mine, "", 0, 20)), ps.select(rows, ps.UNOWNED, mine, "", 0, 20)[1]) == ([2, 1], 0))
    check("the role's rows are the role holder's", nums(ps.select(rows, ps.MINE, ps.Me("h/agent", "", "devex-tooling"), "", 0, 20)) == [5, 4])
    check("--session is a case-insensitive search of the session", nums(ps.select(rows, "OTHER", mine, "", 0, 20)) == [3])
    check("the count describes the narrowed pool", ps.select(rows, ps.MINE, mine, "", 2, 20)[1] == 0)
    check("/lastItem narrows before scope", nums(ps.select(rows, "", mine, "", 2, 20)) == [5, 4])
    check("/lastDate narrows before scope", nums(ps.select(rows, "", mine, "2026-09-30T08:30:00Z", 0, 20)) == [5, 4])
    check("the candidate slice comes last", nums(ps.select(rows, "", mine, "", 0, 2)) == [5, 4])
    check("a bad pattern over rows is refused", "valid regex" in _die(lambda: ps.select(rows, "[", mine, "", 0, 20)))
    check("a bad pattern over an empty pool is no error, as in the bash", ps.select([], "[", mine, "", 0, 20) == ([], 0))

    # ── a whole run ──────────────────────────────────────────────────
    # #30 and #28 are this agent's (#28 under the working copy's older
    # prefix), #29 another session's; #30's one open thread was last
    # answered by a reviewer, #29's by its PR author, #28's are all resolved.
    base_rows = [pr(30, "h/agent/feat/alpha"), pr(29, "h/other/fix/beta", "MERGED", ago(hours=2)),
                 pr(28, "h/clonename/docs/gamma", "MERGED", ago(hours=3))]
    base_threads = gql({30: ("me", [thread(False, "rev")], False), 29: ("me", [thread(False, "me")], False),
                        28: ("me", [thread(True, "rev")], False)})
    rc, out, seen = drive([], base_rows, base_threads)
    check("the default scope lists this agent's PRs, the working copy's older ones too, and hides another session's",
          rc == 0 and "#30" in out and "#28" in out and "#29" not in out)
    check("the default scope marks its rows mine and says it defaulted",
          row(out, 30).startswith("*") and row(out, 28).startswith("*") and "Scoped to this session" in out)
    rc, out, seen = drive(["/all"], base_rows, base_threads)
    check("/all lists every session's PRs", rc == 0 and all(f"#{n}" in out for n in (28, 29, 30)))
    check("a whole run's THR column: a bang for a reply owed, none once the author answered, a dash for resolved",
          "1!" in row(out, 30) and "1!" not in row(out, 29) and " 1 " in row(out, 29) and " - " in row(out, 28))
    rc, out, seen = drive(["--session", "other"], base_rows, base_threads)
    check("--session names one session's PRs", rc == 0 and "#29" in out and "#30" not in out)
    check("the state is chosen at fetch time, all by default",
          drive(["/OPEN"], base_rows, base_threads)[2]["state"] == "open" and seen["state"] == "all")
    rc, out, seen = drive([], [], base_threads)
    check("no PRs is a clean exit that names the scope it defaulted to",
          rc == 0 and "no PRs for this session" in out and "scoped to this session by default" in out)

    # ── --no-threads and /unresolved ─────────────────────────────────
    rc, out, seen = drive(["/all", "--no-threads"], base_rows, base_threads)
    check("--no-threads asks nothing and shows no bang", rc == 0 and seen["looked_up"] is None and "1!" not in out)
    rc, out, seen = drive(["/unresolved", "--no-threads"], base_rows, base_threads)
    check("/unresolved without the lookup is refused", rc == 2 and "drop --no-threads" in out)
    rc, out, seen = drive(["/all", "/unresolved"], base_rows, base_threads)
    check("/unresolved keeps the PRs with open threads and drops the resolved-only one",
          rc == 0 and "#30" in out and "#29" in out and "#28" not in out)
    rc, out, seen = drive(["/all"], base_rows, None)
    check("a failed thread lookup lists on, every THR unknown", rc == 0 and "?" in row(out, 30) and "?" in row(out, 28))
    rc, out, seen = drive(["/all", "/unresolved"], base_rows, None)
    check("a failed thread lookup under /unresolved is refused, never answered none",
          rc == 2 and "could not" in out and "no PRs with unresolved review threads" not in out)
    check("no repository is the same failed lookup", drive(["/all", "/unresolved"], base_rows, base_threads, repo="")[0] == 2)
    check("the thread query holds the PR numbers as variables, one alias each",
          drive(["/all"], base_rows, base_threads)[2]["looked_up"] == [28, 29, 30])

    # Only the first 100 threads arrive: a PR whose open thread sits on page
    # two looks clean, which hides the outstanding work this command exists
    # to surface. #30 and #29 keep their counts, so the "?" is #28's alone.
    paged = gql({30: ("me", [thread(False, "rev")], False), 29: ("me", [thread(False, "me")], False),
                 28: ("me", [thread(True, "rev")], True)}, paged=True)
    rc, out, seen = drive(["/all"], base_rows, paged)
    check("a truncated thread page reads unknown through the query's own pageInfo, not zero",
          rc == 0 and "?" in row(out, 28) and "?" not in row(out, 30) and " - " not in row(out, 28))
    check("and /unresolved keeps it rather than dropping it", "#28" in drive(["/all", "/unresolved"], base_rows, paged)[1])

    # ── pool filters and limits ──────────────────────────────────────
    aged = [pr(30, "h/agent/feat/a"), pr(29, "h/agent/feat/b", at=ago(days=5)), pr(28, "h/agent/feat/c", at=ago(days=6))]
    out = drive(["/all", "/lastItem:1"], aged)[1]
    check("/lastItem:1 keeps the newest PR and drops everything older", "#30" in out and "#29" not in out)
    out = drive(["/all", "/lastDate:2d"], aged)[1]
    check("/lastDate keeps the PRs inside the window", "#30" in out and "#29" not in out and "#28" not in out)
    check("/lastDate accepts a window wide enough for all", "#28" in drive(["/all", "/lastDate:99d"], aged)[1])
    check("/lastItem beyond the derived cap is honoured, not clamped",
          drive(["/all", "/lastItem:600", "--no-threads"], aged)[2]["limit"] == 600)
    rc, out, seen = drive(["/all", "-n", "10", "/lastDate:99d", "--no-threads"], [pr(500 - i, "h/agent/feat/w") for i in range(200)])
    check("a full /lastDate page warns that the window may be short", rc == 0 and seen["limit"] == 200 and "may be" in out)
    # The 100-row candidate cap was once applied after /lastItem: the caller
    # named a number and silently got a different one. 150 rows, every
    # thread RESOLVED but the oldest's, #151.
    many = [pr(300 - i, "h/agent/feat/p", "MERGED") for i in range(150)]
    many_threads = gql({300 - i: ("me", [thread(300 - i != 151, "rev")], False) for i in range(150)}, paged=True)
    rc, out, seen = drive(["/all", "-n", "200", "/lastItem:150", "/unresolved"], many, many_threads)
    check("/unresolved honours an explicit /lastItem past the 100-row cap",
          rc == 0 and len(seen["looked_up"]) == 150 and "#151" in out and "#300" not in out)

    # ── malformed arguments, refused before any gh call ──────────────
    for argv, wants in ((["/lastItem:0"], "positive integer"), (["/lastItem:"], "positive integer"),
                        (["/lastDate:5"], "<N>d"), (["/lastDate:"], "<N>d"), (["-n", "abc"], "positive integer"),
                        # In bash arithmetic this was code execution: a subscript evaluates a command substitution.
                        (["-n", "x[$(touch /nonexistent/pwned)]"], "positive integer")):
        rc, out, seen = drive(argv, base_rows, base_threads)
        check(f"{' '.join(argv)} is refused, naming the expectation", rc == 2 and wants in out and seen["state"] is None)
    rc, out, seen = drive(["--session", "["], base_rows, base_threads)
    check("an invalid --session regex is an invocation error, not an empty result",
          rc == 2 and "session" in out and "no PRs for a session" not in out)
    rc, out, seen = drive(["/all"], [], base_threads, list_fails=True)
    check("a failed pr list is an invocation error", rc == 2 and "could not list PRs" in out)

    # ── bot rows and the role ────────────────────────────────────────
    bots = [pr(40, "dependabot/github_actions/actions-minor-patch-5c7bcdc794"),
            pr(41, "dependabot/nuget/apps/backend_dotnet/dotnet-minor-patch-04e2", at=ago(hours=2)),
            pr(42, "h/agent/feat/real", at=ago(hours=3)), pr(43, "renovate/npm/vite-6.x", at=ago(hours=4))]
    bot_threads = gql({40: ("app/dependabot", [], False), 41: ("app/dependabot", [thread(False, "reviewer[bot]")], False),
                       42: ("me", [], False), 43: ("app/renovate", [], False)})
    out = drive(["/all"], bots, bot_threads)[1]
    check("a Dependabot row's session is the devex-tooling role's", all(
        "role:devex-tooling" in row(out, n) and "(unconventional)" not in row(out, n) for n in (40, 41)))
    check("a bot with no owner in the map stays unattributed", "(unconventional)" in row(out, 43))
    out = drive([], bots, bot_threads, who=("h/agent", "", "devex-tooling"))[1]
    check("the devex-tooling holder's default scope lists the Dependabot rows, marked mine, not the unowned bot",
          "#40" in out and "#41" in out and row(out, 41).startswith("*") and "#43" not in out)
    out = drive(["/unresolved"], bots, bot_threads, who=("h/agent", "", "devex-tooling"))[1]
    check("and its /unresolved surfaces the Dependabot thread, not a resolved bot row", "#41" in out and "#40" not in out)
    out = drive([], bots, bot_threads, who=("h/agent", "", "backend-dev"))[1]
    check("another role sees neither, and the NOTE counts only the unowned bot",
          "#40" not in out and "#41" not in out and "1 PR(s) name no live session" in out)

    # ── attribution by shape ─────────────────────────────────────────
    # A <type> vocabulary once made spike-3/, hotfix/ and stage-4/ branches
    # unconventional, and the default scope then SILENTLY DROPPED them.
    typed = [{"number": n, "headRefName": f"h/agent/{t}/x", "updatedAt": "2026-09-30T10:00:00Z"} for n, t in ((3, "spike-3"), (2, "hotfix"), (1, "feat"))]
    kept, dropped = ps.select(typed, ps.MINE, ps.Me("h/agent", "", ""), "", 0, 20)
    check("an unlisted <type> is still this agent's work, and none reads as unattributed",
          [r["number"] for r in kept] == [3, 2, 1] and dropped == 0)

    # ── what a scope hides, disclosed ────────────────────────────────
    # Removing an unparsable row SILENTLY is how a listing looks complete
    # when it is not, so the count is stated on every path that exits.
    unscopable = [pr(60, "add-claude-github-actions-1785994932117", at=ago(hours=1)), pr(61, "h/agent/feat/real", at=ago(hours=2))]
    noted = gql({60: ("me", [], False), 61: ("me", [], False)})
    rc, out, seen = drive([], unscopable, noted)
    check("the footer path discloses the omission, counts it and names the flag that lists it",
          rc == 0 and "cannot be scoped to a" in out and "1 PR(s) name no live session" in out and "/unattributed" in out)
    check("/all reports nothing omitted, because nothing was scoped away",
          "cannot be scoped to a" not in drive(["/all"], unscopable, noted)[1])
    rc, out, seen = drive([], [pr(62, "add-claude-github-actions-1785994932117")], {"repository": {}})
    check("the disclosure survives the no-rows early exit",
          rc == 0 and "no PRs for this session" in out and "cannot be scoped to a" in out)
    rc, out, seen = drive(["/unresolved"], unscopable, noted)
    check("the disclosure survives the /unresolved-empty early exit",
          rc == 0 and "no PRs with unresolved" in out and "cannot be scoped to a" in out)
    for argv in (["/unattributed"], ["--session", "unconventional"]):
        rc, out, seen = drive(argv, unscopable, noted)
        check(f"{' '.join(argv)} lists exactly the rows no scope can reach, without contradicting itself",
              rc == 0 and "#60" in out and "#61" not in out and "cannot be scoped to a" not in out)
        check(f"{' '.join(argv)} claims no row as this agent's and says the findings are unowned",
              "* = " not in out and "no session" in out)
    check("/unattributed twice is one scope", drive(["/unattributed", "/unattributed"], unscopable, noted)[0] == 0)
    # The pool must exceed the 100-row candidate slice or the claim is not
    # falsifiable: 150 owned rows numbered above the one unowned row put it
    # at position 151, outside the slice unless the scope came first.
    pool = [pr(70, "agent/global-event-identity", "MERGED")] + [pr(200 + i, f"h/agent/feat/w{i}") for i in range(150)]
    rc, out, seen = drive(["/unattributed", "/unresolved"], pool,
                          gql({70: ("me", [thread(False, "rev[bot]"), thread(False, "rev[bot]")], False)}, paged=True))
    check("/unattributed narrows BEFORE the thread lookup, so the unowned row is queried with a real count",
          rc == 0 and seen["looked_up"] == [70] and "#70" in out and "2!" in out)
    rc, out, seen = drive(["/unattributed"], base_rows, base_threads)
    check("/unattributed with nothing to show names its own scope",
          rc == 0 and "without a parsable session branch" in out and "PRs for this session" not in out)
    rc, out, seen = drive(["/unattributed", "/unresolved"], [pr(72, "agent/common-api-idempotency", "MERGED")],
                          gql({72: ("me", [thread(True, "rev[bot]")], False)}, paged=True))
    check("/unattributed /unresolved with nothing to show names the unowned scope, not the session's",
          rc == 0 and "branches no session owns" in out and "for this session" not in out)
    check("the count describes the NARROWED pool: a PR outside /lastItem is not announced",
          "cannot be scoped to a" not in drive(["/lastItem:1"], unscopable, noted)[1])

    # ── whose working copy this is ───────────────────────────────────
    # who_am_i with a fixed identity: hostname h, login agent1, role held.
    def asks(cmd):
        return (0, "h\n") if cmd[0] == "hostname" else (0, "devex-tooling\n") if cmd[-1] == "--role" else (0, "agent1\n")
    saved = (pso._sh, pso.local.toplevel, pso.local.remote_url)
    try:
        pso._sh, pso.local.toplevel = asks, lambda: "/w/legacy-testclone"
        pso.local.remote_url = lambda root: ""
        own_name = pso.who_am_i()
        pso.local.remote_url = lambda root: "git@example.com:org/legacy-testclone.git"
        repo_name = pso.who_am_i()
        # The faked remotes above decide; this one is read from a real clone's origin.
        with tempfile.TemporaryDirectory() as tmp:
            clone = os.path.join(tmp, "legacy-testclone")
            subprocess.run(["git", "init", "-q", clone], check=True)
            subprocess.run(["git", "-C", clone, "remote", "add", "origin",
                            "git@example.com:org/legacy-testclone.git"], check=True)
            pso.local.toplevel, pso.local.remote_url = (lambda: clone), saved[2]
            read_origin = pso.who_am_i()
        pso.local.toplevel = lambda: None
        outside = pso.who_am_i()
    finally:
        pso._sh, pso.local.toplevel, pso.local.remote_url = saved
    check("a working copy with a name of its own leaves its older prefix to this agent, and the role is the binding's",
          own_name == ("h/agent1", "h/legacy-testclone", "devex-tooling"))
    check("a clone named after its repository is every login's: no session's name, no older prefix",
          repo_name == ("h/agent1", "", "devex-tooling"))
    check("…and the remote is read from the clone's own origin", read_origin == ("h/agent1", "", "devex-tooling"))
    check("outside a clone there is no identity", outside == ("", "", ""))
    older = [{"number": 7, "headRefName": "h/legacy-old/fix/theirs", "updatedAt": "2026-09-30T10:00:00Z"}]
    check("another working copy's older branch is its session's: not mine, not unattributed, listed under /all",
          nums(ps.select(older, ps.MINE, mine, "", 0, 20)) == [] and nums(ps.select(older, ps.UNOWNED, mine, "", 0, 20)) == []
          and nums(ps.select(older, "", mine, "", 0, 20)) == [7])

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


def _die(fn) -> str:
    try:
        fn()
    except ps.Die as e:
        return str(e)
    return ""


if __name__ == "__main__":
    sys.exit(main())
