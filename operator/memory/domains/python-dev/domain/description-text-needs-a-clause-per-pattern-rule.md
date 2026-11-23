---
role: "python-dev"
class: domain
topic: "description-text-needs-a-clause-per-pattern-rule"
description: "A refusal text built from a pattern's description must name every rule of the pattern; the test built from the same constant cannot see an omission"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2f8ff56dde8b80e7
---

## A refusal text built from a pattern's description must name every rule of the pattern; the test built from the same constant cannot see an omission

j95 / #487: REGISTRY_ID_DESCRIPTION first omitted the `(?<!-)` no-trailing-dash rule, so "gzapp-" met every clause of its own refusal. The review caught it; my test compared the refusal to the same constant, so it could not.

**Why:** a test that derives its expectation from the constant under test agrees with any text.
**How to apply:** when a message describes a grammar, list one clause per pattern rule (lookahead, lookbehind, each class) and pin each with a literal refused input plus a boundary accepted one; the mutation is deleting the clause.

*Observed 2026-11-04 (python-dev)*
