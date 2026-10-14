#!/usr/bin/env python3
"""Tests for tools/fabric/github/post_review.py's internals; the behaviour
is tests/test_post_review_cli.py's, run through fabric-pr (ADR-040 §5
rule 5)."""
from __future__ import annotations

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
        ("another fence's info string: not a header", "```agent-fabric-dispatch v2\n{}\n```", False),
        ("CRLF line ends, working-tree: refused", tree.replace("\n", "\r\n") + "\r\nF1", True),
        ("CRLF line ends, pinned: posts", pinned.replace("\n", "\r\n") + "\r\nF1", False),
        ("evidence_mode given twice: refused",
         '```agent-fabric-dispatch v1\n{"evidence_mode": "working-tree", "evidence_mode": "pinned"}\n```', True),
        ("a pinned header whose JSON quotes a fence: posts",
         "````agent-fabric-dispatch v1\n{\"evidence_mode\": \"pinned\", \"note\": \"```\"}\n````", False),
    ):
        why = post_review.evidence_refusal(body)
        check(label, bool(why) is refused and (not refused or "agent-fabric-dispatch v1" in why))
    check("a working-tree refusal says what it read and the rule",
          all(w in post_review.evidence_refusal(tree) for w in ("'working-tree'", "ADR-020 §5 rule 10", "line 1")))
    quoted = post_review.evidence_refusal(f"{pinned}\nF1 quotes the fixture:\n\n````markdown\n{tree}\n````\n")
    check("a pinned report quoting a working-tree header: refused, saying a quote counts and where it is",
          "one it quotes too" in quoted and f"line {len(pinned.splitlines()) + 4}" in quoted)

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
        post_review.run(["552"], "findings")
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
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
