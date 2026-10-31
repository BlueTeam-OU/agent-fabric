---
role: "fabric-coordinator"
class: workflow
topic: "subagent-model-audit"
description: "Audit what subagents actually ran on from their transcripts, never trust routing config; 2026-10-10 in my UNLAUNCHED session 32 review dispatches with model fable ran on claude-fable-5-1, not the agent file's Opus 5.5 pin (the…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5cc8b9b51ec81b35
---

## Audit what subagents actually ran on from their transcripts, never trust routing config; 2026-10-10 in my UNLAUNCHED session 32 review dispatches with model fable ran on claude-fable-5-1, not the agent file's Opus 5.5 pin (the per-invocation model wins; the guard drops it only under a fabric launch)

2026-10-10, after the owner pointed at
https://blog.yasaswy.nagavolu.com/claude-subagent-model-routing/ ("a subagent with no model of its
own inherits the main chat's model; nothing errors"; a rule is trusted only once something
records that it ran). Counting my session's subagent transcripts (subagents/agent-*.jsonl, the
assistant messages' `model`): 113 runs, 39 sonnet-5-5 (113M tokens incl. cache), 37 opus-5-5
(219M), 32 fable-5-1 (60M), 5 haiku-5-5 (29M). fabric-status said code-review resolves to
Opus 5.5 "from the agent file", yet the reviews ran on Fable 5.1: my session is vanilla claude,
not launched by the fabric, so the dispatch guard does not drop the per-invocation `model:
fable`, and Claude Code's native order puts the invocation's model above the frontmatter.

**Why:** routing config describes intent; only the transcript says what ran, and the cost and
the review grade follow what ran.

**How to apply:** coordinate from a fabric-launched session (`fabric-fresh`), or omit `model`
for the review class when unlaunched only if the guard allows it; audit per class with the
transcript count above after any routing change; the article's numbers: Haiku for narrow
checkable jobs (reading, checks, drafts), docs authoring escalates ~37% from Haiku, Explore can
ride the cheap tier, the money is in the top-tier classes. Related: [[delegate-to-subagents]].

*References: delegate-to-subagents*

*Observed 2026-10-10 (fabric-coordinator)*
