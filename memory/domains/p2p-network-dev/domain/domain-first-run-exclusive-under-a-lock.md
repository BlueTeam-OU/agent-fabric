---
role: "p2p-network-dev"
class: domain
topic: "domain-first-run-exclusive-under-a-lock"
description: "Making a first-run creation exclusive (provision one identity record) — hold a kernel-released lock across the whole step, not a reservation file: a crash leaves the file behind and refuses every later attempt"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - e35d03993d8503e7
---

## Making a first-run creation exclusive (provision one identity record) — hold a kernel-released lock across the whole step, not a reservation file: a crash leaves the file behind and refuses every later attempt

InterWeave #256 (Android key custody, ADR-0042): `identity.iwk1` was written with an exclusive create, but the
seal ran BEFORE the create, so two racing first runs could both seal (each rotating the platform key) and
only one record would win — possibly one that no longer opens. Fixed by taking the profile lock
(`ProfileLock`, no wait) before anything seals; a second holder gets `ProfileLocked`.

Lock rather than a reservation file: the kernel releases a lock when its holder dies, while a reservation
file left by a crash would refuse every later provisioning of a profile that never got its identity. The
same lock also refuses a restore while a host runs the profile.

**How to apply:** an exclusive create protects only the write, not the side effects before it (a key
generated, a remote registered). Hold one lock over the whole check→side-effect→write sequence, and
prove it with N threads at a barrier: exactly one side effect, and the one record opens.

*Observed 2026-10-15 (p2p-network-dev)*
