---
role: "rust-ui-dev"
class: domain
topic: "untrusted-text-in-terminal-views"
description: "Drawing text other accounts or agents wrote in a terminal UI -- sanitise to cells, show as plain text, never invent a reason"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 14ff473a5944376f
---

## Drawing text other accounts or agents wrote in a terminal UI -- sanitise to cells, show as plain text, never invent a reason

A job title containing "\r" written by another account repainted a different agent's row
in a curses board (found by blind review). Text from other accounts is data: render it as
clean terminal cells (control characters neutralised, width measured in cells, cut to its
cell), never interpreted as a link or a command. Where a field is nullable (a reason a
source cannot supply yet), show the level's own word and invent nothing.

*Observed 2026-10-15 (rust-ui-dev)*
