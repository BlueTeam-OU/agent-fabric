#!/usr/bin/env python3
"""Tests for tools/fabric/github/post_review.py's internals; the behaviour
is tests/test_post_review_cli.py's, run through fabric-pr (ADR-040 §5
rule 5)."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import gh  # noqa: E402
import results  # noqa: E402
import review_brief  # noqa: E402
from github import post_review, pr_reply, pr_review_status  # noqa: E402

LOC = "identities/roles/language-culture/locale/ge/team.md"


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    print("the marker is one string everywhere it is read")
    check("the reader's constant", post_review.REVIEW_MARKER == pr_review_status.REVIEW_MARKER)
    check("results.py's", results.REVIEW_MARKER is post_review.REVIEW_MARKER)

    print("the lane predicate agrees with pr-reply's")
    for b in ("h/l/feat/x", "h/l/Fix/x", "h/l/x", "dependabot/pub/a/b", "/l/feat/x", "snyk-bot/a/b/c"):
        check(f"'{b}'", post_review.branch_names_a_session(b) == pr_reply.branch_names_a_session(b))

    print("a report's dispatch header: only pinned posts (agent-fabric ADR-020 §5 rule 10)")

    def header(**req) -> str:
        """The header as review_brief renders it into a brief, for a request of these fields."""
        return "\n".join(review_brief.dispatch_header({"mode": "review", "repository": "/nowhere", **req}, None,
                                                       "claude", None, "d-1", "2026-10-14T00:00:00Z"))

    pinned, tree = header(range="a..b"), header(diff="/x.diff")
    check("the producer's two modes are what is told apart",
          '"evidence_mode": "pinned"' in pinned and '"evidence_mode": "working-tree"' in tree)
    for label, body, refused in (
        ("no header: posts", "F1 (P2) …", False),
        ("a pinned header: posts", f"{pinned}\nF1 (P2) …", False),
        ("a working-tree header: refused", f"{tree}\nF1 (P2) …", True),
        ("working-tree below the findings: refused", f"F1 (P2) …\n\n{tree}\n", True),
        ("a pinned and a working-tree header: refused", f"{pinned}\n{tree}", True),
        ("indented, tilde-fenced: refused", "  ~~~agent-fabric-dispatch v1\n" + tree.split("\n", 1)[1].rsplit("\n", 1)[0] + "\n  ~~~", True),
        ("evidence_mode explicitly working-tree on a ranged request: refused", header(range="a..b", evidence="working-tree"), True),
        ("no evidence_mode: refused", "```agent-fabric-dispatch v1\n{\"engine\": \"claude\"}\n```", True),
        ("not JSON: refused", "```agent-fabric-dispatch v1\nevidence_mode: pinned\n```", True),
        ("never closed: refused", pinned.rsplit("\n", 1)[0], True),
        ("another version's fence: refused, the name outside a header it reads", "```agent-fabric-dispatch v2\n{}\n```", True),
        ("CRLF line ends, working-tree: refused", tree.replace("\n", "\r\n") + "\r\nF1", True),
        ("CRLF line ends, pinned: posts", pinned.replace("\n", "\r\n") + "\r\nF1", False),
        ("evidence_mode given twice: refused",
         '```agent-fabric-dispatch v1\n{"evidence_mode": "working-tree", "evidence_mode": "pinned"}\n```', True),
        ("a pinned header whose JSON quotes a fence: posts",
         "````agent-fabric-dispatch v1\n{\"evidence_mode\": \"pinned\", \"note\": \"```\"}\n````", False),

        # CommonMark allows spaces between the fence and its info string (review of #259, F5).
        ("a spaced fence, working-tree: refused", tree.replace("```agent", "``` agent", 1) + "\nF1", True),
        ("a spaced tilde fence with a tab, working-tree: refused",
         "~~~ \tagent-fabric-dispatch v1\n" + tree.split("\n", 1)[1].rsplit("\n", 1)[0] + "\n~~~", True),
        ("a spaced fence, pinned: posts", pinned.replace("```agent", "```  agent", 1) + "\nF1", False),

        # A header DISPATCH_FENCE does not see is not read, so the name anywhere else refuses (review of #259, risk 1).
        ("a working-tree header in a blockquote: refused", "F1 (P2) …\n\n" + "\n".join("> " + l for l in tree.split("\n")), True),
        ("a pinned header in a blockquote: refused, unread", "\n".join("> " + l for l in pinned.split("\n")) + "\nF1", True),
        ("a working-tree header in a list item: refused",
         "- F1 (P2) quotes:\n  - " + tree.replace("\n", "\n    "), True),
        ("a pinned header, then a list item opening a working-tree one: refused",
         f"{pinned}\n- " + tree.replace("\n", "\n  "), True),
        ("a header nested in a list item's blockquote: refused",
         "1. F1 quotes:\n   > " + tree.replace("\n", "\n   > "), True),
        ("a spaced fence in a blockquote: refused", "\n".join("> " + l for l in tree.replace("```agent", "``` agent", 1).split("\n")), True),
        # Only a fence opens a header: prose and a quoted hunk naming it carry none, and post (supplier review, F1).
        ("the name in prose: posts", f"{pinned}\nF1 (P3) the agent-fabric-dispatch header is long", False),
        ("the version in inline code: posts", "F1 (P3) `agent-fabric-dispatch v1` is long", False),
        ("a quoted diff adding and removing a header's fence: posts, + and - opening no list item",
         "F1 (P2) quotes the hunk:\n```diff\n+```agent-fabric-dispatch v1\n+{}\n+```\n-```agent-fabric-dispatch v1\n```", False),
        ("a list item whose marker has a tab: refused", "-\t" + tree.replace("\n", "\n  "), True),
        ("a quoted hunk naming it: posts",
         "F1 (P2)\n```\n+DISPATCH_VERSION = \"agent-fabric-dispatch v1\"\n```", False),
    ):
        why = post_review.evidence_refusal(body)
        check(label, bool(why) is refused and (not refused or "agent-fabric-dispatch v1" in why))
    check("a working-tree refusal says what it read and the rule",
          all(w in post_review.evidence_refusal(tree) for w in ("'working-tree'", "ADR-020 §5 rule 10", "line 1")))
    quoted = post_review.evidence_refusal(f"{pinned}\nF1 quotes the fixture:\n\n````markdown\n{tree}\n````\n")
    check("a pinned report quoting a working-tree header: refused, saying a quote counts and where it is",
          "one it quotes too" in quoted and f"line {len(pinned.splitlines()) + 4}" in quoted)

    blockquoted = post_review.evidence_refusal("F1 (P2) …\n\n" + "\n".join("> " + l for l in tree.split("\n")))
    check(f"a stray name's refusal names its line and says what to do (got {blockquoted!r})",
          blockquoted.startswith("line 3 opens an agent-fabric-dispatch fence") and "blockquote" in blockquoted
          and "Take the block out" in blockquoted)
    later = post_review.evidence_refusal(f"{pinned}\nF1\n> {pinned.splitlines()[0]}")
    check("a stray after a recognised header is counted from the report's first line",
          later.startswith(f"line {len(pinned.splitlines()) + 2} opens"))
    check("a line is counted by \\n, not by every break splitlines knows",
          post_review.evidence_refusal(f"F1 a\u2028b\x0cc\nF2\n> {tree.splitlines()[0]}").startswith("line 3 ")
          and "header at line 2 " in post_review.evidence_refusal(f"F1 a\u2028b\n{tree}"))

    print("a pinned report names the one head it covers (agent-fabric ADR-020 §5 rule 10)")
    old, new = "a" * 40, "b" * 40

    def ranged(sha: str | None) -> str:
        """A pinned header as the brief renders it for a range whose head is sha."""
        return "\n".join(review_brief.dispatch_header({"mode": "review", "repository": "/nowhere", "range": "x..y"},
                                                       {"base_sha": "c" * 40, "head_sha": sha, "card_base": None},
                                                       "claude", None, "d-1", "2026-10-14T00:00:00Z"))
    for label, body, want, why in (
        ("no header: no head read here, so run() refuses it without --head", "F1 (P2) …", None, ""),
        ("one header: its head_sha", f"{ranged(old)}\nF1", old, ""),
        ("two headers on one head: that head", f"{ranged(old)}\nF1\n````\n{ranged(old)}\n````", old, ""),
        ("two headers on different heads: refused, naming both", f"{ranged(old)}\n{ranged(new)}", None,
         "different heads (aaaaaaaaaaaa at line 1, bbbbbbbbbbbb at line"),
        ("a header naming no head_sha: refused", f"{ranged(None)}\nF1", None, "names no head_sha"),
        ("a header from a request with no range: refused", header(range="a..b") + "\nF1", None, "names no head_sha"),
        ("an abbreviated sha: refused", f"{ranged(old[:12])}\nF1", None, "names no head_sha"),
        ("a sha-256 head: taken", f"{ranged('d' * 64)}\nF1", "d" * 64, ""),
    ):
        got, refusal = post_review.report_head(body)
        check(f"{label} (got {got!r}, {refusal!r})", got == want and (why in refusal if why else not refusal))

    print("a head that is not the PR's head is posted only when it is a commit of the PR, failing closed")
    real_run = gh.run
    try:
        for label, out, want in (
            ("listed: posts", [[{"sha": new}], [{"sha": old}]], ""),
            ("not listed: refused", [[{"sha": new}]], "is not a commit of PR #1"),
            ("a failing call: refused", None, "could not be read"),
            ("an error object for a page: refused", [{"message": "Not Found"}], "could not be read"),
            ("output that is not JSON: refused", "not json", "could not be read"),
            ("not in 250, GitHub's cap: refused, the list may be cut", [[{"sha": new}] * 250], "a list it cuts there"),
            ("in 250, the cap: posts", [[{"sha": new}] * 249 + [{"sha": old}]], ""),
        ):
            gh.run = (lambda out: lambda args, **kw: (_ for _ in ()).throw(gh.GhError("gh api", "Not Found", 404))
                      if out is None else out if isinstance(out, str) else json.dumps(out))(out)
            got = post_review.pr_commit_refusal("o/r", "1", old)
            check(f"{label} (got {got!r})", want in got if want else got == "")
    finally:
        gh.run = real_run

    print("the posted report carries no dispatch header (review of #259, risk 1)")
    named = header(range="a..b", job_id="j9")
    check("the fixture header names a job", '"job_id": "j9"' in named)
    strip = post_review.without_dispatch_headers
    for label, body, want in (
        ("no header: the report byte for byte", "F1 (P2) …\r\n\n", "F1 (P2) …\r\n\n"),
        ("a pinned header on top: only the findings", f"{named}\n\nF1 (P2) …", "F1 (P2) …"),
        ("a spaced fence: taken out too", named.replace("```agent", "``` agent", 1) + "\nF1", "F1"),
        ("CRLF line ends: taken out", (named + "\nF1").replace("\n", "\r\n"), "F1"),
        ("CRLF line ends: the rest keeps them", (named + "\nF1\nF2\n").replace("\n", "\r\n"), "F1\r\nF2"),
        ("line breaks splitlines knows besides \\n: kept as they are",
         f"{named}\nF1 a\u2028b\x0cc\x1dd\u0085e", "F1 a\u2028b\x0cc\x1dd\u0085e"),
        ("two headers, one quoted: both out, the prose kept",
         f"{named}\nF1 quotes it:\n\n````markdown\n{named}\n````\nF2", "F1 quotes it:\n\n````markdown\n````\nF2"),
        ("a longer fence holding a fence-like line: the whole header out",
         "````agent-fabric-dispatch v1\n{\"evidence_mode\": \"pinned\", \"note\": \"```\"}\n````\nF1", "F1"),
        ("another version's block: kept", "```agent-fabric-dispatch v2\n{}\n```", "```agent-fabric-dispatch v2\n{}\n```"),
    ):
        got = strip(body)
        check(f"{label} (got {got!r})", got == want and review_brief.DISPATCH_VERSION not in got)

    print("locale_only fails closed")
    real_run = gh.run

    def answering(out=None, fail=False):
        def fake(args, **kw):
            if fail:
                raise gh.GhError("gh api", "Not Found (HTTP 404)", 404)
            return out if isinstance(out, str) else json.dumps(out)
        return fake

    cases = [
        ("one locale file", [[{"filename": LOC}]], True),
        ("two pages of locale files", [[{"filename": LOC}], [{"filename": LOC.replace("team", "b")}]], True),
        ("a failing call", None, False),
        ("an error object for a page", [{"message": "Not Found"}], False),
        ("items that are not files", [["not an object"]], False),
        ("an empty list", [[]], False),
        ("a file with no name", [[{"filename": None}]], False),
        ("a code file renamed into locale/", [[{"filename": LOC, "previous_filename": "tools/x.py"}]], False),
        ("a path nested below a locale", [[{"filename": LOC.replace("team.md", "sub/x.md")}]], False),
        ("a name carrying a newline", [[{"filename": LOC + "\ntools/x.py"}]], False),
        ("3000 files, the list cap", [[{"filename": LOC}] * 3000], False),
        ("2999 files", [[{"filename": LOC}] * 2999], True),
        ("output that is not JSON", "not json", False),
    ]
    try:
        for label, out, want in cases:
            gh.run = answering(out, fail=out is None)
            check(label, post_review.locale_only("o/r", "1") is want)
    finally:
        gh.run = real_run

    print("a PR payload with a head but no branch refuses before the lane guard")
    real_view, real_run, real_repo = gh.pr_view, gh.run, os.environ.get("GH_REPO")
    gh.pr_view = lambda n, fields, **kw: {"number": n, "state": "OPEN", "headRefOid": "abc"}
    gh.run = lambda args, **kw: "o/r\n"
    # The repository is named, never read from the checkout's origin (a copy without a remote has none).
    os.environ["GH_REPO"] = "o/r"
    try:
        post_review.run(["552", "--head", "a" * 40], "findings")
        check("refused", False)
    except post_review.Refused as e:
        check("refused, naming the branch", "head branch" in str(e))
    finally:
        gh.pr_view, gh.run = real_view, real_run
        if real_repo is None:
            os.environ.pop("GH_REPO", None)
        else:
            os.environ["GH_REPO"] = real_repo

    print("--help and a usage error never wait on an open stdin (review of #71)")
    shim = [os.path.join(HERE, "bin", "fabric-pr"), "post-review"]
    for args, want in ((["--help"], 0), (["--bogus"], 2)):
        held = subprocess.Popen([*shim, *args], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        try:
            rc = held.wait(timeout=20)
        except subprocess.TimeoutExpired:
            held.kill()
            held.wait()
            rc = None
        finally:
            held.stdin.close()
        check(f"{' '.join(args)} exits {want} with stdin still open", rc == want)
    print("--help's examples: the review class's form is the one its guard admits (review of #283, F2)")
    spec = importlib.util.spec_from_file_location(
        "review_bash_guard", os.path.join(HERE, "runtime", "claude-code", "hooks", "review-bash-guard.py"))
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    examples, cur = [], None
    for line in post_review.HELP.splitlines():
        if line.startswith("  fabric-pr post-review 552"):
            cur = [line[2:]]
        elif cur is not None:
            cur.append(line[2:])
            if line == "  EOF":
                examples.append("\n".join(cur))
                cur = None
    check(f"two examples, the first without --head and the second with it ({len(examples)} found)",
          len(examples) == 2 and "--head" not in examples[0].splitlines()[0]
          and "--head" in examples[1].splitlines()[0])
    if len(examples) == 2:
        check("the first opens its body with an agent-fabric-dispatch v1 block",
              examples[0].splitlines()[1] == f"```{review_brief.DISPATCH_VERSION}")
        check("the review class's guard admits the first", guard.posted_review(examples[0]) is not None)
        # With a real sha for the placeholder: a guard widened to exempt a 40-hex --head must fail this.
        real = examples[1].replace("<full sha of the commit reviewed>", "a" * 40)
        check("and gives the second, the --head path outside the review class, no exemption",
              "<" not in real.splitlines()[0].split("<<")[0] and guard.posted_review(real) is None)
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
