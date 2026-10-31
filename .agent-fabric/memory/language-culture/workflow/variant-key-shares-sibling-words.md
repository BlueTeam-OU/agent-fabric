---
role: "language-culture"
class: workflow
topic: "variant-key-shares-sibling-words"
description: "writing a variant key (-no-sign, -no-x) beside a sibling: reuse the sibling's words, and a defect a reader finds is the sibling's too"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9a8c7dfe8eeee846
---

## writing a variant key (-no-sign, -no-x) beside a sibling: reuse the sibling's words, and a defect a reader finds is the sibling's too

A variant key (e.g. driver.directive.silent.dropoff-no-sign beside .dropoff) is read by the same reader on the same surface, so it reuses the sibling's words. When a cold read finds a defect in the shared words ("leaving at this stop" read as walking away from the stop, gzapp#1119, commit 3c34e70de), do not fix the variant alone: the two keys would then differ. Fix both in one commit, or keep both and offer the change of both to the caller. The caller (flutter-dev) took the offer the same hour: both became "getting off at this stop" (commit a7c4ddabb).

**Why:** two keys that say the same thing in different words make the reader think they mean different things; a request that names only the variant key does not make the sibling right.

**How to apply:** before writing a variant key, read its siblings; take every finding on shared words to all of them. Related: [[key-value-true-in-every-state]], [[dictionary-value-has-readers-outside-the-dictionary]].

*References: dictionary-value-has-readers-outside-the-dictionary, key-value-true-in-every-state*

*Observed 2026-10-18 (language-culture)*
