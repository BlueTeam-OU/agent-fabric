---
role: "devex-tooling"
class: domain
topic: "harness-param-accepted-is-not-honoured"
description: a Claude Code tool parameter a skill or decision names may be absent, rejected or silently ignored in this build or session mode; read the schema you hold and what the tool answers
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fe5a85cf46e0e00f
---

## a Claude Code tool parameter a skill or decision names may be absent, rejected or silently ignored in this build or session mode; read the schema you hold and what the tool answers

Claude Code tool schemas differ by build and by session mode, and a text written against one session's
schema is wrong for another. Seen three ways: Monitor on 2.1.271 had no `persistent` field and a
30-minute cap, while the owner's build had both; 2.1.272 headless accepted `persistent: true` and
ignored it, while interactive honoured it; the Agent tool's `model` accepts only the four tier aliases,
so a provider model id is rejected by the schema before any hook runs.

**How to apply:** before writing a skill, guard or decision that relies on a tool parameter, read
the tool schema this session actually holds, and judge the behaviour from what the tool reports back
(its start message, its error), never from the call being accepted. Name the build and mode in the
text. A teammate's "pass X" is checked the same way before it is followed.

*Observed 2026-10-16 (devex-tooling)*
