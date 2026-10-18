---
role: "p2p-network-dev"
class: domain
topic: "domain-key-custody-isolation-and-order"
description: "Wrapping a secret under a platform key: key the alias per (tenant, purpose) in the trusted layer, and never destroy the old key before the new record is durable — retire after the write, and let a restore try the existing record first"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 548076361d503fab
---

## Wrapping a secret under a platform key: key the alias per (tenant, purpose) in the trusted layer, and never destroy the old key before the new record is durable — retire after the write, and let a restore try the existing record first

Two classes of defect found in three review rounds of InterWeave #256 (IWK1 envelope under an Android
Keystore key; ADR-0042 records the result):

1. **Isolation.** One platform key per POLICY, shared by every profile: sealing one profile rotated the key
   under every other profile's record, and a record copied into another profile's directory unlocked as that
   profile (the PeerId it was checked against came from the record). Fix: `KeyRef = (profile, policy)`, the
   alias `interweave.iwk1.<profile>.<policy>` computed by custody, never by the adapter; whose record it is
   decided from the record's PeerId field against the caller's expectation.
2. **Destroy-before-write.** First fix deleted every key of the profile and then wrote the new record, so a
   failed write (full disk) left a record with no key: a working profile went to recovery. Then a restore
   under the record's own policy sealed over the key a healthy record opens under — same class, second
   instance. Fix: seal replaces only its own alias; the other key is retired (`retire`, missing = Ok) only
   AFTER the new record is written, a failed retire is said (`OldKeyRemains`) and retried by reseal; a
   restore first TRIES the existing record and keeps it if it opens to the expected PeerId.

**How to apply:** for any rotate/replace of key material, list the states after a crash or a failed write at
each step; every one must leave at least one record that opens. Test with an injected write failure after
the seal.

*Observed 2026-10-15 (p2p-network-dev)*
