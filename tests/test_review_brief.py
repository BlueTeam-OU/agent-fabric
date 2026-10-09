#!/usr/bin/env python3
"""tests/test_review_brief.py — the review constitution and the brief.

The reviewer's whole system prompt is runtime/claude-code/agents/
code-review.md, paid on every dispatch; the brief is what the dispatcher
puts in `prompt`. What holds still here: the agent file's frontmatter
(the pin rewrite, the tools allow-list, the Bash fence) is exactly what
the guards and install-agent-files.sh expect; the body stays under its
size cap and carries every section the design names; and the brief's
headings, once there is a renderer, are the ones the constitution says
it reads.
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
AGENT = os.path.join(ROOT, "runtime", "claude-code", "agents", "code-review.md")
SIZE_CAP = 13_000   # 12_288 until 2026-09-19: the owner's code-as-memory policy gave the reviewer one more section (agent-fabric ADR-015 §5 rule 7)

# The headings a rendered brief carries; the constitution names each.
BRIEF_HEADINGS = ["Mode", "Repository", "Range", "Objective", "Requirements", "Invariants",
                  "Compatibility", "Threat model", "Scope", "Out of scope", "Lenses", "Previous findings"]
# The report sections the constitution requires, in order.
REPORT_SECTIONS = ["Findings on the change", "Pre-existing problems", "Risks (unproven)", "Brief notes"]


def read_agent() -> tuple[str, str]:
    text = open(AGENT, encoding="utf-8").read()
    assert text.startswith("---\n"), "no frontmatter"
    end = text.index("\n---\n", 4)
    return text[4:end], text[end + 5:]


def test_frontmatter_is_what_the_guards_and_installer_expect() -> None:
    front, _ = read_agent()
    lines = front.split("\n")
    assert lines[0] == "name: code-review", lines[0]
    # install-agent-files.sh rewrites the FIRST `model:` line; the guard reads the same one.
    assert lines[2] == "model: fable", "model: fable must be the third frontmatter line (the pin rewrite hits the first model: line)"
    assert "tools: Read, Glob, Grep, Bash" in front, "the tools allow-list is the write fence"
    assert "Write" not in front.split("tools:")[1].split("\n")[0]
    assert "review-bash-guard.sh" in front and "permissionDecision" in front, "the Bash fence hook must stay in the frontmatter"
    assert re.search(r"\nmodel: ", front.split("model: fable", 1)[1]) is None, "one model: line only"


def test_body_is_under_the_cap_and_carries_every_section() -> None:
    _, body = read_agent()
    size = os.path.getsize(AGENT)
    assert size <= SIZE_CAP, f"code-review.md is {size} bytes; the cap is {SIZE_CAP} (every byte is paid on every dispatch)"
    for h in ("# Code review: the blind reviewer", "## What you are given", "## Method", "## Git: read history, change nothing",
              "## What has shipped here", "## A finding", "## Report format", "## What happens to your findings"):
        assert h in body, f"section missing: {h}"
    for section in REPORT_SECTIONS:
        assert section in body, f"report section missing: {section}"
    for heading in BRIEF_HEADINGS:
        assert heading in body, f"the constitution does not name the brief heading {heading!r}"


def test_the_incident_rules_are_still_there() -> None:
    """Each of these was bought by an incident; a rewrite may not lose one."""
    _, body = read_agent()
    for rule in ("revert test", "Quote the hunk", "in full", "One PR per dispatch", "re-review", "verify ONLY",
                 "fifty thousand tokens", "git log", "Change nothing", "--no-restore", "Never `pub\nget`",
                 "single-line mutation", "P1", "P2", "P3", "Do not pad", "six weeks from now",
                 "Feature flags that are not rollbacks", "Silent-drop", "CHECK clauses"):
        assert rule in body, f"rule lost in the rewrite: {rule!r}"


def test_the_new_rules_are_stated_once() -> None:
    _, body = read_agent()
    assert "verdict rule" in body.lower() and "Brief notes" in body
    assert "negative space" in body.lower()
    assert body.count("**Trigger**") == 1 and "**Evidence**" in body
    assert "**confirmed**" in body and "**likely**" in body and "Nothing below likely is a finding" in body
    assert "Zero findings is a\nvalid report" in body or "Zero findings is a valid report" in body


# --- the renderer -----------------------------------------------------------
import importlib.util
import subprocess
import tempfile

spec = importlib.util.spec_from_file_location("fabric_review_brief", os.path.join(ROOT, "tools", "fabric", "review_brief.py"))
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
BIN = os.path.join(ROOT, "bin", "fabric-review")


def base_request(repo: str) -> dict:
    return {"mode": "review", "repository": repo, "range": "main..HEAD",
            "objective": "An itinerary's times are the engine's.",
            "requirements": ["A malformed engine response is an error, never an empty itinerary."],
            "invariants": ["Nothing under apps/passenger/ interprets a time zone."],
            "lenses": ["protocol"]}


def refusals(req: dict, **kw) -> list[str]:
    try:
        rb.render(req, **kw)
    except rb.RequestError as exc:
        return exc.problems
    return []


def test_render_carries_every_heading_once_and_the_named_lenses(tmp: str) -> None:
    repo = os.path.join(tmp, "repo"); os.makedirs(os.path.join(repo, ".git"))
    out = rb.render(base_request(repo))
    for h in BRIEF_HEADINGS:
        if h == "Previous findings":
            assert f"## {h}" not in out, "a review carries no previous findings"
        else:
            assert out.count(f"\n## {h}\n") == 1, f"heading {h} not exactly once:\n{out}"
    assert out.startswith("# Review brief (agent-fabric review brief v1)\n## Mode\nreview\n")
    assert "### general\n" in out and "### protocol\n" in out, "general is always on; the named lens is inlined"
    assert rb.lenses()["protocol"]["body"] in out, "the lens body is inlined, not referenced"
    assert "## Threat model\n(none stated)\n" in out, "an empty field is rendered as absent, never dropped"
    assert "model:" not in out, "a brief carries no routing configuration"
    assert out == rb.render(base_request(repo)), "not byte-stable"
    assert "## Brief notes" not in out, "no flagged rationale when there is none"


def test_every_refusal_names_its_field(tmp: str) -> None:
    repo = os.path.join(tmp, "repo2"); os.makedirs(os.path.join(repo, ".git"))
    ok = base_request(repo)
    assert refusals(ok) == [], refusals(ok)
    cases = {
        "mode": ({**ok, "mode": "audit"}, "mode: 'audit'"),
        "unknown key": ({**ok, "invariant": ["x"]}, "invariant: not a request field (did you mean invariants?)"),
        "both range and diff": ({**ok, "diff": os.path.join(tmp, "x.diff")}, "range / diff: exactly one"),
        "neither range nor diff": ({k: v for k, v in ok.items() if k != "range"}, "range / diff: exactly one"),
        "bad range": ({**ok, "range": "main HEAD"}, "range: 'main HEAD' is not base..head"),
        "range with a trailing newline": ({**ok, "range": "main..HEAD\n"}, "is not base..head"),
        "lens with a trailing newline": ({**ok, "lenses": ["general\n"]}, "is not a lens name"),
        "no repository": ({k: v for k, v in ok.items() if k != "repository"}, "repository: required"),
        "not a working copy": ({**ok, "repository": tmp}, "is not a git working copy"),
        "unknown lens": ({**ok, "lenses": ["general", "vibes"]}, "lenses: 'vibes' is not a lens"),
        "objective missing": ({k: v for k, v in ok.items() if k != "objective"}, "objective: required on a review"),
        "previous findings on a review": ({**ok, "previous_findings": "/nope"}, "previous_findings: only on a re-review"),
        "re-review without previous findings": ({**ok, "mode": "re-review"}, "previous_findings: required on a re-review"),
        "list where a value is due": ({**ok, "objective": ["a", "b"]}, "objective: must be one value"),
        "value where a list is due": ({**ok, "requirements": "one"}, "requirements: must be a list"),
    }
    for label, (req, needle) in cases.items():
        probs = refusals(req)
        assert any(needle in p for p in probs), f"{label}: expected {needle!r} in {probs}"


def test_the_rationale_lint_refuses_verdicts_and_passes_facts(tmp: str) -> None:
    repo = os.path.join(tmp, "repo3"); os.makedirs(os.path.join(repo, ".git"))
    ok = base_request(repo)
    verdicts = ["The executor correctly abstracts the host.", "This fixes the PATH bug.", "The worker ensures the token never leaks.",
                "The change is safe.", "The bug was a missing lock.", "I think the dangerous part is the retry.",
                "We suspect the merge path.", "The change adds a transport abstraction.",
                "Retries are bounded. Because the caller loops.", "It should be fine now."]
    for v in verdicts:
        probs = refusals({**ok, "objective": v})
        assert any("objective:" in p and "state what must be true" in p for p in probs), f"verdict passed: {v!r} -> {probs}"
        probs = refusals({**ok, "requirements": [v]})
        assert any(p.startswith("requirements:") for p in probs), f"verdict in a list passed: {v!r}"
    facts = ["A secret never appears in argv.", "Same-host behaviour must remain supported.", "Contracts 1.1.0 clients keep working.",
             "The coordinator and the agent may be on different hosts.", "A malformed reply is an error, never an empty result.",
             "Nothing under apps/ interprets a time zone because-of-clock is not a word here"]
    for f in facts:
        assert refusals({**ok, "objective": f}) == [], f"a fact was refused: {f!r}"
    # --allow-rationale renders, flagged under Brief notes
    out = rb.render({**ok, "objective": "This fixes the PATH bug."}, allow_rationale=True)
    assert "## Brief notes (dispatcher-asserted, not facts)" in out and "- objective: This fixes the PATH bug." in out


def test_re_review_inlines_the_previous_report_and_names_the_new_range(tmp: str) -> None:
    repo = os.path.join(tmp, "repo4"); os.makedirs(os.path.join(repo, ".git"))
    prev = os.path.join(tmp, "findings.md")
    open(prev, "w").write("## Findings on the change\n1. P2 likely — apps/x.py:10 ...\n```\n+hunk\n```\nafter the hunk\n")
    req = {"mode": "re-review", "repository": repo, "range": "3f2c1a0..9b7e44d", "previous_findings": prev}
    out = rb.render(req)
    assert "## Mode\nre-review\n" in out and "## Range\n3f2c1a0..9b7e44d\n" in out
    assert "## Previous findings\n" in out and "1. P2 likely — apps/x.py:10" in out, "the previous report is inlined verbatim"
    assert "answering each by number" in out
    assert "## Objective\n(none stated)" in out, "a re-review needs no objective"
    assert out.count("### ") == 0 and "(none named" in out, "a re-review carries no lens it did not name, general included"
    out = rb.render({**req, "lenses": ["security"]})
    assert out.count("### ") == 1 and "### security\n" in out, "a named lens is inlined on a re-review; general is not added"
    # 11: the inlined report is fenced, so its headings do not read as the brief's
    # re-review finding B: the fence is longer than any backtick run in the report, so a quoted hunk does not close it
    assert "## Previous findings\nVerify only the hunks of the range above against these, answering each by number.\n````markdown\n## Findings on the change\n1. P2 likely" in out
    assert out.count("\n## Findings on the change") == 1 and "\nafter the hunk\n````\n## Lenses" in out


def test_the_yaml_subset_and_the_cli(tmp: str) -> None:
    repo = os.path.join(tmp, "repo5"); os.makedirs(os.path.join(repo, ".git"))
    req = os.path.join(tmp, "req.yaml")
    open(req, "w").write(f"""# comment
