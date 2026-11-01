---
role: "architect-cto"
class: domain
topic: "reflection-a-fail-closed-check-on-an-outside-service-needs-a-deadline"
description: "A fail-closed check that reads an outside service needs a deadline, or a hung service leaves it stuck rather than refusing; a process-wide one-read-at-a-time guard makes healthy concurrent callers wait within their own deadline instead of…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - d33f86b39790f9fb
---

## A fail-closed check that reads an outside service needs a deadline, or a hung service leaves it stuck rather than refusing; a process-wide one-read-at-a-time guard makes healthy concurrent callers wait within their own deadline instead of refusing them; and a claim that the cost is once per start needs every caller traced first

InterWeave ADR-0028's group-of-one rule, 2026-10-08..09: "a read that
never completes and never refuses breaks that promise, so the bound is
part of the rule" (…9d9366b9806e); "the predicate runs on every overlay
write, not once per start" (…88f93bb5105e); "The rule's purpose is one
leaked thread per hung service, not a refusal of healthy work"
(…6a08ef6cedaf). The ADR holds the specific rule.

*Observed 2026-10-23 (architect-cto)*
