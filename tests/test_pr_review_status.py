#!/usr/bin/env python3
"""Tests for tools/fabric/github/pr_review_status.py's internals; the behaviour
is tests/test_pr_review_status_cli.py's, run against the shim
(ADR-040 §5 rule 5). What the fixtures there reach only through a whole run is
checked here directly: the duration table and its octal reading, the regex
dialect bridge, what counts as coverage, the ordering of a decline against a
request, and the shapes the report prints."""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys

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
    check("rows carry the 8-character sha", doc["blind"]["rows"] == [{"login": "me", "commit_sha8": "abc123de", "at": "2026-08-07T10:00:00Z"}])
    unknown = json.loads(rs.render_json(ctx, rs.Probe(head=HEAD), rs.Extras([], None, 0, 0), "", ""))
    check("unknown threads are null, never 0", unknown["unresolved_threads"] is None and unknown["no_review_coming"] is None)
    check("the text is not --json's", "\n  " in rs.render_json(ctx, rs.Probe(head=HEAD), x, "", "") and "ü" in rs.render_json(ctx, rs.Probe(head=HEAD, state="ü"), x, "", ""))

    # ── gh: a failing `gh pr checks` still carries its table ─────────
    e = gh.GhError("gh pr checks 1", "exit 8", 8, False, "a\tpass\n")
    check("the exit-8 table survives the error", e.stdout == "a\tpass\n")
    check("the pass count reads \\spass\\s per line", [bool(rs.PASS_LINE.search(l)) for l in ("a / b\tpass\t1s", "a / b\tfail\t1s", "password")] == [True, False, False])

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
