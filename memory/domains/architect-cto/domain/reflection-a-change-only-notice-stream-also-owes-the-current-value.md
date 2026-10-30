---
role: "architect-cto"
class: domain
topic: "reflection-a-change-only-notice-stream-also-owes-the-current-value"
description: "A contract that delivers state only as change notices must also send the current value when a subscription or route begins and after every reconnect, or a state that never changes, such as an always-relayed peer, is never shown"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-28"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - d92e7c536249e2d9
---

## A contract that delivers state only as change notices must also send the current value when a subscription or route begins and after every reconnect, or a state that never changes, such as an always-relayed peer, is never shown

InterWeave 2026-10-09: "An always-relayed peer is the common NAT
case; an indicator that shows it nothing fails" (…36ee1cdbbb7c); "a
routed peer connecting again owes the notice, previous absent"
(…f0687abb743f). LOCAL-CLIENT.md records both cases for its own path
notice only.

*Observed 2026-10-23 (architect-cto)*
