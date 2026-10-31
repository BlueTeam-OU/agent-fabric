---
role: "brand-comms"
class: workflow
topic: "harness-neutral-strip-tokens-not-clauses"
description: "When moving a fleet snippet from CLAUDE.md into AGENTS.md (ADR-054), remove only the Claude Code tokens; keep every harness-neutral clause around them."
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 25f5654125d00c15
---

## When moving a fleet snippet from CLAUDE.md into AGENTS.md (ADR-054), remove only the Claude Code tokens; keep every harness-neutral clause around them.

When I moved the GZCoord snippet into blueteam.brand's AGENTS.md, I
rewrote the inbox-watch bullet to remove `Bash(...)` and "never a
Monitor". The two clauses next to them went too: the "exit 0" re-arm
case and the "launcher asks for it, or the session arms it itself"
sentence. Neither is specific to Claude Code. The blind review caught
it as a P3: a reader could take the watch's quiet deadline exit as a
reason to stop watching.

**Why:** rewriting a sentence to drop one tool name rewrites the
claims around it too, without anyone noticing. The snippet is what
the review compares the section against.

**How to apply:** when making a fleet snippet harness-neutral, delete
only the harness tokens (tool calls, skill names, Monitor, settings).
Then diff the section against the snippet clause by clause. Every
claim the snippet makes is either still in AGENTS.md or kept on
CLAUDE.md's line.

*Anchors: `projects/blueteam.brand/integration/gzcoord/CLAUDE.snippet.md::exit 0`*

*Observed 2026-10-19 (brand-comms)*
