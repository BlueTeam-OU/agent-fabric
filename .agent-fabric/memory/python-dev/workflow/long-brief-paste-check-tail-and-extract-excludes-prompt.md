---
role: "python-dev"
class: workflow
topic: "long-brief-paste-check-tail-and-extract-excludes-prompt"
description: "j107 #546 - a 35 KB re-review brief pasted by hand lost its diff tail; the extractor's longest-string match returned the prompt, not the report"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d3c16f5ba37cb400
---

## j107 #546 - a 35 KB re-review brief pasted by hand lost its diff tail; the extractor's longest-string match returned the prompt, not the report

Pasting a long rendered re-review brief into the Agent prompt, I abbreviated the diff's last hunks
(a placeholder line in place of the real tail) and sent it. I caught it only on re-reading my own
prompt; stopped the agent (TaskStop) and redispatched the whole text.

**Why:** the reviewer reads the brief's diff as the facts of the fix range; a cut hunk is the one
it would have judged (here, the lint fix for F1). See [[rereview-brief-retyped-by-hand-drifts]].

**How to apply:** after writing the Agent prompt, compare its last 15 lines with the tail of the
rendered brief file before sending; never summarise a hunk. When extracting the report from the
subagent JSONL, the longest string starting with the dispatch header is the *prompt*, which carries
the report's earlier text too: keep only strings that hold `Judgement: F1 |` (or `Finding:`) and
do not hold `## Previous findings`. See [[review-report-extract-walk-json-strings]].

*References: rereview-brief-retyped-by-hand-drifts, review-report-extract-walk-json-strings*

*Observed 2026-11-10 (python-dev)*
