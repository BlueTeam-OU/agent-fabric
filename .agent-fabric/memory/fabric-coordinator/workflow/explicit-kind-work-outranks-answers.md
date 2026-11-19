---
role: "fabric-coordinator"
class: workflow
topic: "explicit-kind-work-outranks-answers"
description: "a supplied commit with Answers: AND an explicit Kind: work counts as work, not fix — check trailers before folding a contributor's review fixes"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 871ddecd74a9d2fc
---

## a supplied commit with Answers: AND an explicit Kind: work counts as work, not fix — check trailers before folding a contributor's review fixes

A commit that answers a review should carry `Answers: <labels>` and no `Kind` line; the commit-msg hook then stamps `Kind: review-fix` (`tools/fabric/guards/commit_kind.py`, stamp only when no Kind). An explicit `Kind: work` outranks `Answers:` in the gate's count (`tools/fabric/github/commit_class.py`).

Seen 2026-11-13 on #589: python-dev-01's j227 round-1 answers 26745429 and 99fd0cb8 carried both, so the gate read 6 work, 0 fix where it was 4 work, 2 fix; their delivered session's guard refused a reword, so I folded as is and stated the miscount in the PR body and in every status. Their later fix commits (8840a4c7, ec6fe8b1) came right.

**How to apply:** before folding a `for/` supply that answers findings, read `git log --format='%(trailers)'` on its range; a `Kind: work` beside `Answers:` is sent back for a re-push before the fold when the supplier's session still can, else stated in the PR body. Related: [[arming-prs]].

*References: arming-prs*

*Anchors: `tools/fabric/guards/commit_kind.py::review-fix`, `tools/fabric/github/commit_class.py::Kind: work is`*

*Observed 2026-11-13 (fabric-coordinator)*
