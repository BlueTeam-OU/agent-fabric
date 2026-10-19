---
role: "fabric-coordinator"
class: rationale
topic: "codex-review-routing-decision"
description: "Owner 2026-10-12 — an `openai` routing provider; the Codex review engine's code-review model is gpt-6.1-sol at reasoning level high; one reviewer (my login) first"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 959cb7ae360f22dc
---

## Owner 2026-10-12 — an `openai` routing provider; the Codex review engine's code-review model is gpt-6.1-sol at reasoning level high; one reviewer (my login) first

The owner, 2026-10-12, in my session: create an `openai` provider in routing; the Codex review
engine reviews on `gpt-6.1-sol` (Codex's default on the team plan) at `model_reasoning_effort`
`high` (the Claude review class stays Opus 5.5 at medium). Both choices were my proposal, accepted
as "I agree with you for both decision"; job j170.

Before this, Codex's model was a required `--model` and its level a hard-coded constant in
`tools/fabric/review_codex.py` — outside routing, which #224's review flagged (ADR-006 §6 names
`-c model_reasoning_effort` as the Codex adapter's channel).

**Why:** a contrarian reviewer should be chosen by policy like the Claude one, not by whoever runs
the command; high because the plan's default was `none`.
**How to apply:** change the Codex review model or level in routing (capabilities.json,
review-grade.json, effort.json), never by a flag default. Related: [[codex-decisions]],
[[codex-chatgpt-signin-2026-10-12]].

*References: codex-chatgpt-signin-2026-10-12, codex-decisions*

*Observed 2026-10-12 (fabric-coordinator)*
