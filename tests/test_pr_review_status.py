#!/usr/bin/env python3
"""Tests for tools/fabric/github/pr_review_status.py: its internals, and the
verdict of a whole run, which here is computed in-process against a scripted
`gh` (ADR-040 §5 rule 5). tests/test_pr_review_status_cli.py drives the shim as a
process and keeps one case per outcome (exit status, stream, output mode); every
reason a run ends in 0, 1, 5 or 2 is asserted here, at 0.1 s a suite. Checked
directly: the duration table and its octal reading, the regex dialect bridge,
what counts as coverage, the ordering of a decline against a request, the wait
loop against a fake clock, and the shapes the report prints."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import time
from types import SimpleNamespace

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import gh  # noqa: E402
from github import pr_review_status as rs  # noqa: E402

HEAD = "abc123def4567890"


def review(login, commit=HEAD, at="2026-08-07T10:00:00Z", body="", assoc="MEMBER", state="COMMENTED"):
    return {"user": {"login": login}, "author_association": assoc, "state": state,
            "commit_id": commit, "submitted_at": at, "body": body}


def comment(login, body, at="2026-08-25T10:00:00Z"):
    return {"user": {"login": login}, "created_at": at, "body": body}


def cfg(**kw):
    env = {"AGENT_FABRIC_VERDICT_AUTHORS": '["reviewer[bot]"]',
           "AGENT_FABRIC_REVIEWER_REFUSAL_RE": "usage limit reached",
           "AGENT_FABRIC_REVIEW_REQUEST_RE": "@reviewer[[:space:]]+review"}
    env.update(kw)
    return rs.read_config(env)


REF = "mine/branch"
# gh's other answers to `gh pr checks`, as measured on 2.87.3: a 502 has no
# table, "no checks reported" is a real zero.
CHECKS_TABLE = "some / Check\tpass\t1s\n"
CHECKS_502 = gh.GhError("gh pr checks 77", "HTTP 502", 502, True, "", "HTTP 502: Bad Gateway (https://api.github.com/graphql)\n", 1)
CHECKS_NONE = gh.GhError("gh pr checks 77", "x", None, False, "", f"no checks reported on the '{REF}' branch\n", 1)


def verdict(sha, login="reviewer[bot]", at="2026-08-25T10:00:00Z"):
    return comment(login, f"### Review\n\n**Reviewed commit:** `{sha}`\n", at)


def ask(at, login="someone"):
    return comment(login, "@reviewer review\n\nplease look again", at)


def decline(at="2026-08-25T10:00:00Z", login="reviewer[bot]", body="Usage limit reached for reviews; none will run."):
    return comment(login, body, at)


def suite(at, ref=REF, prs=(77,)):
    return {"created_at": at, "head_branch": ref, "pull_requests": [{"number": n} for n in prs]}


@contextlib.contextmanager
def scripted_gh(polls=(("OPEN", "abc123", 0),), reviews=(), comments=(), threads=(), threads_fail=False,
                checks=CHECKS_TABLE, reviews_fail=False, reviews_fail_after=None, comments_fail=False,
                formal=(), suites=None, page2=(), head_date="2026-08-10T00:00:00Z", head_ref=REF):
    """gh as one run of the command sees it, in place of gh.py's calls.

    polls     one per `gh pr view`, the last repeating: (state, head, requests)
              with requests a count of the configured reviewer or a list of
              logins, or the word FAIL for a call gh fails.
    formal    (date, login) per REVIEW_REQUESTED_EVENT on the timeline.
    suites    the check suites of the head, default this PR's own, born at
              head_date; page2 is served only to a caller that paginates,
              which is how the earliest suite across pages stays pinned.
    The clock is fake: sleep advances time.time() and is recorded, so a wait
    of an hour costs nothing and the naps can be asserted."""
    seen = SimpleNamespace(polls=0, naps=[])
    clock = [1_000_000.0]
    own = [suite(head_date, ref=head_ref)] if suites is None else list(suites)

    def pr_view(number, fields, *, repo=None, timeout=0):
        poll = polls[min(seen.polls, len(polls) - 1)]
        seen.polls += 1
        if poll == "FAIL":
            raise gh.GhError(f"gh pr view {number}", "exit 1")
        state, head, requests = poll
        who = ["reviewer[bot]"] * requests if isinstance(requests, int) else requests
        return {"state": state, "mergeStateStatus": "CLEAN", "headRefOid": head, "headRefName": head_ref,
                "author": {"login": "me"}, "isDraft": False,
                "reviewRequests": [{"__typename": "User", "login": w} for w in who]}

    def api(path, *, method="GET", body=None, paginate=False, timeout=0, items_key=None):
        if "/reviews" in path:
            # polls counts this probe's own `pr view`, so it IS the poll number.
            if reviews_fail or (reviews_fail_after is not None and seen.polls > reviews_fail_after):
                raise gh.GhError(f"gh api GET {path}", "exit 1")
            return list(reviews)
        if "/check-suites" in path:
            return own + (list(page2) if paginate else [])
        if "/commits/" in path:
            return {"commit": {"committer": {"date": head_date}}}
        if "/comments" in path:
            if comments_fail:
                raise gh.GhError(f"gh api GET {path}", "exit 1")
            return list(comments)
        raise AssertionError(path)

    def graphql(query, *, timeout=0, **variables):
        if "REVIEW_REQUESTED_EVENT" in query:
            nodes = [{"createdAt": d, "requestedReviewer": {"login": who}} for d, who in formal]
            return {"repository": {"pullRequest": {"timelineItems": {"nodes": nodes}}}}
        if "reviewThreads" in query:
            if threads_fail:
                raise gh.GhError("gh api graphql", "exit 1")
            return {"repository": {"pullRequest": {"reviewThreads": {"nodes": list(threads), "pageInfo": {}}}}}
        raise AssertionError(query)

    def run(args, *, input=None, timeout=0, what=None):
        assert args[:2] == ["pr", "checks"], args
        if isinstance(checks, gh.GhError):
            raise checks
        return checks

    def sleep(n):
        seen.naps.append(n)
        clock[0] += n

    real = (gh.pr_view, gh.api, gh.graphql, gh.run, shutil.which, time.time, time.sleep)
    gh.pr_view, gh.api, gh.graphql, gh.run = pr_view, api, graphql, run
    shutil.which, time.time, time.sleep = (lambda name: "/bin/gh"), (lambda: clock[0]), sleep
    try:
        yield seen
    finally:
        gh.pr_view, gh.api, gh.graphql, gh.run, shutil.which, time.time, time.sleep = real


def go(*argv, env=None, **world):
    """One run of the command for PR 77 of o/r, as main() makes it: the exit
    status, stdout, stderr (a refusal prefixed as main() prefixes it), both
    together as .all, and what the scripted gh saw. The environment is the
    one the CLI suite configured: an automated reviewer, its two phrases."""
    e = {"AGENT_FABRIC_VERDICT_AUTHORS": '["reviewer[bot]"]',
         "AGENT_FABRIC_REVIEWER_REFUSAL_RE": "usage limit reached|no environment for this repo",
         "AGENT_FABRIC_REVIEW_REQUEST_RE": "@reviewer[[:space:]]+review", **(env or {})}
    out, err = io.StringIO(), io.StringIO()
    with scripted_gh(**world) as seen, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = rs.run(["77", "o/r", *argv], e)
        except rs.Die as d:
            rc = d.code
            print(f"{rs.PROG}: {d}", file=sys.stderr)
    return SimpleNamespace(rc=rc, out=out.getvalue(), err=err.getvalue(), all=out.getvalue() + err.getvalue(),
                           polls=seen.polls, naps=seen.naps)


def rev(login, commit="abc123", **kw):
    return review(login, commit=commit, **kw)


def says(r, *lines):
    return all(l in r.all for l in lines)


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    def die(fn) -> str:
        try:
            fn()
        except rs.Die as e:
            return f"{e.code}:{e}"
        return ""

    # ── durations ────────────────────────────────────────────────────
    check("a bare number is seconds, unchanged", rs.as_seconds("--wait", "90") == "90")
    check("s, m and h", (rs.as_seconds("--wait", "90s"), rs.as_seconds("--wait", "10m"), rs.as_seconds("--wait", "2h")) == ("90", "600", "7200"))
    check("a second unit is refused", "needs a duration like 90" in die(lambda: rs.as_seconds("--wait", "1mm")))
    check("a unit alone, an empty value and a word are refused",
          all(die(lambda v=v: rs.as_seconds("--wait", v)) for v in ("m", "", "x", "-5", "1.5")))
    check("the refusal quotes the raw value", die(lambda: rs.as_seconds("--interval", "10x")) == "2:--interval needs a duration like 90, 90s, 10m or 2h, got '10x'.")
    check("a leading zero is octal, as in the bash's $(( ))", rs.bash_int("010") == 8 and rs.as_seconds("--wait", "0010m") == "480")
    check("an 8 or 9 in one is bash's arithmetic error", die(lambda: rs.as_seconds("--wait", "08m")).startswith("2:08: value too great"))
    check("a bare leading-zero interval is refused, the string being kept",
          die(lambda: rs.parse(["--interval", "010"])) == "2:--interval must be greater than zero, got '010'.")
    check("an interval of 10m is 600", rs.parse(["--interval", "10m"]).interval == "600")

    # ── argv ─────────────────────────────────────────────────────────
    a = rs.parse(["77", "o/r", "-q", "--json", "--wait", "5"])
    check("positionals, flags and a value option", (a.pr, a.repo, a.quiet, a.json, a.wait) == ("77", "o/r", True, True, "5"))
    check("an empty word is skipped: the next positional takes its place", (rs.parse(["", "77"]).pr, rs.parse(["", "77"]).repo) == ("77", ""))
    check("a third positional is refused", die(lambda: rs.parse(["1", "o/r", "x"])) == "2:unexpected argument 'x' (try --help)")
    check("an unknown option is refused", die(lambda: rs.parse(["--nope"])) == "2:unknown option '--nope' (try --help)")
    check("a value option takes the next word whatever it is", die(lambda: rs.parse(["--wait", "--json"])).startswith("2:--wait needs a duration"))
    check("a value option at the end needs a value", die(lambda: rs.parse(["--wait"])) == "2:--wait needs a value (try --help).")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        helped = rs.parse(["--help", "--bogus"])
    check("--help prints at once, so a later bad argument is never read", helped is None and buf.getvalue() == rs.HELP + "\n")
    check("a bad argument before --help wins", die(lambda: rs.parse(["--bogus", "--help"])).startswith("2:unknown option"))

    # ── configuration ────────────────────────────────────────────────
    check("an unset list is empty", rs.read_config({}).verdict_authors == [] and rs.read_config({}).review_posters == [])
    check("an EMPTY list variable is its default too", rs.read_config({"AGENT_FABRIC_VERDICT_AUTHORS": ""}).verdict_authors == [])
    check("a list that is not JSON is refused, naming the variable",
          die(lambda: rs.read_config({"AGENT_FABRIC_VERDICT_AUTHORS": "a,b"})) == "2:AGENT_FABRIC_VERDICT_AUTHORS must be a JSON array of logins, got 'a,b'.")
    check("a list of non-strings is refused", die(lambda: rs.read_config({"AGENT_FABRIC_REVIEW_POSTERS": "[1]"})).startswith("2:AGENT_FABRIC_REVIEW_POSTERS must be"))
    check("an object is not a list", die(lambda: rs.read_config({"AGENT_FABRIC_REVIEW_POSTERS": "{}"})).startswith("2:"))
    check("a regex the engine refuses is exit 2, named",
          die(lambda: rs.read_config({"AGENT_FABRIC_REVIEW_REQUEST_RE": "ask("})) == "2:AGENT_FABRIC_REVIEW_REQUEST_RE is not a regex jq accepts: 'ask('.")
    check("the list is checked before the patterns",
          die(lambda: rs.read_config({"AGENT_FABRIC_VERDICT_AUTHORS": "x", "AGENT_FABRIC_REVIEW_REQUEST_RE": "("})).startswith("2:AGENT_FABRIC_VERDICT"))
    check("the built-in markers, then the project's, blank lines dropped",
          cfg(AGENT_FABRIC_LEGACY_REVIEW_MARKERS="<!-- mine -->\n\n<!-- x -->").markers
          == [rs.REVIEW_MARKER, rs.BUILTIN_LEGACY_MARKER, "<!-- mine -->", "<!-- x -->"])

    # ── jq's regex dialect, as Python's ──────────────────────────────
    check("a POSIX class inside brackets", rs.compile_re("@reviewer[[:space:]]+review").search("@Reviewer \n review") is not None)
    check("a negated POSIX class", rs.compile_re("a[^[:digit:]]b").search("axb") is not None and rs.compile_re("a[^[:digit:]]b").search("a1b") is None)
    check("a named group, both spellings", rs.compile_re("(?<n>ask)").search("ASK") is not None)
    check("a look-behind is not a named group", rs.compile_re("(?<=a)b").search("ab") is not None)
    check("a bracket holding ] first is one set", rs.compile_re("[]x]+").search("]x") is not None)
    check("an escaped bracket is no set", rs.compile_re(r"\[:space:\]").search("[:space:]") is not None)
    check("the match is case-insensitive, as jq's \"i\"", rs.compile_re("usage limit").search("USAGE LIMIT") is not None)
    check("an unterminated set is an error", die(lambda: rs.read_config({"AGENT_FABRIC_REVIEWER_REFUSAL_RE": "[unclosed"})) != "")

    # ── what counts ──────────────────────────────────────────────────
    c = cfg()
    marked = rs.REVIEW_MARKER + "\nfindings"
    b = rs.classify([review("someone"), review("me", body=marked), review("me"), review("rando", assoc="NONE"),
                     review("rando", body=marked), review("reviewer[bot]", assoc="NONE")], "me", c)
    check("a member's review is independent; a configured reviewer's too, whatever its association",
          [rs.login_of(r) for r in b.independent] == ["someone", "reviewer[bot]"])
    check("a stranger's unmarked review is not trusted", [rs.login_of(r) for r in b.outsiders] == ["rando"])
    check("the author's marked review is blind, another login's is reported and not coverage",
          [rs.login_of(r) for r in b.blind] == ["me"] and [rs.login_of(r) for r in b.marked_others] == ["rando"])
    check("the author's unmarked review is a self review", len(b.self_) == 1)
    check("qualifying is independent then blind", [rs.login_of(r) for r in b.qualifying] == ["someone", "reviewer[bot]", "me"])
    check("a named poster's marked review is blind",
          len(rs.classify([review("ci", body=marked)], "me", cfg(AGENT_FABRIC_REVIEW_POSTERS='["ci"]')).blind) == 1)
    check("the marker must LEAD the body: a quotation is an ordinary review",
          len(rs.classify([review("me", body="see " + rs.REVIEW_MARKER)], "me", c).self_) == 1)
    check("the built-in earlier marker counts", len(rs.classify([review("me", body=rs.BUILTIN_LEGACY_MARKER + "\nx")], "me", c).blind) == 1)
    check("a null body is an empty one", rs.classify([{"user": {"login": "me"}, "body": None}], "me", c).self_ != [])
    check("a review from a deleted account has no login and is nobody's",
          rs.classify([{"user": None, "author_association": "NONE", "body": ""}], "me", c).outsiders != [])

    # ── verdict comments, refusals, requests ─────────────────────────
    v = rs.verdicts_of([comment("reviewer[bot]", "**Reviewed commit:** `abc1234`"), comment("rando", "Reviewed commit: `abc1234`"),
                        comment("me", "Reviewed commit: `abc1234`"), comment("reviewer[bot]", "nothing here")], "me", c)
    check("only a configured reviewer's comment naming a sha is a verdict", [(x["login"], x["sha"]) for x in v] == [("reviewer[bot]", "abc1234")])
    check("a sha shorter than 7 is no verdict", rs.verdicts_of([comment("reviewer[bot]", "Reviewed commit: `abc12`")], "me", c) == [])
    check("the PR author is never a verdict author", rs.verdicts_of([comment("me", "Reviewed commit: `abc1234`")], "me", cfg(AGENT_FABRIC_VERDICT_AUTHORS='["me"]')) == [])
    check("a comment of the wrong shape reads as no verdicts", rs.verdicts_of([None], "me", c) == [])
    check("a verdict sha matches the head either way round",
          rs.head_covered(HEAD, [{"sha": "abc123d"}], []) and rs.head_covered("abc123d", [{"sha": HEAD}], [])
          and not rs.head_covered(HEAD, [{"sha": "fffffff"}], []))
    check("ANY qualifying review of the head covers it, not the newest",
          rs.head_covered(HEAD, [], [review("a", commit=HEAD, at="2026-08-01T00:00:00Z"), review("b", commit="old", at="2026-08-09T00:00:00Z")]))
    check("a review of an earlier commit does not", not rs.head_covered(HEAD, [], [review("a", commit="old")]))

    at, reason = rs.refusal_of([comment("reviewer[bot]", "\r\nUsage limit reached for reviews.\r\nlater line", "2026-08-20T10:00:00Z"),
                                comment("rando", "usage limit reached", "2026-08-30T10:00:00Z")], c)
    check("a refusal is the reviewer's own, newest, with its first non-empty line", (at, reason) == ("2026-08-20T10:00:00Z", "Usage limit reached for reviews."))
    check("a reason is cut to 160", len(rs.refusal_of([comment("reviewer[bot]", "usage limit reached " + "x" * 300)], c)[1]) == 160)
    check("no pattern, no refusal", rs.refusal_of([comment("reviewer[bot]", "usage limit reached")], cfg(AGENT_FABRIC_REVIEWER_REFUSAL_RE="")) == ("", ""))
    check("a request is anybody's, the newest",
          rs.request_of([comment("x", "@reviewer review", "2026-08-01T00:00:00Z"), comment("y", "@reviewer  review", "2026-08-02T00:00:00Z")], c) == "2026-08-02T00:00:00Z")
    check("no pattern, no request", rs.request_of([comment("x", "@reviewer review")], cfg(AGENT_FABRIC_REVIEW_REQUEST_RE="")) == "")
    check("a null timestamp sorts first and never wins", rs.newest([None, "2026-01-01"]) == "2026-01-01" and rs.newest([None]) == "" and rs.newest([]) == "")

    p = rs.Probe(head=HEAD, buckets=rs.Buckets(independent=[review("a", commit="old")]))
    check("a review of an earlier commit, none requested, nothing pending: nothing is coming", rs.no_review_coming(p))
    p.requested = 1
    check("a pending request means one is coming", not rs.no_review_coming(p))
    p.requested, p.request_pending = 0, True
    check("an asked phrase in flight means one is coming", not rs.no_review_coming(p))
    check("a fresh PR is not 'nothing is coming'", not rs.no_review_coming(rs.Probe(head=HEAD)))
    check("a covered head is not 'nothing is coming'", not rs.no_review_coming(rs.Probe(head=HEAD, head_reviewed=True, buckets=rs.Buckets(independent=[review("a")]))))
    check("a verdict is evidence the PR is one the reviewer answers", rs.no_review_coming(rs.Probe(head=HEAD, verdicts=[{"sha": "old"}])))

    # ── what the report prints ───────────────────────────────────────
    check("jq's null is the word null", rs.jstr(None) == "null" and rs.jstr("x") == "x" and rs.jstr(True) == "true")
    check("8 characters of a sha, null staying null", rs.sha8(HEAD) == "abc123de" and rs.sha8(None) is None)
    pb = rs.Probe(head=HEAD, head_reviewed=True, buckets=rs.Buckets(blind=[review("me")]))
    check("the head line names the blind review", "blind review of abc123de" in rs.head_evidence(pb))
    pi = rs.Probe(head=HEAD, head_reviewed=True, buckets=rs.Buckets(independent=[review("someone")]))
    check("...or the independent one", rs.head_evidence(pi).startswith(" — an independent review (someone, abc123de"))
    check("...or says a verdict comment", rs.head_evidence(rs.Probe(head=HEAD, head_reviewed=True)) == " — a verdict comment on this head")
    check("an unreviewed head names nothing", rs.head_evidence(rs.Probe(head=HEAD)) == "")

    ctx = rs.Ctx("77", "o/r", c, rs.Args())
    x = rs.Extras([{"path": "a.sh", "isOutdated": True}], 1, 2, 1)
    doc = json.loads(rs.render_json(ctx, rs.Probe(head=HEAD, state="OPEN", mergest="CLEAN", buckets=rs.Buckets(blind=[review("me")])), x, "head-moved", ""))
    check("the --json keys are the contract, in order",
          list(doc) == ["pr", "state", "merge_state", "head", "head_reviewed", "independent", "blind", "not_trusted",
                        "no_review_coming", "marked_by_others", "verdicts", "self", "unresolved_threads", "unresolved_paths", "checks"])
    check("pr is a number, a cause carries a null reason", doc["pr"] == 77 and doc["no_review_coming"] == {"cause": "head-moved", "reason": None})
    check("rows carry the 8-character sha", doc["blind"]["rows"] == [{"login": "me", "commit_sha8": "abc123de", "at": "2026-08-07T10:00:00Z", "engine": "claude"}])
    marker = "<!-- agent-fabric-review v1 -->"
    check("a review posted with --model codex is the codex engine, any other the review class's",
          [rs.engine_of({"body": b}) for b in (f"{marker}\n<!-- model: codex -->\nx", f"{marker}\n<!-- model: fable -->\nx", f"{marker}\nx",
                                              f"{marker}\nx\n<!-- model: codex -->")] == ["codex", "claude", "claude", "claude"])
    unknown = json.loads(rs.render_json(ctx, rs.Probe(head=HEAD), rs.Extras([], None, 0, 0), "", ""))
    check("unknown threads are null, never 0", unknown["unresolved_threads"] is None and unknown["no_review_coming"] is None)
    check("the text is not --json's", "\n  " in rs.render_json(ctx, rs.Probe(head=HEAD), x, "", "") and "ü" in rs.render_json(ctx, rs.Probe(head=HEAD, state="ü"), x, "", ""))

    # ── gh: a failing `gh pr checks` still carries its table ─────────
    e = gh.GhError("gh pr checks 1", "exit 8", 8, False, "a\tpass\n")
    check("the exit-8 table survives the error", e.stdout == "a\tpass\n")
    check("the pass count reads \\spass\\s per line", [bool(rs.PASS_LINE.search(l)) for l in ("a / b\tpass\t1s", "a / b\tfail\t1s", "password")] == [True, False, False])

    # ── fetch_extras: a checks lookup that printed no table is unknown ──
    # Each answer is gh's as measured on 2.87.3 (2026-10-09); only the
    # "no checks reported" one, and a table, are counts.
    table = "a / b\tpass\t1s\thttps://x\nc / d\tfail\t2s\thttps://y\n"
    answers = [
        ("exit 0, a table", table, None, (1, 1)),
        ("exit 1 with its table (a failing check)", table, gh.GhError("gh pr checks 77", "exit 1", None, False, table, "", 1), (1, 1)),
        ("exit 8 with its table (a pending check)", table, gh.GhError("gh pr checks 77", "exit 8", None, False, table, "", 8), (1, 1)),
        ("gh's 'no checks reported' is zero", "",
         gh.GhError("gh pr checks 77", "x", None, False, "", "no checks reported on the 'mine/branch' branch\n", 1), (0, 0)),
        ("an HTTP 502 is unknown", "",
         gh.GhError("gh pr checks 77", "HTTP 502", 502, True, "", "HTTP 502: Bad Gateway (https://api.github.com/graphql)\n", 1), (None, None)),
        ("a timeout is unknown", "", gh.GhError("gh pr checks 77", "no answer within 60 s", transient=True), (None, None)),
        ("exit 1, no table, another line, is unknown", "",
         gh.GhError("gh pr checks 77", "x", None, False, "", "could not find pull request\n", 1), (None, None)),
        ("exit 8 with no table is unknown", "", gh.GhError("gh pr checks 77", "exit 8", None, False, "", "", 8), (None, None)),
        ("gh not installed is unknown", "", gh.GhError("gh pr checks 77", "gh is not installed"), (None, None)),
        ("a table on another exit code is unknown", "", gh.GhError("gh pr checks 77", "exit 2", None, False, table, "", 2), (None, None)),
        ("exit 1 with only a blank line is unknown", "", gh.GhError("gh pr checks 77", "exit 1", None, False, "\n", "", 1), (None, None)),
    ]
    real_run, real_graphql = gh.run, gh.graphql
    try:
        gh.graphql = lambda *a, **k: {"repository": {"pullRequest": {"reviewThreads": {"nodes": [], "pageInfo": {}}}}}
        for label, stdout, raised, want in answers:
            def fake_run(args, *, input=None, timeout=gh.TIMEOUT_S, what=None, stdout=stdout, raised=raised):
                assert args[:2] == ["pr", "checks"], args
                if raised is not None:
                    raise raised
                return stdout
            gh.run = fake_run
            x = rs.fetch_extras(ctx)
            check(f"checks: {label} (got {x.checks_pass!r}, {x.checks_other!r})", (x.checks_pass, x.checks_other) == want and x.unresolved == 0)
    finally:
        gh.run, gh.graphql = real_run, real_graphql
    nochecks = rs.Extras([], 0, None, None)
    doc = json.loads(rs.render_json(ctx, rs.Probe(head=HEAD), nochecks, "", ""))
    check("unknown checks are null in --json, never 0", doc["checks"] == {"pass": None, "other": None})
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rs.render_text(ctx, rs.Probe(head=HEAD), nochecks)
    check("unknown checks read 'unknown' in the report", "  checks              : unknown\n" in buf.getvalue())
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rs.render_text(ctx, rs.Probe(head=HEAD), rs.Extras([], 0, 0, 0))
    check("...and a real zero reads as one", "  checks              : 0 pass, 0 other\n" in buf.getvalue())

    # ── the verdict of a whole run, against a scripted gh ────────────
    # Every reason a run ends in 0, 1, 5 or 2. The polls, reviews and comments
    # are the ones tests/test_pr_review_status_cli.py once fed a mocked gh on
    # PATH; its remaining cases are the outcomes only a process has.
    T = "2026-08-07T10:00:00Z"
    blind_body = marked + "…"
    r = go(reviews=[rev("bot", at=T)])
    check("independent review AT the head exits 0, says so and names the review",
          r.rc == 0 and says(r, "head reviewed?      : yes", "yes — an independent review (bot, abc123, 2026-08-07T10:00:00Z)"))
    check("no reviews at all exits 1", go().rc == 1)
    # The PR #363 case: three self-replies are REVIEW objects authored by the PR author.
    r = go(reviews=[rev("me", at=f"2026-08-07T10:0{i}:00Z") for i in range(3)])
    check("self-authored reviews are NOT coverage, counted as self and not as independent",
          r.rc == 1 and says(r, "self reviews        : 3", "independent reviews : 0"))
    r = go(reviews=[rev("me", at=T, body=blind_body)])
    check("a blind review at the head IS coverage, counted as blind and not as self, and says what it is",
          r.rc == 0 and says(r, "blind reviews       : 1", "self reviews        : 0", "the review class — coverage"))
    check("the head line names its evidence, trimmed or not",
          says(r, "head reviewed?      : yes — the review class's blind review of abc123, 2026-08-07T10:00:00Z"))
    r = go(reviews=[rev("me", at=T, body=rs.BUILTIN_LEGACY_MARKER + "\nfindings…")])
    check("the fabric's earlier marker still counts, unconfigured, as a blind review", r.rc == 0 and says(r, "blind reviews       : 1"))
    r = go(reviews=[rev("me", at=T, body="I think the marker " + rs.REVIEW_MARKER + " should move.")])
    check("a review that only QUOTES the marker is not coverage, not blind, still a self review",
          r.rc == 1 and says(r, "blind reviews       : 0", "self reviews        : 1"))
    legacy = {"AGENT_FABRIC_LEGACY_REVIEW_MARKERS": "<!-- legacy-project-review v1 -->"}
    legacy_review = rev("me", at=T, body="<!-- legacy-project-review v1 -->\nfindings…")
    r = go(reviews=[legacy_review], env=legacy)
    check("a legacy marker the forwarder names IS coverage, counted as blind", r.rc == 0 and says(r, "blind reviews       : 1"))
    r = go(reviews=[legacy_review])
    check("the same marker, not named by the environment: not coverage, a self review", r.rc == 1 and says(r, "self reviews        : 1"))
    check("a marker nobody named is not coverage even with a legacy one set",
          go(reviews=[rev("me", at=T, body="<!-- somebody-else-review v1 -->\nfindings…")], env=legacy).rc == 1)
    r = go(reviews=[rev("somebodyelse", at=T, body=blind_body)])
    check("a marked review from another account is NOT coverage, neither blind nor independent, reported with its login",
          r.rc == 1 and says(r, "blind reviews       : 0", "independent reviews : 0", "marked, other login : 1", "- somebodyelse  commit=abc123"))
    r = go(reviews=[rev("somebodyelse", at=T, body=blind_body)], env={"AGENT_FABRIC_REVIEW_POSTERS": '["somebodyelse"]'})
    check("a poster named in AGENT_FABRIC_REVIEW_POSTERS IS coverage, as a blind review, login shown",
          r.rc == 0 and says(r, "blind reviews       : 1", "- somebodyelse  commit=abc123"))
    check("the author's own marked review is blind, login shown", says(go(reviews=[rev("me", at=T, body=blind_body)]), "- me  commit=abc123"))
    r = go(reviews=[rev("stranger", at=T, assoc="NONE")])
    check("a stranger's review is NOT coverage, not independent, listed as not trusted with its association",
          r.rc == 1 and says(r, "independent reviews : 0", "- stranger  NONE  commit=abc123"))
    check("a collaborator's review IS coverage", go(reviews=[rev("helper", at=T, assoc="COLLABORATOR")]).rc == 0)
    check("a configured reviewer's review IS coverage whatever its association",
          go(reviews=[rev("reviewer[bot]", at=T, assoc="NONE")]).rc == 0)
    # A FAILED THREADS LOOKUP IS "unknown", never 0.
    r = go(reviews=[rev("me", at=T, body=blind_body)], threads_fail=True)
    check("a failed threads lookup reads unknown", says(r, "unresolved threads  : unknown"))
    r = go(reviews=[rev("me", at=T, body=blind_body)], threads=[{"isResolved": False, "isOutdated": False, "path": "a.sh"}])
    check("a real unresolved thread is counted", says(r, "unresolved threads  : 1"))
    r = go(reviews=[rev("me", at=T, body=blind_body)], checks=CHECKS_502)
    check("a failed checks lookup reads unknown and leaves the exit alone", r.rc == 0 and says(r, "  checks              : unknown\n"))
    r = go(reviews=[rev("me", at=T, body=blind_body)], checks=CHECKS_NONE)
    check("gh's 'no checks reported' reads 0 through a whole run", r.rc == 0 and says(r, "  checks              : 0 pass, 0 other\n"))
    # THE --json CONTRACT: the same answer as fields, the same exit code.
    r = go("--json", reviews=[rev("me", at=T, body=blind_body), rev("somebodyelse", at="2026-08-07T10:01:00Z", body=blind_body)],
           threads_fail=True)
    d = json.loads(r.out)
    check("--json keeps the exit code, carries the buckets, the login, and null for an unknown thread count",
          r.rc == 0 and d["head_reviewed"] == "yes" and d["blind"]["count"] == 1 and d["blind"]["rows"][0]["login"] == "me"
          and d["blind"]["rows"][0]["commit_sha8"] == "abc123" and d["marked_by_others"]["count"] == 1
          and d["unresolved_threads"] is None and d["independent"]["count"] == 0
          and isinstance(d["checks"]["pass"], int) and not isinstance(d["checks"]["pass"], bool))
    d = json.loads(go("--json", "-q", reviews=[rev("me", at=T, body=blind_body)], threads=[]).out)
    check("--json: a successful lookup with none is 0, not null", d["unresolved_threads"] == 0 and d["unresolved_threads"] is not False)
    r = go(reviews=[rev("me", at=T, body=blind_body), rev("me", at="2026-08-07T10:01:00Z"), rev("me", at="2026-08-07T10:02:00Z")])
    check("marked and unmarked are separated", says(r, "blind reviews       : 1", "self reviews        : 2"))
    # Reviewed at an EARLIER commit, a review still requested: "not yet" (1), not "never coming" (5).
    r = go(polls=[("OPEN", "newhead", 1)], reviews=[rev("bot", commit="oldhead", at=T)])
    check("stale review WITH a request pending is 'not yet', and flags the earlier commit", r.rc == 1 and says(r, "an EARLIER commit"))

    # exit 5: nothing is coming
    r = go(polls=[("OPEN", "newhead", 0)], reviews=[rev("bot", commit="oldhead", at=T)])
    check("reviewed then pushed, nothing requested, exits 5 and names the cause", r.rc == 5 and says(r, "NO REVIEW COMING"))
    r = go("--json", "-q", polls=[("OPEN", "newhead", 0)], reviews=[rev("bot", commit="oldhead", at=T)])
    check("--json keeps exit 5, stdout one object with the cause in no_review_coming",
          r.rc == 5 and json.loads(r.out)["no_review_coming"]["cause"] == "head-moved")
    r = go()
    check("a never-reviewed PR is 1, not 5, and claims nothing about the cause", r.rc == 1 and not says(r, "NO REVIEW COMING"))

    # waiting, against the fake clock
    r = go("--wait", "2", "--interval", "1", "-q", polls=[("OPEN", "abc123", 1)])
    check("wait expires with nothing and exits 1, napping the interval", r.rc == 1 and r.naps == [1, 1])
    r = go("--wait", "60", "--interval", "1", "-q", polls=[("OPEN", "abc123", 1)], reviews=[rev("bot", at=T)])
    check("wait returns immediately once the head is reviewed", r.rc == 0 and r.naps == [])
    # Exit 5 must not sleep: --wait 3600 with a permanent state comes back at once.
    r = go("--wait", "3600", "--interval", "1", "-q", polls=[("OPEN", "newhead", 0)], reviews=[rev("bot", commit="oldhead", at=T)])
    check("a permanent no-review state exits 5 under a long --wait, without sleeping first", r.rc == 5 and r.naps == [])
    r = go("--wait", "3600", "--interval", "1", "-q", polls=[("CLOSED", "abc123", 1)])
    check("a CLOSED PR stops the wait and exits 1", r.rc == 1 and r.naps == [])
    # --wait SHORTER than --interval once answered at once while reporting a
    # 4-second wait: the nap is clamped to what is left.
    r = go("--wait", "4", "--interval", "60", "-q", polls=[("OPEN", "abc123", 1)])
    check("a --wait shorter than --interval still exits 1, waits the requested time and polls again at the deadline",
          r.rc == 1 and r.naps == [4] and r.polls >= 2)

    # invocation
    check("no PR number exits 2", die(lambda: rs.run([], {})).startswith("2:a PR number is required"))
    check("zero --interval exits 2", die(lambda: rs.parse(["77", "o/r", "--interval", "0"])) == "2:--interval must be greater than zero, got '0'.")
    # The duration table: this is what stops as_seconds accepting something a caller did not mean.
    check("rejects --wait '', '10sm', 'm', '-1', '1x', '10 m'",
          all(die(lambda v=v: rs.parse(["77", "o/r", "--wait", v])).startswith("2:--wait needs a duration")
              for v in ("", "10sm", "m", "-1", "1x", "10 m")))
    check("accepts --wait 5m --interval 1s, --wait 2h --interval 30s and bare seconds",
          [(rs.parse(["77", "--wait", w, "--interval", i]).wait, rs.parse(["77", "--wait", w, "--interval", i]).interval)
           for w, i in (("5m", "1s"), ("2h", "30s"), ("300", "1"))] == [("300", "1"), ("7200", "30"), ("300", "1")])
    r = go("--wait", "5m", "--interval", "1s", "-q", reviews=[rev("bot", at=T)])
    check("  and a reviewed head returns 0 at once either way", r.rc == 0 and r.naps == [])
    check("--help documents exit 5", "no review is COMING" in rs.HELP)
    check("three failed lookups exit 2", go(polls=["FAIL"] * 3).rc == 2)

    # an unreadable lookup is not 'no reviews'
    r = go("--wait", "10", "--interval", "1", "-q", reviews_fail=True)
    check("a failing reviews lookup exits 2, not 1, and renders no verdict from data it never had",
          r.rc == 2 and not says(r, "head reviewed?"))
    r = go(polls=[("OPEN", "newsha", 0)], reviews=[rev("reviewer-a", commit="newsha")], comments_fail=True)
    check("a failing comments lookup exits 2, not 0, and renders no verdict from data it never had",
          r.rc == 2 and not says(r, "head reviewed?"))
    # A partial probe is not readable data. The numbers are load-bearing:
    # wait < 3 x interval reaches the fall-out path (two failures, not three).
    r = go("--wait", "4", "--interval", "3", "-q", polls=[("OPEN", "sha-one", 0), ("OPEN", "sha-two", 0)], reviews_fail_after=1)
    check("a probe that dies halfway does not render stale data", r.rc == 2 and not says(r, "head reviewed?"))

    # coverage is ANY review at the head
    r = go(polls=[("OPEN", "head1", 0)], reviews=[rev("reviewer-a", commit="head1", at="2026-08-12T10:00:00Z"),
                                                   rev("reviewer-b", commit="oldsha", at="2026-08-12T11:00:00Z")])
    check("a stale review submitted LAST cannot mask head coverage", r.rc == 0 and says(r, "head reviewed?      : yes"))
    check("a merged pr with a stale review does not claim exit 5",
          go(polls=[("MERGED", "newsha", 0)], reviews=[rev("reviewer-a", commit="oldsha1")]).rc != 5)
    check("an open pr past its newest review still exits 5",
          go(polls=[("OPEN", "newsha", 0)], reviews=[rev("reviewer-a", commit="oldsha1")]).rc == 5)

    # a configured reviewer's verdict comments
    r = go(polls=[("OPEN", "e7eb89d90cabc", 0)], comments=[verdict("e7eb89d90c")])
    check("a verdict comment at the head exits 0, with zero reviews, shows its source and names it a clean review",
          r.rc == 0 and says(r, "head reviewed?      : yes", "verdict comments    : 1", "a clean review leaves no review object"))
    r = go(polls=[("OPEN", "bbbbbbbbbb", 0)], comments=[verdict("aaaaaaaaaa")])
    check("a verdict naming an older commit is READ, not coverage: the head stays unreviewed, with the cause",
          r.rc == 5 and says(r, "verdict comments    : 1", "head reviewed?      : no", "NO REVIEW COMING"))
    check("a short verdict sha covers a full head",
          go(polls=[("OPEN", "2756062690aaaabbbbccccddddeeeeffff00001111", 0)], comments=[verdict("2756062690")]).rc == 0)
    r = go(polls=[("OPEN", "cccccccccc", 0)], comments=[verdict("cccccccccc", login="some-stranger")])
    check("a stranger's forged verdict is NOT coverage and none is counted",
          r.rc == 1 and says(r, "head reviewed?      : no", "verdict comments    : 0"))
    check("the pr author cannot certify their own head",
          go(polls=[("OPEN", "dddddddddd", 0)], comments=[verdict("dddddddddd", login="me")]).rc == 1)
    other = verdict("eeeeeeeeee", login="some-other-bot")
    check("AGENT_FABRIC_VERDICT_AUTHORS names the reviewer",
          go(polls=[("OPEN", "eeeeeeeeee", 0)], comments=[other], env={"AGENT_FABRIC_VERDICT_AUTHORS": '["some-other-bot"]'}).rc == 0)
    check("an account the list does not name is not recognised", go(polls=[("OPEN", "eeeeeeeeee", 0)], comments=[other]).rc == 1)
    r = go(polls=[("OPEN", "eeeeeeeeee", 0)], comments=[verdict("eeeeeeeeee")], env={"AGENT_FABRIC_VERDICT_AUTHORS": ""})
    check("unconfigured, no comment is a verdict and none is counted", r.rc == 1 and says(r, "verdict comments    : 0"))

    # a configured reviewer that DECLINED ends the wait
    ff = [("OPEN", "ffffffffff", 0)]
    r = go("--wait", "10m", "--interval", "1s", polls=ff, comments=[decline()])
    check("a decline exits 5 immediately, not after 10m, names the cause and reports the decline",
          r.rc == 5 and r.naps == [] and says(r, "the reviewer declined", "reviewer declined   :"))
    check("  and says WHICH decline it is, in the reviewer's words, in the verdict line too",
          says(r, "decline reason      : Usage limit reached for reviews",
               "the reviewer declined: Usage limit reached for reviews; none will run. (exit 5)"))
    r = go(polls=ff, comments=[decline(body="No environment for this repo; none will run.")])
    check("every configured phrase is the same verdict: the second exits 5 too, with its reason",
          r.rc == 5 and says(r, "decline reason      : No environment for this repo"))
    r = go(polls=ff, comments=[decline()], env={"AGENT_FABRIC_REVIEWER_REFUSAL_RE": ""})
    check("with no refusal wording configured, the comment is just a comment", r.rc == 1 and not says(r, "reviewer declined   :"))
    r = go(polls=ff, comments=[decline("2026-08-01T10:00:00Z"), verdict("ffffffffff", at="2026-08-20T10:00:00Z")])
    check("a refusal a later review superseded is stale: the later verdict wins", r.rc == 0 and says(r, "superseded by later coverage"))
    r = go(polls=ff, comments=[decline(login="some-stranger")])
    check("a stranger cannot fake a refusal either", r.rc == 1 and not says(r, "reviewer declined   :"))

    # a configured review ask in flight is not 'nothing coming'
    stale = [rev("reviewer-a", commit="aaaaaaaaaa", at="2026-08-01T10:00:00Z")]
    r = go(polls=ff, reviews=stale, comments=[ask("2026-08-20T10:00:00Z")])
    check("a configured review ask in flight reports 'not yet', claims nothing about the cause and says so",
          r.rc == 1 and says(r, "in flight") and not says(r, "NO REVIEW COMING"))
    r = go(polls=ff, reviews=stale, comments=[ask("2026-08-20T10:00:00Z")], env={"AGENT_FABRIC_REVIEW_REQUEST_RE": ""})
    check("with no ask phrase configured, the stale review is 'nothing is coming' and no ask is reported",
          r.rc == 5 and not says(r, "review asked        :"))
    r = go(polls=ff, reviews=[rev("reviewer[bot]", commit="ffffffffff", at="2026-08-20T10:00:00Z")],
           comments=[ask("2026-08-15T10:00:00Z")], head_date="2026-08-10T00:00:00Z")
    check("the review it asked for answers the ask: the head is covered and the ask reads answered, not in flight",
          r.rc == 0 and says(r, "already answered") and not says(r, "in flight"))

    def ask_case(head_date, review_at, ask_at, **kw):
        return go(polls=ff, reviews=[rev("reviewer-a", commit="aaaaaaaaaa", at=review_at)], comments=[ask(ask_at)],
                  head_date=head_date, **kw)

    pushed = suite("2026-08-25T12:06:07Z")
    # Committed 11:48:37, pushed 12:06: an ask inside that gap is for the PREVIOUS head.
    r = ask_case("2026-08-25T11:48:37Z", "2026-08-25T11:50:00Z", "2026-08-25T11:55:00Z", suites=[pushed])
    check("an ask between commit and push is for the older head", r.rc == 5 and says(r, "NO REVIEW COMING"))
    r = ask_case("2026-08-25T11:48:37Z", "2026-08-25T11:50:00Z", "2026-08-25T12:10:00Z", suites=[pushed])
    check("an ask after the ref moved is in flight", r.rc == 1)
    r = ask_case("2026-01-01T00:00:00Z", "2026-08-25T11:50:00Z", "2026-08-25T11:55:00Z", suites=[pushed])
    check("an ancient commit date does not make the ask current (a REBASED head still expires an older ask)",
          r.rc == 5 and says(r, "NO REVIEW COMING"))
    # Dating from the latest suite bought exit 5 here and paid for it with a
    # false exit 5 on every dispatch, schedule, re-run and reopen.
    r = ask_case("2026-08-25T08:00:00Z", "2026-08-25T11:50:00Z", "2026-08-25T11:00:00Z",
                 suites=[pushed, suite("2026-08-25T09:00:00Z")])
    check("a RESTORED sha costs a wait, not a verdict, and nothing declares the review dead",
          r.rc == 1 and not says(r, "NO REVIEW COMING"))
    for label, extra in (("the other pr's suite is ignored", suite("2026-01-01T00:00:00Z", ref="someone/else", prs=(999,))),
                         ("the other ref's suite is ignored", suite("2026-01-01T00:00:00Z", ref="someone/else")),
                         ("a suite belonging to no pr is ignored", suite("2026-01-01T00:00:00Z", prs=()))):
        r = ask_case("2026-08-25T11:48:37Z", "2026-08-25T11:50:00Z", "2026-08-25T11:55:00Z", suites=[extra, pushed])
        check(label, r.rc == 5 and says(r, "NO REVIEW COMING"))
    # Dispatch, schedule, re-run and reopen raise a later suite for the
    # unchanged sha with this ref AND this pr: ordering rejects the class.
    r = ask_case("2026-08-25T11:48:37Z", "2026-08-25T11:50:00Z", "2026-08-25T12:10:00Z",
                 suites=[pushed, suite("2026-08-25T13:00:00Z")])
    check("a later suite does not move the head's birthday, and nothing declares the review dead",
          r.rc == 1 and not says(r, "NO REVIEW COMING"))
    # HEAD_DATE is LATER than the ask, so the committer-date fallback yields
    # exit 5: without that, every way of getting this wrong still reached 1.
    r = ask_case("2026-08-25T12:30:00Z", "2026-08-25T11:50:00Z", "2026-08-25T11:55:00Z",
                 suites=[pushed], page2=[suite("2026-08-25T11:00:00Z")])
    check("a later page's earlier suite wins (the earliest suite is found ACROSS pages)",
          r.rc == 1 and not says(r, "NO REVIEW COMING"))
    r = ask_case("2026-01-01T00:00:00Z", "2026-08-25T11:50:00Z", "2026-08-25T11:55:00Z",
                 suites=[suite("2026-08-25T12:06:07Z", ref='mine/we"ird')], head_ref='mine/we"ird')
    check("a quote in the branch name does not break the lookup: the suite date is still found",
          r.rc == 5 and says(r, "NO REVIEW COMING"))
    # The ask falls BEFORE the commit date, so the fallback CHANGES the answer.
    r = ask_case("2026-08-20T00:00:00Z", "2026-08-25T10:00:00Z", "2026-08-15T10:00:00Z", suites=[])
    check("no check suite falls back to the commit date, which still decides", r.rc == 5 and says(r, "NO REVIEW COMING"))
    r = ask_case("2026-08-10T00:00:00Z", "2026-08-20T10:00:00Z", "2026-08-15T10:00:00Z")
    check("a STALE review does not answer a later ask: it still counts as in flight",
          r.rc == 1 and not says(r, "NO REVIEW COMING"))
    r = ask_case("2026-08-10T00:00:00Z", "2026-08-07T10:00:00Z", "2026-08-05T10:00:00Z")
    check("an ask made BEFORE this head still expires", r.rc == 5 and says(r, "NO REVIEW COMING"))
    r = go(polls=ff, reviews=[rev("reviewer-a", commit="aaaaaaaaaa", at="2026-08-20T10:00:00Z")], comments=[ask("2026-08-01T10:00:00Z")])
    check("an ask ALREADY ANSWERED does not suppress the verdict: the answer that followed it wins and is marked",
          r.rc == 5 and says(r, "already answered"))
    r = go(polls=ff, comments=[decline("2026-08-01T10:00:00Z"), ask("2026-08-20T10:00:00Z")])
    check("a re-ask after a refusal supersedes it: the wait reopens", r.rc == 1 and not says(r, "the reviewer declined"))
    r = go(polls=ff, comments=[ask("2026-08-01T10:00:00Z"), decline("2026-08-20T10:00:00Z")])
    check("a refusal AFTER the ask still ends the wait", r.rc == 5 and says(r, "the reviewer declined"))
    check("a pending request from ANYONE suppresses the verdict",
          go(polls=[("OPEN", "ffffffffff", ["a-human"])], reviews=stale).rc == 1)

    # a FORMAL request against a decline, ordered by the timeline
    one = [("OPEN", "ffffffffff", 1)]
    refused = [decline("2026-08-20T10:00:00Z")]
    r = go(polls=one, comments=refused, formal=[("2026-08-01T10:00:00Z", "reviewer[bot]")])
    check("a formal request PREDATING the refusal does not supersede it", r.rc == 5 and says(r, "the reviewer declined"))
    r = go(polls=one, comments=refused, formal=[("2026-08-25T10:00:00Z", "reviewer[bot]")])
    check("a formal request AFTER the refusal supersedes it: the wait reopens", r.rc == 1 and not says(r, "the reviewer declined"))
    # The timeline keeps a REVIEW_REQUESTED_EVENT after the request is
    # withdrawn: the event has to name a reviewer who is STILL pending.
    r = go(polls=one, comments=refused, formal=[("2026-08-25T10:00:00Z", "a-human")])
    check("a request since WITHDRAWN cannot supersede the refusal", r.rc == 5 and says(r, "the reviewer declined"))
    r = go(polls=[("OPEN", "ffffffffff", ["a-human", "reviewer[bot]"])], comments=[ask("2026-08-01T10:00:00Z"), decline("2026-08-20T10:00:00Z")])
    check("a decline does not answer a PENDING HUMAN request", r.rc == 1 and not says(r, "the reviewer declined"))
    r = go(polls=one, comments=refused, formal=[("2026-08-19T10:00:00Z", "reviewer[bot]"), ("2026-08-25T10:00:00Z", "a-human")])
    check("a request event for someone NOT pending does not clear the refusal", r.rc == 5 and says(r, "the reviewer declined"))
    r = go(polls=one, comments=refused, formal=[("2026-08-25T10:00:00Z", "reviewer[bot]")])
    check("a request of the reviewer itself after the refusal clears it", r.rc == 1)
    check("an unreadable timeline leaves the refusal standing", go(polls=one, comments=refused, formal=[]).rc == 5)
    r = go(polls=ff, reviews=stale, comments=refused)
    check("a CURRENT refusal outranks the stale-review message: names the DECLINE, does not send the caller to re-review",
          r.rc == 5 and says(r, "the reviewer declined") and not says(r, "dispatch a re-review (exit 5)"))

    # a configuration that cannot be applied is refused, never read as 'none'
    for var, bad in (("AGENT_FABRIC_REVIEW_REQUEST_RE", "@reviewer review("), ("AGENT_FABRIC_REVIEWER_REFUSAL_RE", "[unclosed"),
                     ("AGENT_FABRIC_VERDICT_AUTHORS", "reviewer[bot]")):
        r = go(polls=ff, comments=refused, env={var: bad})
        check(f"an unusable {var} exits 2 and names the variable", r.rc == 2 and says(r, var))
    r = go(polls=ff, comments=[decline(body="\r\nCannot review this PR — usage limit reached for reviews.\r\nTry later.")])
    check("the decline reason is the reviewer's first line, whole, CR stripped, in the report and the verdict line",
          r.rc == 5 and says(r, "decline reason      : Cannot review this PR — usage limit reached for reviews.",
                             "the reviewer declined: Cannot review this PR — usage limit reached for reviews. (exit 5)"))
    check("a MERGED pr is not ended by a refusal", go(polls=[("MERGED", "ffffffffff", 0)], comments=refused).rc == 1)
    # A background watcher runs for half an hour, so anything unconditional on
    # stderr is emitted on every poll; the head-birth path is where it leaked.
    r = go("-q", polls=ff, reviews=[rev("reviewer-a", commit="aaaaaaaaaa", at="2026-08-25T11:50:00Z")],
           comments=[ask("2026-08-25T12:10:00Z")], head_date="2026-08-25T11:48:37Z", suites=[pushed])
    check("no diagnostic output escapes under -q on the head-birth path", r.err == "")

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
