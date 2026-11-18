---
role: "devex-tooling"
class: solution
topic: "compliance-exemption-reads-every-comment"
description: "a new fabric-pr comment can read as a compliance exemption; pr_compliance greps every comment with the project's phrases"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d30a5a4695896884
---

## a new fabric-pr comment can read as a compliance exemption; pr_compliance greps every comment with the project's phrases

pr_compliance.row greps the PR body and every comment with the project's `exemption` regex (gzapp: "arming basis",
"owner.?s word", "dequeue", … no word boundary). Any comment a fabric-pr verb posts can match by accident:
"Disarming basis:" did (#545 round 1 F2), and a disarm basis on another session's PR must carry "the owner's word".
Fix is on the reader's side by prefix, not in the regex: `common.DISARMING_BASIS`, written by disarm.py, dropped by
pr_compliance (18e148e1). A new verb that posts a comment: give it a prefix in common and exclude it the same way.

Testing part-way failures in a verb whose main() catches every Exception as exit 2: a case that asserts only the exit
code survives deleting the specific except — pin the specific message and the writes made (7e441916).

*Anchors: `tools/fabric/github/common.py::DISARMING_BASIS`, `tools/fabric/github/pr_compliance.py::DISARMING_BASIS`*

*Observed 2026-11-10 (devex-tooling)*
