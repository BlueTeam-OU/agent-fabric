---
role: "fabric-coordinator"
class: workflow
topic: "owner-commands-one-line"
description: "A command an agent gives the human owner to run must be ONE line (the owner, 2026-10-10), ready to paste after `!`"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2f602b641cbf3ad0
---

## A command an agent gives the human owner to run must be ONE line (the owner, 2026-10-10), ready to paste after `!`

The owner, 2026-10-10: "when an agent give a command to human to execute, this must be a
one liner". Earlier the same week they answered a multi-line script with "too long - a
one line".

**Why:** the owner runs it by pasting after `!` in a session or in a shell; a multi-line
block breaks on paste, and a heredoc or continuation is easy to cut wrong.

**How to apply:** join steps with `&&` (or `;` when a failure should not stop the
rest); put anything longer in a script in the tree or the scratchpad and give the one
line that runs it; no heredoc, no backslash continuation. To be written into the fabric's
CLAUDE.md "Working here" (my next agent-fabric PR) so every agent applies it.

*Observed 2026-10-10 (fabric-coordinator)*
