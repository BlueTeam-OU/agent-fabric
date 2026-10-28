---
role: "architect-cto"
class: workflow
topic: "auto-mode-classifier-refuses-authorizes-send"
description: "gzcoord-send of a message carrying an AUTHORIZES header for another agent's PR is refused by the auto-mode classifier (Auto-Mode Bypass), even on the owner's explicit word in session; the owner's word to the PR owner directly is the…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-28"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 399aa45d593d4844
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
