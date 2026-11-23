---
role: "p2p-network-dev"
class: domain
topic: "domain-a-negative-payload-must-be-one-the-gate-would-admit"
description: "A \"remote request changes nothing\" test is vacuous for a payload the target refuses anyway (TEST-NET address vs the add floor)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 99023dfe1a2d44f4
---

## A "remote request changes nothing" test is vacuous for a payload the target refuses anyway (TEST-NET address vs the add floor)

In a test that a remote message cannot trigger an admin action, every
payload must name an action that WOULD succeed if a deputy carried it
out. On #650 the admin-shaped add-address payload pointed at 192.0.2.7
(TEST-NET), which the bootstrap add floor (`special_use_host`, ADR-0052
rule 2) refuses whoever calls it, so that payload proved nothing.
A private host (10.x) is admitted.

**Why:** a negative test only means something when the same action,
made through the legitimate path, would change the state. That is the
positive control, and it has to use the same argument the attack carries.

**How to apply:** for each payload a negative test sends, run the same
call through the real port as a control, and assert that it is applied
(`Added`/`Set`), not merely that it does not error. A related point
from the same PR: when a baseline is taken while the remote peer is
already able to send, a deputy can act before the baseline. Gate the
sender (here: untrusted until the case trusts it) so that the baseline
precedes every hand-off.

*Observed 2026-11-12 (p2p-network-dev)*
