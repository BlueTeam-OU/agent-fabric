---
role: "fabric-coordinator"
class: workflow
topic: "owner-arm-only-when-verified"
description: "Never hand the owner an arm command for a PR I don't own unless I verified, just before, that its author calls it final, a dry-run arm of the current head passes (both engines), and CI is green"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8cfe75b74ae18538
---

## Never hand the owner an arm command for a PR I don't own unless I verified, just before, that its author calls it final, a dry-run arm of the current head passes (both engines), and CI is green

The owner, 2026-10-13 evening: "you should not let me arm from you something that you don't own -
better if you do you must be sure that it is ready to be armed". That night I gave arm commands for
#240, #241, fleetdeck #29 and #236: #241's and #236's were refused (no codex review of the head),
and #236 was armed, then disarmed by its author's next push (a codex P2 still being fixed).

**Why:** the owner's word is spent on a check I should have made; a refused or undone arm costs
them a round trip and trust in what I say is ready.
**How to apply:** before giving `fabric-pr arm <n> --any-owner …` for another agent's PR:
(1) the author confirms the PR is final — no fix, push or review in flight; (2) `fabric-pr arm <n>
--any-owner --dry-run --basis "owner's word"` passes on the current head (each required engine);
(3) checks green. Only then the command, with the head sha I checked. My own PRs I arm myself at the
gate. Related: [[threat-model-before-boundary-request]].

*References: threat-model-before-boundary-request*

*Observed 2026-10-13 (fabric-coordinator)*
