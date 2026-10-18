---
role: "p2p-network-dev"
class: domain
topic: "domain-failure-set-needs-a-non-verdict"
description: "A closed failure set for a platform key operation needs a 'transient — decide nothing' member, or an adapter must report a passing platform error as a verdict that sends the user into recovery"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 9b370495338bba5b
---

## A closed failure set for a platform key operation needs a 'transient — decide nothing' member, or an adapter must report a passing platform error as a verdict that sends the user into recovery

InterWeave #256's SeedCipher seam (Rust custody path ↔ Android Keystore adapter) was agreed with four
failures — KeyInvalidated, KeyMissing, UserNotAuthenticated, Authentication — each a VERDICT on the record
(two of them lead to recovery). Any other Keystore error (a binder hiccup, a busy keystore daemon) would have
had to be mapped to one of them. Added a fifth, `Unavailable(String)`: for the log only, read by unlock as
"try again, decide nothing", never recovery. ADR-0042's amendment records the set as closed.

**How to apply:** when you define the error enum another role implements against, sort each member into
"verdict about the data" vs "could not ask"; if the second column is empty, add it before the adapter
exists, and test that it never reaches the destructive path.

*Observed 2026-10-15 (p2p-network-dev)*
