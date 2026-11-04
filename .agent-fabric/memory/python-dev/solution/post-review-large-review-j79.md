---
role: "python-dev"
class: solution
topic: "post-review-large-review-j79"
description: "j79 #370 — how fabric-pr post-review holds a several-hundred-path review (compact block, comment split, rename sources) and the traps met"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 004dbcddeda16199
---

## j79 #370 — how fabric-pr post-review holds a several-hundred-path review (compact block, comment split, rename sources) and the traps met

#370 (post_review.py, review_coverage.py): the coverage block is posted as compact JSON,
bound `MAX_BLOCK_CHARS` 60000; `diff_changes` reads `git diff --name-status -z`
(R/C records carry two paths) and a rename source may be named but is never owed.
A report that would push the review past `MAX_REVIEW_CHARS` is posted first as a PR
comment; the review keeps header, `Finding:`/`Judgement:` lines, block and the comment URL.
A split report with no machine lines is refused (fabric-errors would read zero findings).
The stub size is checked with a 255-char placeholder URL and again with the real one.

**Why:** the gate (`pr_review_status`) reads only the marker and block, so it did not change.
Open for the coordinator: ADR-065 §2 C says the previous report is the review's posted body;
a split review's body no longer holds the prose.

**How to apply:**
- Mutations only after the commit: a `git checkout` mutation check wiped uncommitted edits once.
- A re-review brief is pasted verbatim, never retyped (a hand-retyped hunk came out garbled).
- When a rebase moves the base, the first review's base is no longer an ancestor: re-brief.
- After a job is delivered, even "arm <n>" from the owner needs `fabric-jobs add` +
  `fabric-jobs switch` (the PreToolUse guard refuses `fabric-pr arm` in the old session).
- `test_review_bash_guard_cli` "spins on CPU" can fail under full-suite load; passes alone.

*Anchors: `tools/fabric/github/post_review.py::MACHINE_LINE`, `tools/fabric/github/review_coverage.py::diff_changes`*

*Observed 2026-10-25 (python-dev)*
