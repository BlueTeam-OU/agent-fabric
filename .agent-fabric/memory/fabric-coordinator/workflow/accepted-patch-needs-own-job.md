---
role: "fabric-coordinator"
class: workflow
topic: "accepted-patch-needs-own-job"
description: "Patches I accept by REPLY to land \"on my PR from my job session\" need their own job at once, or they are lost"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6b08064f0e1cd113
---

## Patches I accept by REPLY to land "on my PR from my job session" need their own job at once, or they are lost

On 2026-10-24 I accepted python-dev-02's three j379 patches (commands.json gzcoord-carrier entry, live-check page, CARRIER-CONTRACT.md; REPLY 01a16feb) "to land on #371 from my job session", and marked j379 delivered against them. No job carried the apply. On 2026-10-25, after #373 merged and the fleet upgraded, gzcoord-carrier was on no account's PATH: bootstrap links only what commands.json lists, and the entry was still in the handover dir. Caught only by reading back PATH after the upgrade; j402 added then.

**Why:** a session works one job's working copy (ADR-037 rule 3), so "later, from that job's session" has no carrier unless a job names it; a delivered job hides that work remains.

**How to apply:** when accepting a supply to apply myself, `fabric-jobs add` the apply job in the same turn (working copy = the PR's worktree), and read back the user-visible effect (PATH, status) after distribution. Related: [[supply-contract-commit-and-push]], [[launch-time-change-needs-relaunch]].

*References: launch-time-change-needs-relaunch, supply-contract-commit-and-push*

*Anchors: `runtime/claude-code/commands.json::commands`*

*Observed 2026-10-25 (fabric-coordinator)*
