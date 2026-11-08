---
role: "devex-tooling"
class: solution
topic: "arm-record-unreadable-falls-back"
description: "arm and pr-gate read an unreadable record decision (head tree, record_paths) as \"no record\", every gate applying — never exit 2"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f58c79a893371eb8
---

## arm and pr-gate read an unreadable record decision (head tree, record_paths) as "no record", every gate applying — never exit 2

fabric-pr arm's record-path decision (record_pr over head_modes and load_record_rules) catches Unanswered,
says "whether it is a record PR could not be read (...): judged as any other" on stdout, and continues with
record = False, as pr-gate's record_of does (5338db1f, #488 round 1 F2). A relaxing path that cannot be read
falls to the side that keeps every gate; exit 2 there left a reviewed PR unarmable and the two tools disagreeing.
arm's stdout holds what each gate found; stderr only a refusal or an unanswered question.

*Observed 2026-11-05 (devex-tooling)*
