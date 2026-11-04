#!/usr/bin/env python3
"""tools/fabric/review_lines.py — the one definition of the machine lines a review report carries.

errors.py reads them (`Finding:` and `Judgement:`, ADR-061), the review brief tells a Claude reviewer
to write them, the codex body renders them from its structured answer, and the review class's agent
file (runtime/claude-code/agents/code-review.md) quotes them. The vocabularies and the shapes live
here so none of the four can drift from the others; tests/test_review_lines.py holds the agent file
and the parser to this module. Pure text: no I/O, so errors.py (which reads GitHub) and the brief
renderer can both import it.
"""
from __future__ import annotations

CONFIDENCES = ("certain", "likely", "possible")
VERDICTS = ("real", "not-real", "partly", "fixed", "not-fixed")

FINDING_SHAPE = "Finding: F<n> | P<1-3> | certain|likely|possible | <path>[:<line>] or - | <summary>"
JUDGEMENT_SHAPE = "Judgement: F<n> | real|not-real|partly|fixed|not-fixed | <reason>"
NO_FINDINGS = "Finding: none"

_PLACE = "each at the start of its own line (no list marker, no quote, no fence)"

# errors.py counts every Finding line as an error of the change's author, so only a finding ON THE CHANGE
# gets one; a pre-existing problem or a risk is prose in its own section and has no line.
_RULES = {
    "review": [
        f"End the report with one block of machine lines, {_PLACE}: one `Finding:` per numbered finding on the "
        f"change, none for a pre-existing problem or a risk: `{FINDING_SHAPE}`.",
        "F<n> is the finding's number in section 1; a confirmed finding is `certain`; the summary is one line "
        "and the path has no space.",
        f"No findings on the change: the single line `{NO_FINDINGS}`.",
    ],
    "re-review": [
        f"End the report with one block of machine lines, {_PLACE}: one `Judgement:` per previous finding, by "
        f"its number: `{JUDGEMENT_SHAPE}`.",
        f"A finding the fix range itself introduces also gets a `Finding:` line (`{FINDING_SHAPE}`) under a "
        f"number the previous report did not use; with none, the single line `{NO_FINDINGS}`, which a "
        "judgement report still carries.",
    ],
    "finding-adjudication": [
        f"End the report with one block of machine lines, {_PLACE}: one `Judgement:` per finding judged, by "
        f"its number: `{JUDGEMENT_SHAPE}`.",
        f"Raise no new finding: the single line `{NO_FINDINGS}` follows, which a judgement report still carries.",
    ],
}


def report_rules(mode: str) -> list[str]:
    """The brief's text on the machine lines for a mode (review, re-review, finding-adjudication)."""
    return list(_RULES[mode])


def finding_line(label: str, level: str, confidence: str, path: str, summary: str, line: int | None = None) -> str:
    """One `Finding:` line. The reader takes a path with no whitespace or `|` and the summary on one line, so
    any other path is given as `-` with the path moved into the summary."""
    text = " ".join(summary.split())
    where = path if line is None else f"{path}:{line}"
    if not path or any(c.isspace() or c == "|" for c in path):
        where, text = "-", f"{where}: {text}"
    return f"Finding: {label} | {level} | {confidence} | {where} | {text}"


def judgement_line(label: str, verdict: str, reason: str) -> str:
    return f"Judgement: {label} | {verdict} | {' '.join(reason.split())}"
