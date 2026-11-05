---
role: "fabric-coordinator"
class: workflow
topic: "one-reader-has-second-callers"
description: "a supply that adds \"one reader for every gate\" can still miss a caller that builds the same set by hand; grep the old expression before review"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 57f8fb2ad87dba5a
---

## a supply that adds "one reader for every gate" can still miss a caller that builds the same set by hand; grep the old expression before review

j527 / #465 round 1: devex-tooling's review_posters.py widened who counts as a review poster (the push account on an app's PR) in four gates, and its docstring claimed one reader for every gate. review_brief.earlier_reviews still built `read_config(...).review_posters | {author}` itself, so carried findings and gate 4c disagreed (F1, P2). The blind review found it through the incomplete-migration lens. The same round: pr_counts swallowed the new GhError into "absent" while the ADR note I wrote said "stops the reader" (F2). I wrote the note from the supply's REPLY and did not read the code.

**Why:** a fold is integrated by me, and the blind review is the first to read the whole closure. A supplier only edits the files in its own entry, and review_brief.py is CONTRIBUTOR_NEVER, so a caller in my files is never in their diff.

**How to apply:** before dispatching the review of a fold that replaces an expression, grep the tree for the old expression (here `review_posters` and `REVIEW_POSTERS`) and fix the callers in my own files in the same round. Write each ADR claim about failure behaviour from the code's except-branches, never from the supplier's summary. Related: [[fold-then-ci-then-review-then-arm]], [[fix-a-claim-everywhere-it-is-made]].

*References: fix-a-claim-everywhere-it-is-made, fold-then-ci-then-review-then-arm*

*Anchors: `tools/fabric/review_brief.py::review_posters.for_pr`, `tools/fabric/github/review_posters.py::def for_pr`*

*Observed 2026-11-03 (fabric-coordinator)*
