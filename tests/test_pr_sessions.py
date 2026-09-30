#!/usr/bin/env python3
"""Tests for tools/fabric/github/pr_sessions.py's internals; the behaviour is
runtime/github/test_pr-sessions.sh's, run unchanged against the shim
(ADR-040 §5 rule 5). What the fixtures there reach only through a whole run
is checked here directly: who owns a branch, the /lastDate span, the THR
column's "!" rule, the unknown-is-not-zero reading of a thread page."""
from __future__ import annotations

import contextlib
import io
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from github import pr_reply, pr_sessions as ps  # noqa: E402


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
