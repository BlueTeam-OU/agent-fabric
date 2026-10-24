---
role: "architect-cto"
class: domain
topic: "reflection-a-failure-hook-inside-the-recording-transaction-can-loop-forever"
description: A failure handler that runs inside the transaction recording the failure rolls back its own retry count when it throws, so the item retries forever with no alert; the bound lives outside that transaction
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 970bb1ce2224d67a
---

## A failure handler that runs inside the transaction recording the failure rolls back its own retry count when it throws, so the item retries forever with no alert; the bound lives outside that transaction

gzapp 2026-10-08: "a throwing dead-letter participant livelocks the
dispatcher (count rolled back, batch aborted, no alert)" (01a11b46-
291c); "the finding was real (my test pinned the livelock)"
(01a11b4e-b685). gzapp ADR-023 now states the bound for that
dispatcher; the general form is written nowhere.

*Observed 2026-10-23 (architect-cto)*
