---
role: "python-dev"
class: workflow
topic: "carry-branches-one-pr-j133"
description: "j133 #568 — carrying three delivered-but-unmerged branches as one PR; skip-list conflict, review post, arm with defer"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d6c741f92c1f1ebf
---

## j133 #568 — carrying three delivered-but-unmerged branches as one PR; skip-list conflict, review post, arm with defer

#568 (3 work, 0 fix) carried the j62/j63/j64 branches by cherry-pick; the only conflict was tests/stripped_skip.txt (the j62 branch had left its line), resolved to an empty list. Stripped check: `TMPDIR=/var/tmp/<x> python3 tests/stripped_run.py . --skip-list tests/stripped_skip.txt <files>`, then rmdir the dir.

**Why:** the review class returns its report as a message with every line indented; I first wrote a condensed copy and `fabric-pr post-review` was denied as Self-Approval. The same text, dedented only, posted at once. A P3 on a coordinator-owned file blocks arm until `--defer "<head8>:F1" "<why>"`; arm itself needs the owner's word when I have not been told to arm.
**How to apply:** after a review hand-back, Write the report verbatim (dedent only) before posting; send the coordinator the doc point in the merge INFO; close the job with `owner/repo#N` (bare `pr:N` is refused). See [[review-post-shape-j91]].

*References: review-post-shape-j91*

*Anchors: `tests/stripped_skip.txt::Files red on a stripped copy`*

*Observed 2026-11-12 (python-dev)*
