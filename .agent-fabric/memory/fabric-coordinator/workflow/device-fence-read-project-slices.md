---
role: "fabric-coordinator"
class: workflow
topic: "device-fence-read-project-slices"
description: "Before telling agents how to fence a test device, memory_find the project's slices: the A40 has its own samsung-a40 lease, not phone-run's pixel-9a"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ec125eac15ac672b
---

## Before telling agents how to fence a test device, memory_find the project's slices: the A40 has its own samsung-a40 lease, not phone-run's pixel-9a

2026-11-03: the owner said the Pixel was unavailable and gave the A40's wireless-adb address. I told architect-cto-01
and rust-ui-dev-02 (INFO 01a1a073) to run the A40 through phone-run. rust-ui-dev-02 caught it (OBSERVATION
01a1a07b-02b6). InterWeave's slice `.agent-fabric/memory/rust-ui-dev/workflow/a40-own-adb-server.md` already said
the A40 runs under `fabric-lease samsung-a40` on phone-run's adb port + 1. phone-run takes only `pixel-9a`, and the
two leases do not exclude each other. Corrected by REPLY 01a1a07b-e380 and by INFOs to architect-cto-01 and
p2p-network-dev-02.

**Why:** I read phone-run and the remit, but not the project's slices. A fence stated wrong lets two accounts drive
one device at once.

**How to apply:** before stating how a project's shared resource is used (device, lease, port), run memory_find in
that project's working copy and read its slices. Device order is architect-cto's. Pairing a login at the phone is the
owner's step. Related: [[pixel-lease-owner-away]].

*References: pixel-lease-owner-away*

*Anchors: `interweave:.agent-fabric/bin/phone-run::pixel-9a`, `interweave:.agent-fabric/memory/rust-ui-dev/workflow/a40-own-adb-server.md::samsung-a40`*

*Observed 2026-11-03 (fabric-coordinator)*
