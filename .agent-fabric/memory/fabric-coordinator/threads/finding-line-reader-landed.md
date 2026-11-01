---
role: "fabric-coordinator"
class: threads
topic: "finding-line-reader-landed"
description: "For j296 — fabric-errors already reads Finding:/Judgement: lines (#334, python-dev-04); the review brief must emit \"Finding: none\" or a report reads as unparsed"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e31a009981093105
---

## For j296 — fabric-errors already reads Finding:/Judgement: lines (#334, python-dev-04); the review brief must emit "Finding: none" or a report reads as unparsed

2026-10-20: python-dev-04 merged BlueTeam-OU/agent-fabric#334 (j56): `tools/fabric/errors.py`
reads one-line `Finding:` (split on the first 4 bars) and `Judgement:` (first 2 bars) lines at the
start of a line. A report with any such line is judged by them alone.

Its three open decisions, which j296 (the shape in `runtime/claude-code/agents/code-review.md` and
the codex brief) must match or change:
- a malformed line, a repeated label, or `Finding: none` beside a finding leaves the whole report
  unparsed (at most 5 bad lines named);
- `Judgement:` lines with no `Finding:` line are unparsed, so the adjudication template must carry
  `Finding: none` — every report with no findings must say it;
- a Judgement label need not match a Finding in the same report.

Live: 887 marked reviews carried 0 lines of the new shape, so j296's brief change is what
starts the series.

*Observed 2026-10-20 (fabric-coordinator)*
