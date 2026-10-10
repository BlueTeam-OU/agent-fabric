---
role: "fabric-coordinator"
class: workflow
topic: "delegate-to-subagents"
description: "The owner wants the coordinator to run more work through asynchronous subagents (2026-10-09): delegate implementation, reviews and investigations, keep myself on coordination"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 30bc399cc2a9b118
---

## The owner wants the coordinator to run more work through asynchronous subagents (2026-10-09): delegate implementation, reviews and investigations, keep myself on coordination

The owner, 2026-10-09: "as you are a really important guy in our organization you
should use more subagents (doing asynchronous work)". That day I wrote plan v0, the
bootstrap re-point, the #148 fixes and several records myself, serially, while agents
and the owner waited on me.

**Why:** the coordinator's measure is the fleet's throughput; my own serial edits block
replies, reviews and dispatch.

**How to apply:** for a piece of my own lane (never-list code, records, fixes from a
review), dispatch a worktree-isolated class agent (code-medium/code-high, model per
aliases) in the background with a complete contract, and keep answering the inbox,
reviewing and arming meanwhile; run independent pieces in parallel. Do directly only
what is a few lines or needs a decision. Reviews stay code-review on fable. Related:
[[nudge-idle-agent-by-message]].

**Learned the same day:** a worker's push can be refused by the classifier ("Out-of-Place
Publication") even when earlier workers' pushes went through; never push a refused
worker's commit for it. Brief a worker to commit locally and report, and keep design
latitude out of mechanical briefs: one worker met "no lookaround" with a 5,924-character
regex, where the right answer was a shape-only pattern with the transport as authority.

**Fleet first (the owner, 2026-10-09, later the same day):** before dispatching a
subagent, read the board (`fabric-ctl all jobs`, `fabric-fleet`) for an agent with no job
whose role and entry cover the work; if there is one, send it a REQUEST (it becomes a job
on its list) instead of spawning a subagent. A subagent is for what no free agent may
take: my never-list (identities/, routing/, policies/, runtime/claude-code/, bootstrap,
records), a decision only I make, or nobody free and applicable.

*References: nudge-idle-agent-by-message*

*Observed 2026-10-09 (fabric-coordinator)*
