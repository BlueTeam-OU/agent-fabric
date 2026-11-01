---
role: "python-dev"
class: workflow
topic: "review-report-extract-walk-json-strings"
description: "Extracting a code-review subagent's report from its tasks/<id>.output JSONL for fabric-pr post-review: walk every JSON string, not message.content"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 00437f4d9283eb33
---

## Extracting a code-review subagent's report from its tasks/<id>.output JSONL for fabric-pr post-review: walk every JSON string, not message.content

The subagent output file's lines do not have the assistant-message shape I assumed (`message.role/content` gave None).
Walk every string in every JSON line and keep those that start with "```agent-fabric-dispatch v1" and end with the
`Finding:` line (two copies, same length); the system prompt also contains "Finding: none", so match the start too.
Post with `fabric-pr post-review N --model fable --head <full sha> < file`. j77 / #440 posted this way, accepted.

**Why:** a retyped report is refused; verbatim extraction is the sanctioned route (see [[review-report-post-extract-from-transcript]]).
**How to apply:** the first match on "Finding: none" alone returns the reviewer's own constitution, not the report.
Also: `tests/test_review_codex.py` takes about 2 minutes, so run it with run_in_background from the start.

*References: review-report-post-extract-from-transcript*

*Observed 2026-10-31 (python-dev)*
