---
role: "fabric-coordinator"
class: rationale
topic: "review-model-availability"
description: "Owner 2026-10-13 — a review model at capacity: retry 10 s, 20 s, 60 s; then report 'chosen model unavailable' (capacity vs weekly allowance); divert to another review-grade model/provider when it is the request's only reviewer; model…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1a77481d89caef3b
---

## Owner 2026-10-13 — a review model at capacity: retry 10 s, 20 s, 60 s; then report 'chosen model unavailable' (capacity vs weekly allowance); divert to another review-grade model/provider when it is the request's only reviewer; model availability belongs to the control plane

The owner, 2026-10-13, in the coordinator's session, after a Codex review on #232 failed twice with
OpenAI's "Selected model is at capacity" (python-dev-01's live check of ADR-053 rule 8) and Codex
became required on every PR (policies/arming.json, ADR-053 rule 6 made engine-neutral):

1. **Retry**: 10 s, 20 s, 60 s — not minutes.
2. **Then report**: "the chosen model is unavailable", saying which kind — at capacity (the
   provider's, transient) or over the weekly allowance (ours, until the window resets).
3. **Divert**: to another review-level model or provider, when it is the only review model
   running for that review request (a request another engine also reviews just reports).
4. **Control plane**: tracks availability only "to let humans know about it"; availability is
   "rediscovered each time locally, not centrally managed" (the owner corrected my first draft,
   which had routing consult a central record). Drafted as ADR-055 (Proposed).

**Why:** with both engines required, one provider's capacity spell stops every merge in the fleet.
**How to apply:** 1–3 are an engine change (review_codex.py, python-dev) plus routing's fallback
order (mine); 4 is a decision record I draft for the owner. Related: [[codex-review-routing-decision]].

*References: codex-review-routing-decision*

*Observed 2026-10-13 (fabric-coordinator)*
