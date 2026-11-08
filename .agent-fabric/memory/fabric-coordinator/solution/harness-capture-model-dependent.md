---
role: "fabric-coordinator"
class: solution
topic: "harness-capture-model-dependent"
description: "re-capturing runtime/claude-code/harness/en.md — the text may differ by model, not only by build; how j579 built it"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4ea35cb2827bc829
---

## re-capturing runtime/claude-code/harness/en.md — the text may differ by model, not only by build; how j579 built it

The 2.1.311 capture (j579, PR BlueTeam-OU/agent-fabric#506, live check docs/live-checks/2026-11-07-claude-code-harness-prompt.md) was taken in an Opus 5.5 session; the 2.1.274 one in Fable 5.1. On 2.1.311 "# Delivering work", "# Corrections" and the no-Agent-unasked line are absent, and a "This iteration of Claude is Claude Fable 5" paragraph arrives even on Opus. Whether those follow the build or the model is open: a capture from a Fable session on 2.1.311 decides it.

**Why:** en.md is the source a locale translates and replaces for language-culture logins; text that depends on the model would make one capture wrong for logins on another model.

**How to apply:** record the session model in the live check's header (fabric-status "session model"), and build en.md from the previous one by asserted one-occurrence replacements (a script in the scratchpad), not by retyping — unchanged spans stay byte-identical. The `<total_tokens>` line and the trailing parallel-tool-calls line are not part of the replaceable text. See [[launch-time-change-needs-relaunch]].

*References: launch-time-change-needs-relaunch*

*Anchors: `runtime/claude-code/harness/en.md::build: "2.1.311 (Claude Code)"`*

*Observed 2026-11-07 (fabric-coordinator)*
