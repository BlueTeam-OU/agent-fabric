"""tools/fabric/github/review_status/config.py — the markers, and the environment's configuration: reviewer logins, markers and their patterns.
A part of tools/fabric/github/pr_review_status.py, whose docstring is the contract."""
from __future__ import annotations

import json
import re
import warnings
from dataclasses import dataclass
from github.review_status.base import Die


# The marker post-review writes as the first line of every review the
# review class posts. Must stay byte-identical to post_review.REVIEW_MARKER:
# test_post_review_cli.py compares this line with that one, and
# tests/test_post_review.py the two constants, so a one-sided change is
# caught. A literal, not an import, so the comparison has two sides.
REVIEW_MARKER = "<!-- agent-fabric-review v1 -->"


# Reviews posted under earlier markers keep counting: the fabric's own
# previous marker is built in, and a project's pr-tools.json
# (projects/<id>/integration/, legacy_review_markers) may add its own: the
# commands put them in AGENT_FABRIC_LEGACY_REVIEW_MARKERS, one per line. The project's name never
# appears here — the fabric's lint refuses it in a generic file. The
# built-in one goes when no open PR anywhere carries a review posted before
# 2026-09-20 (docs/adr/ADR-020-the-review-class-is-the-review.md §5 rule 8).
BUILTIN_LEGACY_MARKER = "<!-- agent-fabric-substitute-review v1 -->"


TRUSTED_ASSOCIATIONS = ("OWNER", "MEMBER", "COLLABORATOR")


# ── configuration ───────────────────────────────────────────────────────

POSIX_CLASSES = {
    "alpha": "a-zA-Z", "digit": "0-9", "alnum": "0-9a-zA-Z", "upper": "A-Z", "lower": "a-z",
    "space": " \\t\\n\\r\\f\\v", "blank": " \\t", "punct": "!-/:-@\\[-`{-~", "xdigit": "0-9A-Fa-f",
    "word": "\\w", "cntrl": "\\x00-\\x1f\\x7f", "print": " -~", "graph": "!-~",
}


def onig_to_py(pattern: str) -> str:
    """jq's regex engine is Oniguruma and this is Python's `re`: what a
    reviewer's wording needs is the same in both except two spellings the
    bash's own suite and its projects use — POSIX bracket classes
    (`[[:space:]]`) and named groups (`(?<n>...)`)."""
    res, i, in_set = [], 0, False
    while i < len(pattern):
        c = pattern[i]
        if c == "\\" and i + 1 < len(pattern):
            res.append(pattern[i:i + 2])
            i += 2
            continue
        if in_set:
            m = re.match(r"\[:(\w+):\]", pattern[i:])
            if m and m.group(1) in POSIX_CLASSES:
                res.append(POSIX_CLASSES[m.group(1)])
                i += m.end()
                continue
            if c == "]":
                in_set = False
        elif c == "[":
            in_set = True
            res.append(c)
            i += 1
            if pattern[i:i + 1] == "^":
                res.append("^")
                i += 1
            if pattern[i:i + 1] == "]":
                res.append("\\]")
                i += 1
            continue
        elif pattern.startswith("(?<", i) and pattern[i + 3:i + 4] not in ("=", "!"):
            res.append("(?P<")
            i += 3
            continue
        res.append(c)
        i += 1
    return "".join(res)


def compile_re(pattern: str) -> re.Pattern:
    """Compiled with the same "i" flag the consumers use, so what passes
    validation is exactly what runs."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return re.compile(onig_to_py(pattern), re.IGNORECASE)


def logins(raw: str, name: str) -> list[str]:
    try:
        v = json.loads(raw)
    except ValueError:
        v = None
    if not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
        raise Die(f"{name} must be a JSON array of logins, got '{raw}'.")
    return v


@dataclass
class Config:
    verdict_authors: list[str]
    review_posters: list[str]
    refusal_re: re.Pattern | None
    request_re: re.Pattern | None
    markers: list[str]


def read_config(env) -> Config:
    """A CONFIGURED value that cannot be applied fails HERE, not silently
    below. Every read over these falls back to "none" on a failure, so a
    list that is not JSON, or a pattern the engine rejects, would read as no
    verdicts, no decline, no ask — and the no-ask reading turns a pending
    request into a confident "NO REVIEW COMING" (exit 5), the wrong answer
    this script exists to avoid. Exit 2 is the invocation-problem code; a
    bad configuration is one.

    AN AUTOMATED REVIEWER, if a project runs one — none by default.
    Accounts whose verdict COMMENT counts as a review of the sha it names:
    a LIST, because the alternative is a negation and a negation lets
    anybody in ("not the PR author" is right for a review OBJECT, which
    only a reviewer can create, and wrong for a comment, which anyone with
    access may leave). Empty means no comment is ever a verdict. Who may
    post a blind review, besides the PR author: a JSON array of logins.
    Empty by default, because every session pushes AND posts as one
    account, which is the author of every PR a session opens. The
    reviewer's own refusal wording (a regex over the comment body) and the
    phrase a request for it takes; both empty by default, so nothing reads
    as a decline and nothing as a pending request. A request never marks a
    head reviewed — it can only turn "nothing is coming" into "not yet" —
    which is why it needs no allow-list."""
    verdict = logins(env.get("AGENT_FABRIC_VERDICT_AUTHORS") or "[]", "AGENT_FABRIC_VERDICT_AUTHORS")
    posters = logins(env.get("AGENT_FABRIC_REVIEW_POSTERS") or "[]", "AGENT_FABRIC_REVIEW_POSTERS")
    compiled = {}
    for name in ("REVIEWER_REFUSAL_RE", "REVIEW_REQUEST_RE"):
        raw = env.get(f"AGENT_FABRIC_{name}") or ""
        compiled[name] = None
        if raw:
            try:
                compiled[name] = compile_re(raw)
            except re.error:
                raise Die(f"AGENT_FABRIC_{name} is not a regex jq accepts: '{raw}'.") from None
    legacy = [BUILTIN_LEGACY_MARKER, *(env.get("AGENT_FABRIC_LEGACY_REVIEW_MARKERS") or "").split("\n")]
    markers = [m for m in [REVIEW_MARKER, *legacy] if m]
    return Config(verdict, posters, compiled["REVIEWER_REFUSAL_RE"], compiled["REVIEW_REQUEST_RE"], markers)
