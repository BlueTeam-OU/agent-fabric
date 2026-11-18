---
role: "fabric-coordinator"
class: rationale
topic: "gateway-reuse-mit-and-adr-007-decided"
description: "owner 2026-11-13: agent-fabric-gateway admits attributed MIT code (LiteLLM j90 plan), and gateway ADR-007 with plan-declared alternatives is coming; the amendments are my j833"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ec5d09c97c6f1ad2
---

## owner 2026-11-13: agent-fabric-gateway admits attributed MIT code (LiteLLM j90 plan), and gateway ADR-007 with plan-declared alternatives is coming; the amendments are my j833

Owner, 2026-11-13, after rust-services-dev-01's j90 reuse review of LiteLLM's Rust workspace (plan
`architecture/research/reuse-review-litellm-rust-2026-11.md`, branch
develop-qzapp/rust-services-dev-01/feat/j90-in-depth-review-of-litellm-s at ca32526): "yes ADR-007 is coming, do the
amendments".

**Why:** the gateway's own text forbade copied code (roadmap "Behaviours to reproduce, not code to copy", CLAUDE.md §6,
ADR-005 "no implementation is copied … without an explicit licensing decision"); the owner chose to admit attributed
MIT code, decided per piece. The circuit breaker had no consumer while ADR-007 was deferred.

**How to apply:** j833 (mine, gateway working copy, fresh session): amend those three texts, add LICENSES/MIT.txt and a
REUSE.toml annotation pattern per copied path, fold the j90 document, rule on reading SSE `event:` names on a raw path
(ADR-003 rules 2 and 4) and name the new stream outcome (ADR-006 §8 / ADR-012); each ADR amendment touches the four
places in [[gateway-adr-amendment-checklist]]. Gateway CLAUDE.md also bars citing an unrelated external project by
name: attribution headers and the research doc need that rule's exception too. The breaker job (C) rides the
ADR-007 PR (below), not after it. Related: [[tool-litellm]].

**PR order (owner 11-13, answered as recommended):** j833's PR lands the MIT-reuse amendments; the NEXT gateway PR
carries ADR-007's enforcement amendment together with the circuit-breaker code and its tests (job C, supplied onto my
branch). The j830 test-speed work in agent-fabric gets its own PR.

**ADR-007 open questions, owner 11-13 (all as recommended):** OQ-1 a new agent-fabric record decides what the plan
compiler declares as alternatives (job j835; no generated plan carries `failover` before it); OQ-2 all suppressed →
one attempt, first in plan order; OQ-3 a declared rate-limit reset opens the credential scope, the 429 still passed
on; OQ-4 ADR-006 and ADR-007 accepted before the enforcement code merges. Draft: scratchpad adr-007/ (OQ-5..10 at
their recommendations). "agent-fabric ADR-006 rule 13" never existed: the gateway's own ADR-006 rule 20 is meant.

*References: gateway-adr-amendment-checklist, tool-litellm*

*Observed 2026-11-13 (fabric-coordinator)*
