---
role: "fabric-coordinator"
class: workflow
topic: "review-report-from-handback"
description: "Saving a code-review subagent's report for fabric-review save / post-review — where the text is in its transcript"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 03f0f1354c88fca9
---

## Saving a code-review subagent's report for fabric-review save / post-review — where the text is in its transcript

A code-review subagent's final report arrives as a SubagentHandback tool_use, not as an assistant text block: a script reading the task's .output JSONL for the last assistant *text* finds nothing (2026-10-30, #425 round 2). Take the string input of the tool_use that holds both `agent-fabric-dispatch v1` and `Judgement:` (or `Finding:`), write it to the scratchpad, then `fabric-review save PR ROUND < f` and `fabric-pr post-review PR < f`.

**Why:** retyping the report by hand risks changing the header that post-review checks (head_sha, coverage block).
**How to apply:** compute it with a short python over the JSONL; never Read the .output file into context. See [[post-review-run-bare]].

*References: post-review-run-bare*

*Anchors: `tools/fabric/review_brief.py::agent-fabric-dispatch v1`*

*Observed 2026-10-30 (fabric-coordinator)*
