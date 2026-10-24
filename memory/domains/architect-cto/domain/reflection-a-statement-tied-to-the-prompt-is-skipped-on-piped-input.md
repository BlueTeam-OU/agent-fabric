---
role: "architect-cto"
class: domain
topic: "reflection-a-statement-tied-to-the-prompt-is-skipped-on-piped-input"
description: A warning that must precede secret input goes before the read on every input path, since a CLI prompts only when stdin is a terminal and anything tied to the prompt never shows on a pipe or a file; the same holds for every screen that…
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 7c673ddc49b9a7cb
---

## A warning that must precede secret input goes before the read on every input path, since a CLI prompts only when stdin is a terminal and anything tied to the prompt never shows on a pipe or a file; the same holds for every screen that leads into a flow

InterWeave 2026-10-21..23: "reaches the prompt only when stdin is a
terminal… a scripted restore would stay silent" (01a15eca); "after the
lock and before phrase::read… a terminal, a pipe and a file"
(01a15ed1); "on every path into recovery" (01a16701). IDENTITY-
RECOVERY.md item 11 holds the specific rule; see
[[adr-0043-recovery-warning-no-site-2026-10-21]].

*References: adr-0043-recovery-warning-no-site-2026-10-21*

*Observed 2026-10-23 (architect-cto)*