mode: review   # a trailing comment
repository: {repo}
range: main..HEAD
objective: >-
  An itinerary's times are
  the engine's.
requirements:
  - "A malformed engine response is an error."
  - Plain item
compatibility: [ "Contracts 1.1.0 clients keep working, PR #746", 'quoted' ]
threat_model: []
lenses: [protocol, security]
""")
    doc = rb.parse_request(open(req).read())
    assert doc["objective"] == "An itinerary's times are the engine's." and doc["requirements"] == ["A malformed engine response is an error.", "Plain item"]
    assert doc["mode"] == "review", "a trailing comment is not part of the value"
    assert doc["compatibility"] == ["Contracts 1.1.0 clients keep working, PR #746", "quoted"], "a # inside a quoted string is text (a PR number)"
    assert doc["threat_model"] == [], "an empty inline list is empty"
    assert doc["lenses"] == ["protocol", "security"], "an inline list keeps its order"
    r = subprocess.run([BIN, "check", req], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.startswith("ok: review of main..HEAD"), r.stdout + r.stderr
    r = subprocess.run([BIN, "brief", req], capture_output=True, text=True)
    assert r.returncode == 0 and "### security" in r.stdout and "### protocol" in r.stdout, r.stderr
    open(req, "a").write("invariant: [x]\n")
    r = subprocess.run([BIN, "brief", req], capture_output=True, text=True)
    assert r.returncode == 2 and "invariant: not a request field (did you mean invariants?)" in r.stderr, r.stderr
    assert r.stdout == "", "a refused request renders nothing"
    r = subprocess.run([BIN, "lenses"], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.startswith("cleanup") and "general" in r.stdout
    # JSON is accepted as is
    r = subprocess.run([BIN, "check", "-"], input=json.dumps({"mode": "review", "repository": repo, "range": "a..b", "objective": "x must hold"}),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_the_parser_refuses_what_it_cannot_keep(tmp: str) -> None:
    """Findings of the first live review (2b61473): a block line kept its
    comment and its quotes; an apostrophe opened a quote; a duplicate key,
    an empty block and a block indicator with trailing text were silent."""
    parse = rb.parse_request
    # 1: a comment on a `- item` line, and a comment line inside a folded scalar
    doc = parse('requirements:\n  - "fix #12 is out"  # c\n  - plain # trailing\nobjective: >-\n  the PR (#746)\n  # a note to self\n  more\n')
    assert doc["requirements"] == ["fix #12 is out", "plain"], doc
    assert doc["objective"] == "the PR (#746) more", doc
    # 2: an apostrophe inside a plain value is text, a quote opens only at a value's start
    doc = parse("objective: The engine's clock is authoritative # ADR-58\nlenses: [it's late, \"b, c\"]\n")
    assert doc["objective"] == "The engine's clock is authoritative", doc
    assert doc["lenses"] == ["it's late", "b, c"], doc
    doc = parse("requirements:\n  - The engine's clock # note\n")
    assert doc["requirements"] == ["The engine's clock"], doc
    # re-review finding A: a quoted # in any item of an inline list is text, whatever its position
    assert parse('compatibility: ["fix #746", x]\n')["compatibility"] == ["fix #746", "x"]
    assert parse('compatibility: [x, "fix #746"] # c\n')["compatibility"] == ["x", "fix #746"]
    assert parse("compatibility: [x, 'it #1', \"a, b\"]\n")["compatibility"] == ["x", "it #1", "a, b"]
    def refused(text: str) -> str:
        try:
            parse(text)
        except rb.RequestError as exc:
            return " | ".join(exc.problems)
        raise AssertionError(f"parsed silently: {text!r}")
    assert "unterminated ' quote" in refused("lenses: [it's, 'open]\n")
    # 3: a key given twice loses a value; refused in both syntaxes
    assert "line 2: mode: given twice" in refused("mode: review\nmode: re-review\n")
    assert "mode: given twice" in refused('{"mode": "review", "mode": "re-review"}')
    # 4: an empty block is the empty value of its shape
    doc = parse("objective:\nrequirements:\n\nlenses: []\n")
    assert doc == {"objective": "", "requirements": [], "lenses": []}, doc
    # 5: a block indicator with text on its line would have rendered nothing
    assert "objective: a block indicator (>) takes no text on its line" in refused("objective: > 3 retries is an error\n")
    assert "block indicator (|-)" in refused("objective: |- x\n")
    # 7: a # glued to its word is text, in a plain item and inside a folded
    # scalar — YAML would cut there, and the brief lost both silently
    # (backend-dev-01, 2026-09-25); a free-standing "# " is still a comment
    doc = parse("objective: >-\n  onto PR #934 (which adds AnalysisMode=All and the rule that\n  findings are never silenced)\n"
                "requirements:\n  - No #pragma, [SuppressMessage] or .editorconfig change is introduced.\n  - kept # dropped\n")
    assert doc["objective"] == "onto PR #934 (which adds AnalysisMode=All and the rule that findings are never silenced)", doc
    assert doc["requirements"] == ["No #pragma, [SuppressMessage] or .editorconfig change is introduced.", "kept"], doc
    # 8: a CRLF request: a CR after a free-standing # is the line's end (re-review of #37)
    doc = parse("objective: keep PR #\r\nrange: a..b\r\nrequirements:\r\n  - PR #934\r\n")
    assert doc["objective"] == "keep PR" and doc["range"] == "a..b", doc
    assert doc["requirements"] == ["PR #934"], doc
    # 6: the front door: no argument is a usage error, --help is not
    r = subprocess.run([BIN], capture_output=True, text=True)
    assert r.returncode == 2 and "numeric argument" not in r.stderr and "fabric-review brief" in r.stderr, r.stderr
    r = subprocess.run([BIN, "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "fabric-review brief" in r.stdout, r.stderr


def test_the_readme_example_renders_as_documented(tmp: str) -> None:
    """The README shows a request and its rendered head; both are the
    renderer's output, so the README cannot drift from the tool."""
    readme = open(os.path.join(ROOT, "runtime", "claude-code", "review", "README.md"), encoding="utf-8").read()
    m = re.search(r"```yaml\n(.*?)```", readme, re.S)
    assert m, "the README carries no yaml example"
    repo = os.path.join(tmp, "readme"); os.makedirs(os.path.join(repo, ".git"))
    req = rb.parse_request(m.group(1).replace("/home/user/projects/gzapp", repo))
    out = rb.render(req)
    head = re.search(r"```markdown\n(.*?)```", readme, re.S)
    assert head, "the README carries no rendered example"
    expected = head.group(1).replace("/home/user/projects/gzapp", repo)
    assert out.startswith(expected.split("## Lenses")[0]), "the README's rendered example differs from the renderer's output"


def main() -> int:
    cases = [test_frontmatter_is_what_the_guards_and_installer_expect, test_body_is_under_the_cap_and_carries_every_section,
             test_the_incident_rules_are_still_there, test_the_new_rules_are_stated_once,
             test_render_carries_every_heading_once_and_the_named_lenses, test_every_refusal_names_its_field,
             test_the_rationale_lint_refuses_verdicts_and_passes_facts, test_re_review_inlines_the_previous_report_and_names_the_new_range,
             test_the_yaml_subset_and_the_cli, test_the_parser_refuses_what_it_cannot_keep,
             test_the_readme_example_renders_as_documented]
    failures = 0
    # Removed when the run ends, however it ends: tests/run.sh names every
    # entry a run leaves under the temporary directory as a failure.
    with tempfile.TemporaryDirectory() as tmp:
        for case in cases:
            try:
                case(tmp) if case.__code__.co_argcount else case()
                print(f"  ok   {case.__name__}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL {case.__name__}: {exc}")
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
