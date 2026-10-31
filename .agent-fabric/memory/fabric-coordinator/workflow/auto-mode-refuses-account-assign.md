---
role: "fabric-coordinator"
class: workflow
topic: "auto-mode-refuses-account-assign"
description: "auto mode may refuse fleet-wide account moves, pane reads and fabric upgrades that earlier sessions ran; state the command and let the owner decide, never retry or hand it over"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 53823e8e9e7fa116
---

## auto mode may refuse fleet-wide account moves, pane reads and fabric upgrades that earlier sessions ran; state the command and let the owner decide, never retry or hand it over

On 2026-10-15 the owner said "move interweave user on the other account". The classifier refused
`fabric-accounts assign p2p-network-dev-01 p2p-network-dev-02 andrea-benetton-blueteam-ge` (no
reason given), then refused `agent-fabric-fleetdeck pane list` as [Account & Standing-Rule
Changes]. Earlier sessions ran both (see [[account-move-needs-relaunch]], [[stuck-agent-read-its-pane]]).

Later the same day (j215, after #272 merged) it refused `fabric-ctl all upgrade fabric` as
[Interfere With Workloads] — the distribution step every merged fabric PR ends with. The
same session then ran `fabric-reflect-jobs` (jobs-add on 26 lists) without a refusal.

**Why:** a refusal holds for the outcome for the rest of the session; the team rule says a refused
command is never handed to the owner as a task.
**How to apply:** state the exact command, the accounts' usage and what restart does, and let the
owner decide; propose an allowlist or auto-mode entry for fabric-accounts assign and fleetdeck pane
read if the owner wants agents to keep doing it (policies/auto-mode.json, bash-allowlist.json).

*References: account-move-needs-relaunch, stuck-agent-read-its-pane*

*Anchors: `policies/auto-mode.json`, `bin/fabric-ctl`*

*Observed 2026-10-15 (fabric-coordinator)*
