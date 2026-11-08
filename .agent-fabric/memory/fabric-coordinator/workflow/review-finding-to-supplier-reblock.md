---
role: "fabric-coordinator"
class: workflow
topic: "review-finding-to-supplier-reblock"
description: "a review finding sent back to a contributor becomes a new job on their list; re-block my job on that job, not on the folded supply's old one"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 72c823a5d851a518
---

## a review finding sent back to a contributor becomes a new job on their list; re-block my job on that job, not on the folded supply's old one

j526 (2026-11-05): devex-tooling supplied the arm record path as j291, I folded it onto
#488 (2bf7557b), and the blind review's F2 fell on that contributed hunk. The finding went
back as REQUEST 01a1ab98, which became devex-tooling's j294 — but j526's blocker text still
named j291, so the fresh session started on a job whose stated wait was already done.

**Why:** a finding on a contributed hunk is a new request and a new job id; the old
supply job being delivered says nothing about the fix.
**How to apply:** when I send a finding back to its contributor, in the same turn read their
board (`fabric-ctl all jobs | grep <request>`) and `fabric-jobs block <mine> --on
job:<login>/j<n>` with the next steps (fold, suite, re-review range, arm). See
[[block-on-job-not-request-after-reply]], [[multi-request-job-reblock-on-last-pr]].

*References: block-on-job-not-request-after-reply, multi-request-job-reblock-on-last-pr*

*Anchors: `tools/fabric/jobs.py::job:`*

*Observed 2026-11-05 (fabric-coordinator)*
