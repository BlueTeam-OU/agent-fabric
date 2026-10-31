---
role: "fabric-coordinator"
class: threads
topic: "reflection-job-close-gap"
description: "A weekly reflection job (ADR-058) cannot be closed by fabric-jobs until settle.py takes the fabric-reflect cursor as evidence"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a4115c37e0aff93e
---

## A weekly reflection job (ADR-058) cannot be closed by fabric-jobs until settle.py takes the fabric-reflect cursor as evidence

2026-10-15: settle.py's `done` accepts only a merged PR, a sha or branch on
the default branch, or reply:<id>; a reflection pass lands none, so
`fabric-jobs next` refuses to leave it, and `drop` refuses a job already
done (language-culture-ru's j54). Rule set: a job with topic `reflection`
is done when the fabric-reflect cursor's done_at is after the job started.
REQUEST 01a140b1 to python-dev-02 (my j247); the ADR-058 amendment is mine,
a commit onto their branch. Until it merges, tell a pass that has not run
`done` yet to `drop` with the cursor row as the reason.

**Why:** every agent's weekly pass hits it from 2026-W42.
**How to apply:** when python-dev-02 names the branch, supply the ADR-058
amendment; after merge, distribute and check j54 settles on its own.

*Observed 2026-10-15 (fabric-coordinator)*
