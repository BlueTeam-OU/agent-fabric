---
role: "fabric-coordinator"
class: rationale
topic: "cutover-d6-d7-d8-accepted"
description: "Owner 2026-11-15 accepted cutover decisions D6, D7, D8 as recommended; W11 and new W17 dispatched; soak is 3 working days on two accounts, 7 on the fleet per rung"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6d3f12e66882354e
---

## Owner 2026-11-15 accepted cutover decisions D6, D7, D8 as recommended; W11 and new W17 dispatched; soak is 3 working days on two accounts, 7 on the fleet per rung

The owner said "yes to D6, D7 and D8" in session on 2026-11-15, each as the cutover plan recommends (docs/proposals/gzcoord-interweave-only-cutover.md §7):
- D6: a TO-ROLE is decided at arrival (the presence check already refuses a role with no running holder unless forced). Work: W11, a test.
- D7: a GZCOORD_JOURNAL=off send in a carrier mode goes through the carrier with its bypass line; no journal-off receiving; the human relay is the break-glass. Work: W17 (added to the plan that day, commit 4362409e). Records: ADR-041 rule 10 and ADR-064 rule 8, amended at gate 2's word, not before.
- D8: soak of three working days on two accounts (python-dev-02 and python-dev-03 first), then seven days on the fleet at each rung; the coordinator's account last.

**Why:** these were the last open decisions before gate 2's evidence could be gathered.
**How to apply:** the gate words still come one at a time; D8 sets the soak length to quote when asking for gate 1 and gate 2. Related: [[interweave-only-cutover-owner-decisions]].

*References: interweave-only-cutover-owner-decisions*

*Observed 2026-11-15 (fabric-coordinator)*
