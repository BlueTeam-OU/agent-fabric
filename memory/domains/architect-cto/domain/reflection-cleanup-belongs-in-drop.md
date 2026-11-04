---
role: "architect-cto"
class: domain
topic: "reflection-cleanup-belongs-in-drop"
description: In Rust on tokio, dropping a JoinHandle detaches the task and does not abort it; cleanup that must run on every exit path belongs in impl Drop, not in a shutdown method the caller must remember, and an abort is observable with no new…
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 5a5ab2d8716d97fa
---

## In Rust on tokio, dropping a JoinHandle detaches the task and does not abort it; cleanup that must run on every exit path belongs in impl Drop, not in a shutdown method the caller must remember, and an abort is observable with no new export by wrapping each test task in a future that records its own drop

InterWeave ADR-0053's vendored mDNS patch, 2026-09-25: "Drop covers
every path a behaviour leaves by… a method the caller must remember
is the shape that produced this defect" (01a0dbbf-c364); "an aborted
task's future is dropped at its next scheduling point, a detached one's
is not, so the drop IS the abort, observed" (01a0dbc5-9065). The ADR
records the patch; the field rule is written nowhere.

*Observed 2026-10-23 (architect-cto)*
