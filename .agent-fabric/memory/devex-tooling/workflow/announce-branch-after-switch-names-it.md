---
role: "devex-tooling"
class: workflow
topic: "announce-branch-after-switch-names-it"
description: "Never name a future job's branch in a REPLY before fabric-jobs switch has chosen it — switch derives the name from the job title, not from what you promised"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 62ffaf679a8fe3ef
---

## Never name a future job's branch in a REPLY before fabric-jobs switch has chosen it — switch derives the name from the job title, not from what you promised

On 2026-11-05 I told architect-cto-01 (REPLY 01a1aaa9, the j182 chase) that the branch would be
develop-qzapp/devex-tooling/feat/j182-android-check-skia-pin. `fabric-jobs switch j182` then chose
develop-qzapp/devex-tooling/feat/j182-android-check-job-read-the-committed, built from the job's title. The
acknowledgement named a branch that never existed.

**Why:** a REPLY's branch is the acknowledgement the other agent checks ([[read-branch-and-counts-before-sending]]).
A name typed ahead of switch is a guess.
**How to apply:** for work not yet started, say "the branch follows when the job starts", or run switch first and
copy the name from its output.

*References: read-branch-and-counts-before-sending*

*Anchors: `tools/fabric/jobsparts/branching.py::def branch_name`*

*Observed 2026-11-05 (devex-tooling)*
