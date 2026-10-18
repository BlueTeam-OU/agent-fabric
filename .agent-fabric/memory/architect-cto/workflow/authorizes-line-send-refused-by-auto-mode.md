---
role: "architect-cto"
class: workflow
topic: "authorizes-line-send-refused-by-auto-mode"
description: "The auto-mode classifier refuses gzcoord-send of a DECISION carrying an AUTHORIZES line (boundary arm below minimum) as \"CI Bypass\"; the judgement is done in-session, the line reaches the arm only by the owner's hand"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d03bddac4329d398
---

## The auto-mode classifier refuses gzcoord-send of a DECISION carrying an AUTHORIZES line (boundary arm below minimum) as "CI Bypass"; the judgement is done in-session, the line reaches the arm only by the owner's hand

On 2026-10-18 the auto-mode classifier refused `gzcoord-send` of a
DECISION to fabric-coordinator carrying
`AUTHORIZES: BlueTeam-OU/agent-fabric#295@71d5b3b7`, reason "CI Bypass".
The repository's arming override (agent-fabric-settings
repos/agent-fabric.json, commits.boundary_authority = architect-cto) lets
this role arm a security-boundary PR below boundary_min in the owner's
place; the harness's classifier does not know that and reads the line as a
gate bypass.

**Why:** the AUTHORIZES line is, by design, the thing that lets an arm pass
under the minimum, so the classifier's category matches it literally.

**How to apply:** do the judgement (remote head, CI, review on that head,
the diff itself, a live run of the changed function) and record it in the
job; do not re-send the line through another shape or turn. Report the
refusal and the verdict to the owner. When the owner types the AUTHORIZES
line into the session, that is their word: the same send then passes
(2026-10-18, DECISION 01a14d19 sent, seq 299293), and the DECISION says
the owner gave the line. Proposing an allowlist entry (policies/auto-mode.json) for a
DECISION whose only effect is this line is fabric-coordinator's to decide,
on the owner's word. See [[pull-requests]].

*References: pull-requests*

*Anchors: `tools/fabric/github/arm.py::AUTHORIZES`, `policies/auto-mode.json::gzcoord-send`*

*Observed 2026-10-18 (architect-cto)*
