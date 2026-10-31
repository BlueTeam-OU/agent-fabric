---
role: "fabric-coordinator"
class: intersection
topic: "gate-output-unknown-not-zero"
description: A fabric reader or gate whose output others parse prints a distinct unknown when a lookup fails, never 0, none or pass; each failure path has a test and the fields are a documented contract
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 42a81452441fb297
---

## A fabric reader or gate whose output others parse prints a distinct unknown when a lookup fails, never 0, none or pass; each failure path has a test and the fields are a documented contract

A review-status reader printed "unresolved threads : 0" when its threads query failed, while a project's arm script gated a security boundary on that line. A trimmed report also lost its coverage line. The fix each time was an explicit "unknown" and a contract for the fields.

**Why:** a default meant for people reads as a pass to a machine consumer.
**How to apply:** when writing or reviewing a reader that a gate consumes, test the failure path for an unknown output and document the field names. Related: [[lint-overreport-not-model]].

*References: lint-overreport-not-model*

*Observed 2026-10-22 (fabric-coordinator)*
