#!/usr/bin/env python3
"""tests/test_review_lines.py — the machine lines a review report carries (j296), tested the way the reader
reads them: the text each writer produces goes through errors.py's parser, so a writer and the reader cannot
drift (the data and its reader together). Writers: the examples in the review class's agent file, the
brief's rules for a mode, and the posted body review_codex.render_review builds from Codex's answer.
Plain script: ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from instance_fixtures import own_instance_tree  # noqa: E402

own_instance_tree()

import errors  # noqa: E402
import review_brief  # noqa: E402
import review_codex  # noqa: E402
import review_lines  # noqa: E402
import test_review_brief as trb  # noqa: E402

AGENT = os.path.join(ROOT, "runtime", "claude-code", "agents", "code-review.md")


def machine_examples() -> list[str]:
    """The ```text blocks under the agent file's Machine lines paragraph, in order."""
    text = open(AGENT, encoding="utf-8").read()
    section = text[text.index("**Machine lines.**"):text.index("## What happens to your findings")]
    return re.findall(r"```text\n(.*?)\n```", section, re.S)


def test_the_agent_files_examples_parse() -> None:
    review, judged = machine_examples()
    got = errors.read_review(review)
    assert not got.unparsed and got.findings == [("F1", "P2"), ("F2", "P3")], (got, review)
    got = errors.read_review(judged)
    assert not got.unparsed and got.findings == [] and [(l, v) for l, v, _ in got.judgements] == [
        ("F1", "fixed"), ("F2", "not-real")], (got, judged)


def test_the_agent_file_states_the_shared_vocabulary() -> None:
    text = " ".join(open(AGENT, encoding="utf-8").read().split())
    assert f"Verdicts: {', '.join(review_lines.VERDICTS)}." in text, "the verdicts differ from review_lines.VERDICTS"
    assert f"`{review_lines.NO_FINDINGS}`" in text
    assert "## Report lines" not in text, "the heading is the brief's; the constitution names it, it does not render it"
    for c in review_lines.CONFIDENCES[:1]:
        assert f"`{c}` is confirmed" in text, "the constitution's confirmed maps to certain"


def test_the_grammar_text_and_the_reader_agree(tmp: str) -> None:
    assert errors.CONFIDENCES == set(review_lines.CONFIDENCES) and errors.VERDICTS == set(review_lines.VERDICTS)
    for c in review_lines.CONFIDENCES:
        assert errors.read_review(review_lines.finding_line("F1", "P1", c, "a.py", "s", 3)).findings == [("F1", "P1")]
    for v in review_lines.VERDICTS:
        body = review_lines.NO_FINDINGS + "\n" + review_lines.judgement_line("F1", v, "r")
        assert [x[1] for x in errors.read_review(body).judgements] == [v]
    assert review_lines.FINDING_SHAPE.startswith("Finding: F<n> | P<1-3> | " + "|".join(review_lines.CONFIDENCES))
    assert review_lines.JUDGEMENT_SHAPE.endswith("|".join(review_lines.VERDICTS) + " | <reason>")


def test_the_brief_states_the_lines_for_each_mode(tmp: str) -> None:
    repo = trb.mkrepo(tmp, "lines")
    prev = os.path.join(tmp, "lines-previous.md")
    open(prev, "w").write("## Findings on the change\n1. P2 likely: a.txt:1 ...\n")
    review = review_brief.render(trb.base_request(repo))
    judge = review_brief.render({**trb.base_request(repo), "mode": "finding-adjudication", "previous_findings": prev})
    assert review.count("\n## Report lines\n") == 1 and judge.count("\n## Report lines\n") == 1
    for mode, out in (("review", review), ("finding-adjudication", judge)):
        assert out.endswith("## Report lines\n" + "\n".join(review_lines.report_rules(mode)) + "\n"), (mode, out[-600:])
    assert review_lines.FINDING_SHAPE in review and review_lines.JUDGEMENT_SHAPE in judge
    assert review_lines.JUDGEMENT_SHAPE in "\n".join(review_lines.report_rules("re-review"))
    assert "## Report lines" not in review_brief.render(trb.base_request(repo), engine="codex"), "codex's body is rendered, not asked for"


def test_the_codex_body_carries_lines_the_reader_parses() -> None:
    base = {"file": "a/b.py", "line": 4, "scenario": "s", "expected": "e", "fix": "f"}
    body = review_codex.render_review("gpt-x", "a" * 40, "b..c", [
        {**base, "level": "P3", "scenario": "two\nlines | with a bar"}, {**base, "level": "P1", "file": "dir with space/x.py"},
        {**base, "level": "P2"}])
    got = errors.read_review(body)
    assert not got.unparsed and got.findings == [("F1", "P1"), ("F2", "P2"), ("F3", "P3")], (got, body)
    assert "Finding: F1 | P1 | likely | - | dir with space/x.py:4: s" in body, body
    assert "Finding: F3 | P3 | likely | a/b.py:4 | two lines | with a bar" in body, body
    clean = errors.read_review(review_codex.render_review("gpt-x", "a" * 40, "b..c", []))
    assert not clean.unparsed and clean.findings == [] and not clean.malformed, clean


CASES = [test_the_agent_files_examples_parse, test_the_agent_file_states_the_shared_vocabulary,
         test_the_grammar_text_and_the_reader_agree, test_the_brief_states_the_lines_for_each_mode,
         test_the_codex_body_carries_lines_the_reader_parses]


def main() -> int:
    failures = 0
    # Removed when the run ends, however it ends: tests/run.sh names every entry a run leaves as a failure.
    with tempfile.TemporaryDirectory() as tmp:
        for case in CASES:
            try:
                case(tmp) if case.__code__.co_argcount else case()
                print(f"  ok   {case.__name__}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL {case.__name__}: {exc}")
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
