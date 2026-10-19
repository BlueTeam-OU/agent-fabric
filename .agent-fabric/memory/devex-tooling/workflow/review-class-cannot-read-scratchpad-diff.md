---
role: "devex-tooling"
class: workflow
topic: "review-class-cannot-read-scratchpad-diff"
description: "A review brief's diff file in the session scratchpad is refused to the review class; hunks only in a patch go unreviewed"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cc0e63297a2dbf59
---

## A review brief's diff file in the session scratchpad is refused to the review class; hunks only in a patch go unreviewed

The code-review class's guard refuses to read a `diff:` file under the parent session's scratchpad (j119, 2026-10-13: "the review guard refused the scratchpad path"). It falls back to `git show` of the committed range, so a hunk that exists only as an outside-entry patch (tests/test_pr_counts.py) is never seen, and the review reports it as missing tests.

**Why:** the review is blind and read-only; the guard limits what it may open.

**How to apply:** brief the review on the committed range (base..head) in the repository. Quote an outside-entry patch's hunks in the brief's text, or name in the brief that it travels separately, so the review neither misses it nor flags its absence. Related: [[test-arm-policy-outside-entry]].

*References: test-arm-policy-outside-entry*

*Observed 2026-10-13 (devex-tooling)*
