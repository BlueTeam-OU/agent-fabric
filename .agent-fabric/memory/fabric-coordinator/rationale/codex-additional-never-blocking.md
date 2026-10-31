---
role: "fabric-coordinator"
class: rationale
topic: "codex-additional-never-blocking"
description: "Owner 2026-10-13: codex is an additional review, never blocking — when it cannot run, the claude review alone arms; settings stopgap + arm rule (additional_reviews, 'unavailable' marker) in flight"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8f74647b8604327f
---

## Owner 2026-10-13: codex is an additional review, never blocking — when it cannot run, the claude review alone arms; settings stopgap + arm rule (additional_reviews, 'unavailable' marker) in flight

The owner, 2026-10-13 ~21:50, after the ChatGPT workspace ran out of Codex allowance and every arm
stopped on gate 4b (reviews ["claude","codex"]): "codex is 'more' not a blocking. If it is not
available only claude run. Fix this because is a big problem." (Earlier the same evening he had said
so in other sessions too, and refused paid API fallback: [[no-paid-openai-api-for-reviews]].)

**Why:** a second engine is added assurance; making it a hard gate let one exhausted subscription
stop the whole fleet's merges.
**How to apply:** codex runs where available and its P1/P2 still block when it reviewed the head;
when it cannot run, its "unavailable" marker on that head lets claude's review arm; never silently
skipped. In flight: settings PRs BlueTeam-OU/agent-fabric-settings#5 and gzapi-org/...#5 (claude-only
reviews as the stopgap), devex-tooling (arm reads additional_reviews + marker), python-dev-03
(review_codex posts the marker), mine: arming.json key/schema, ADR-055 amendment, cap on codex runs.

*References: no-paid-openai-api-for-reviews*

*Observed 2026-10-13 (fabric-coordinator)*
