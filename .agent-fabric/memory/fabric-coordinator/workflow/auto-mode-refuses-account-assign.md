---
role: "fabric-coordinator"
class: workflow
topic: "auto-mode-refuses-account-assign"
description: "auto mode may refuse fleet-wide account moves, pane reads and fabric upgrades that earlier sessions ran; state the command and let the owner decide, never retry or hand it over"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 53823e8e9e7fa116
  - 57896eafd6add460
---

## auto mode may refuse fleet-wide account moves, pane reads and fabric upgrades that earlier sessions ran; state the command and let the owner decide, never retry or hand it over

On 2026-10-15 the classifier refused `fabric-accounts assign <logins> <account>`, then
`agent-fabric-fleetdeck pane list` as [Account & Standing-Rule Changes], and later `fabric-ctl all upgrade
fabric` as [Interfere With Workloads] — commands earlier sessions had run. `policies/auto-mode.json` still has no
allow entry for any of the three (read 2026-10-23). Refused again 2026-10-30 as [Modify
Shared Resources] when distributing python-dev-03's merged #430 (j471): a contributor's merge leaves the
fleet un-upgraded until the owner runs it.

**Why:** a refusal holds for the outcome for the rest of the session; the team rule says a refused command is
never handed to the owner as a task.
**How to apply:** state the exact command, the accounts' usage and what restart does, and let the owner decide;
propose an allow entry (policies/auto-mode.json, bash-allowlist.json) if the owner wants agents to keep doing
it. Related: [[account-move-needs-relaunch]], [[stuck-agent-read-its-pane]].

2026-10-30: refused again after #429 merged — `fabric-ctl all upgrade fabric` as [Modify Shared Resources], even with the owner's "arm 429" given in the same turn. Arming is not distribution: report the merge and leave the upgrade to the owner.

2026-10-30, third time that day: after python-dev-02's #432 (j474) merged, refused as [Modify Shared Resources]. Three contributor merges in one day left undistributed — the case for an allow entry is now the owner's call.

*References: account-move-needs-relaunch, stuck-agent-read-its-pane*

*Anchors: `policies/auto-mode.json`, `bin/fabric-ctl`*

*Observed 2026-10-30 (fabric-coordinator)*
