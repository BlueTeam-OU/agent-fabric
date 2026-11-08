---
role: "architect-cto"
class: workflow
topic: "auto-mode-classifier-refuses-authorizes-send"
description: "Correction, 2026-11-03: gzcoord-send of a REPLY or DECISION carrying AUTHORIZES from gzapp's arming authority is allowed in auto mode since agent-fabric f5968f1c (policies/auto-mode.json allow[1]); the 2026-10-18 refusal is history"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
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

In an auto-mode session, `gzcoord-send` of a DECISION or REPLY carrying
`AUTHORIZES: <org/repo>#<n>@<sha>` for another login's below-minimum PR
is refused by the harness classifier ("Auto-Mode Bypass"). Seen twice:
2026-10-18 in two consecutive architect-cto-01 sessions for FleetDeck #42
(j145), the second time after the owner said "AUTHORIZES for FleetDeck
#42" in session. A dry run passes; only the live post is refused, and
the follow-up read of the sent log was refused too.

**Why:** the classifier reads a third-party arm authorization as
merging without review, whatever the PR's review state.

**How to apply:** compose and dry-run the message, record the refusal
on the job, and report to the owner with the refusal text; the owner's
word goes to the PR's owner directly, or the owner adds a permission
rule. Never retry through another tool or quoting. fabric-coordinator
took the refusal as its finding on 2026-10-18 (INFO 01a150c6-c1d9); #42
merged on the owner's word to its owner directly. Related:
[[fold-by-merge-breaks-follow-on-a-rename]] is unrelated; see
`policies/auto-mode.json` for where a change would land.

*References: fold-by-merge-breaks-follow-on-a-rename*

*Observed 2026-10-18 (architect-cto)*

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
