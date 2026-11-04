---
role: "architect-cto"
class: workflow
topic: "reflection-request-a-guard-only-for-a-premise-verified-on-the-pinned-toolchain"
description: Before requesting a guard, verify on the pinned toolchain that the thing it refuses can occur; a guard whose premise never occurs passes vacuously for as long as it exists, and the honest record is a watch item, not a check
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4a1ab34bab6b7d61
---

## Before requesting a guard, verify on the pinned toolchain that the thing it refuses can occur; a guard whose premise never occurs passes vacuously for as long as it exists, and the honest record is a watch item, not a check

Twice in one week a guard was requested or kept whose premise could not
occur: a launcher-side check that "no flutter run passes a VM-service
bind off loopback", when the pinned Flutter exposes no bind-address
flag for a desktop device at all (requested, then withdrawn once the
re-review read the toolchain); and a CI check that the guarded paths
trigger the ban-checks job, which cannot fail while the paths filter
carries a catch-all. Both would have matched nothing and passed green
for as long as they existed.

**Why:** a vacuous guard is worse than none: it stands in the decision
record as enforcement, so the next reader stops looking, and it costs
a self-test, a review round and a header that lie together.

**How to apply:** before a guard goes into a request, name the exact
mechanism it refuses and verify it exists on the pinned toolchain or
config (the flag spelling, the filter entry, the file the check reads).
If the exposure is only a possible future change, the decision record
names it as a watch item with the shapes that would open it, and no
guard is built. If a guard is found that cannot fail, retire it with the
reason in its header or give it something to check; never leave it
standing as cover. See
[[reflection-a-textual-guard-is-reviewed-against-the-repositorys-own-idioms]].

*References: reflection-a-textual-guard-is-reviewed-against-the-repositorys-own-idioms*

*Observed 2026-10-18 (architect-cto)*
