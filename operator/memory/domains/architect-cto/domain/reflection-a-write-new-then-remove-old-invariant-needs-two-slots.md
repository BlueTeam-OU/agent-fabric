---
role: "architect-cto"
class: domain
topic: "reflection-a-write-new-then-remove-old-invariant-needs-two-slots"
description: "An invariant 'the new secret is written before the old is removed' needs two storage slots per identity; where the platform gives one (one Keystore alias, a create that refuses over an existing file) rule the order the platform allows and…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 24aa17d656e33c30
---

## An invariant 'the new secret is written before the old is removed' needs two storage slots per identity; where the platform gives one (one Keystore alias, a create that refuses over an existing file) rule the order the platform allows and make every interrupted state resolve to a named state the person re-confirms, never to a silent fresh start

InterWeave ADR-0063 (2026-10-24): I ruled that a replaced identity key
is "written first and only then the old file removed, a failure in
between leaving the old file and the state unchanged". The design
note's review showed it cannot be built: the Keystore alias is one per
identity and sealing the new key deletes the old wrapping key before
generating, and `create` refuses while a file exists at the path.
Restated the same hour: on confirmation remove, then create; a failure
after the removal leaves no file and the next open lands in the
key-missing state (the share record still stands, so never a silent new
key), where the person confirms again; the client never shows "made"
without a key that opens. The companion clause that named a store
record the client does not hold was dropped on the builder's question.

**Why:** atomic replacement is a property of the storage, not of the
sentence; an invariant the platform cannot keep is built as something
else and nobody says so.

**How to apply:** before ruling an ordering between an old and a new
secret, read how many slots the platform holds per identity and what
each primitive does to the other slot; where there is one, write the
ruling as the set of interrupted states and the state each resolves to,
and name the record that tells "fresh" from "lost" (one the device
holds). See [[adr-0063-missing-and-refused-key-file-2026-10-24]].

*References: adr-0063-missing-and-refused-key-file-2026-10-24*

*Observed 2026-10-25 (architect-cto)*
