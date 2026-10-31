---
role: "rust-services-dev"
class: domain
topic: "validator-shares-runtime-construction"
description: "a validator that copies the runtime's acceptance rule as a pattern drifts both ways; validate by calling the constructor the runtime uses"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - d296ca1517e19c48
---

## a validator that copies the runtime's acceptance rule as a pattern drifts both ways; validate by calling the constructor the runtime uses

When a validator (a schema pattern, a hand-copied regex) restates what the serving path will accept, the two drift, and in both
directions. The first base_url host pattern let through five hosts the transport refuses (a leading hyphen, an empty label, a
malformed bracketed literal, a %-escape, non-ASCII), so a plan passed validation and failed at serve. The tightened pattern was
then stricter than the transport (underscores, a trailing dot).

The fix that holds: the validator builds the very object the runtime will use (the plan reader constructs each backend target
through the backend crate, and a refusal is a validation error with its own rule and exit code). Any pattern in a schema is a
cheap first filter, never the authority.

**Why:** "validate says yes, serve says no" is the failure an operator cannot predict, and pattern review alone missed it twice.

**How to apply:** where a check precedes a runtime step, have it call that step's constructor or parser. Probe a copied pattern
against the real constructor with inputs from each grammar class, with a control that should pass, before you trust it.
[[stage-6-seam]]

*References: stage-6-seam*

*Observed 2026-10-15 (rust-services-dev)*
