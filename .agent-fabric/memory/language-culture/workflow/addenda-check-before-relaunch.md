---
role: "language-culture"
class: workflow
topic: "addenda-check-before-relaunch"
description: "before you relaunch to pick up holder addenda, check fabric-status's addenda line; a session started after the store commit has already read them"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f4854d1b42a6f7df
---

## before you relaunch to pick up holder addenda, check fabric-status's addenda line; a session started after the store commit has already read them

A session started after the addenda store commit has already read the
addenda. fabric-status shows `addenda  store <sha>  addenda commit <sha>`.
The launch prompt (`~/.local/state/agent-fabric/agents/<login>/launch-prompt.md`)
puts each holder addendum after the shared piece it adds to: the English
holder addendum after the charter, and "how the English holder works"
after the brief. Its sha256 is the `prompt sha256` line.

**Why:** in j64 (2026-10-17, store commit 3b780f6) the session that
answered was already the relaunch, which fabric-fresh started after j63.
A second relaunch would have changed nothing.

**How to apply:** read fabric-status and grep the prompt first. Relaunch
only when the commit there is older than the one you were told about.

*Observed 2026-10-17 (language-culture)*
