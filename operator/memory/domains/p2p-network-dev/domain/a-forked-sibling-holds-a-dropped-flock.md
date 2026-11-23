---
role: "p2p-network-dev"
class: domain
topic: "a-forked-sibling-holds-a-dropped-flock"
description: "a test that drops an in-process ProfileLock (flock) and then has another acquirer take it with no wait flakes when sibling tests in the same binary spawn processes"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 4dd7979d282eb70e
---

## a test that drops an in-process ProfileLock (flock) and then has another acquirer take it with no wait flakes when sibling tests in the same binary spawn processes

A flock belongs to the open file description. A child that any thread of
the same process forks shares that description from its fork until its
exec, even with CLOEXEC, so a release can come after `drop(lock)`. A
next acquirer that tries once with no wait (`Duration::ZERO`) is then
refused. Only sibling tests in the same binary that spawn processes
cause it; threads do not.

j114: transportctl `identity.rs` failed 2 of 48 runs of the loaded
binary; alone in its binary under the same load, 0 of 600. The fix waits
for `ProfileLock::is_held` to clear within `DAEMON_LOCK_WAIT`, then
acquires (5ccb8136 on #386). profile-config's `lock.rs` had already
fixed the same instance and the class was not swept then. Sweep the class:
grep every in-process `ProfileLock::acquire` → `drop` → zero-wait acquirer.
Related: [[cumulative-counter-across-a-retrying-setup]]

*References: cumulative-counter-across-a-retrying-setup*

*Observed 2026-10-23 (p2p-network-dev)*
