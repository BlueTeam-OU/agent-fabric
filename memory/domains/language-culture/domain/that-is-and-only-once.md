---
role: "language-culture"
class: domain
topic: "that-is-and-only-once"
description: "two English phrases that read two ways in design/ prose — \"only once\" and \"X, that is Y\""
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 2f15aaa51560a8ea
---

## two English phrases that read two ways in design/ prose — "only once" and "X, that is Y"

Two phrases read two ways for a second-language reader of a spec or a test step:

- "only once <event>" means "only after" or "a single time". Write "only after" when the clause is about order (PR #609, identity note §10 item 15: "a launch runs a start only once the Service has ended").
- "After X, that is Y" can mean "after X, focus is on Y" or "in other words". Write the verb out: "after Try again it stays on Try again" (#609, §8, commit 465559c1).

**Why:** both were in text that tells a tester which run to make, and the author confirmed the reading only after it was asked.
**How to apply:** grep a design/ change for "only once" and ", that is" on the first pass. Change the phrase only where the text around it settles the reading. Otherwise ask the author. See [[interweave-spec-prose-wording]].

A third phrase, found on #700 (j338, commit 15fe6c082): "So does X" after "Y does nothing" can read as "X does something". Write "X does nothing too". On the same pass, the "only once" grep was skipped, and the cold read had to catch the phrase ("protects that person only once R4 is open"). Run the grep every time.

A related lesson from the same PR: when the PR head moves during a pass and a merge conflicts, reword the author's new sentences in a separate commit after the merge, not inside the merge commit, and say so in the reply.

*References: interweave-spec-prose-wording*

*Observed 2026-11-17 (language-culture)*
