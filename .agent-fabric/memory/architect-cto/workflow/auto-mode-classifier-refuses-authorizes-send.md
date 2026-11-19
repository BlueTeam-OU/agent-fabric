---
role: "architect-cto"
class: workflow
topic: "auto-mode-classifier-refuses-authorizes-send"
description: "Correction, 2026-11-03: gzcoord-send of a REPLY or DECISION carrying AUTHORIZES from gzapp's arming authority is allowed in auto mode since agent-fabric f5968f1c (policies/auto-mode.json allow[1]); the 2026-10-18 refusal is history"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 399aa45d593d4844
  - defe42a9d093ca95
---

## gzcoord-send of a message carrying an AUTHORIZES header for another agent's PR is refused by the auto-mode classifier (Auto-Mode Bypass), even on the owner's explicit word in session; the owner's word to the PR owner directly is the working path

On 2026-10-18 the auto-mode classifier refused `gzcoord-send` of a
message carrying `AUTHORIZES: <org/repo>#<n>@<sha>` (FleetDeck #42,
j145). That is history: agent-fabric f5968f1c (2026-10-19) added
`policies/auto-mode.json` allow[1], which names the send by the role
the repository's arming policy lists as below_min_authority or
boundary_authority (architect-cto in gzapp and InterWeave). Observed
again 2026-11-03: REPLY 01a19edb-94d5 with the header beside `TO:`
authorizing gzapp #1205 at cf3982a3 went out as seq 770732 with no
refusal, in an auto-mode session; five DECISIONs on 2026-10-20 before it.

**Why:** the allow entry states the authority and the limit: the
message merges nothing; `fabric-pr arm`, run by the PR's own session,
still applies the review gate and the required checks.

**How to apply:** judge first (remote head, its commits and paths,
the posted review, CI), then send the REPLY or DECISION with the
header beside `TO:`; the PR's session passes its id to
`--authorization`. A refusal now is a new fact to report, not the
known one. The header is on a REPLY as well as a DECISION: arm reads
the header, not the type.

*Observed 2026-11-08 (architect-cto)*

## Correction, 2026-11-03: gzcoord-send of a REPLY or DECISION carrying AUTHORIZES from gzapp's arming authority is allowed in auto mode since agent-fabric f5968f1c (policies/auto-mode.json allow[1]); the 2026-10-18 refusal is history

On 2026-10-18 the auto-mode classifier refused `gzcoord-send` of a
message carrying `AUTHORIZES: <org/repo>#<n>@<sha>` (FleetDeck #42,
j145). That is history: agent-fabric f5968f1c (2026-10-19) added
`policies/auto-mode.json` allow[1], which names the send by the role
the repository's arming policy lists as below_min_authority or
boundary_authority (architect-cto in gzapp and InterWeave). Observed
again 2026-11-03: REPLY 01a19edb-94d5 with the header beside `TO:`
authorizing gzapp #1205 at cf3982a3 went out as seq 770732 with no
refusal, in an auto-mode session; five DECISIONs on 2026-10-20 before it.

**Why:** the allow entry states the authority and the limit: the
message merges nothing; `fabric-pr arm`, run by the PR's own session,
still applies the review gate and the required checks.

**How to apply:** judge first (remote head, its commits and paths,
the posted review, CI), then send the REPLY or DECISION with the
header beside `TO:`; the PR's session passes its id to
`--authorization`. A refusal now is a new fact to report, not the
known one. The header is on a REPLY as well as a DECISION: arm reads
the header, not the type.

*Observed 2026-11-03 (architect-cto)*
