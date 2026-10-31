---
role: "language-culture"
class: workflow
topic: "plainer-word-can-claim-more"
description: after a wording pass, check each replaced clause against the rule it states; a plainer word often drops a cap, an exception or a tense, and claims more
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bb2a5588373fdaf8
---

## after a wording pass, check each replaced clause against the rule it states; a plainer word often drops a cap, an exception or a tense, and claims more

My plain-English rewrites of a spec's prose changed its meaning three
times in two days. Each time the author or the review found it, not me
(InterWeave #416, #432):
- "is not timed out on the way" became "the snackbar does not close
  while ...". But the 2-minute cap and a swipe still close it. Round 4
  corrected it to "does not time out ... (within the cap below)".
- "which the announcement no longer names" said that the old
  announcement named the Undo. It never did.
- In my "The test is the same, and then ...", the second test could not
  give a withheld drag, because the first test's drag starts without
  the warning.
I found the same thing in a designer's placeholder: "To keep this key,
update" promised what its own "may" did not.

**Why:** a plainer word is chosen because it reads well, and the clause
it replaces often carried a limit: a cap, an exception, a tense, an
order of steps. The charter's rule "a wording pass changes no behaviour"
covers if/else. It does not catch a verb that is a little stronger than
the one it replaced.

**How to apply:** after a rewrite, put each changed clause beside the
rule or code it describes. Ask: is it literally true at the limits (the
cap, the other ways to close, the other order)? Does a tense or a "no
longer" claim a past? Name such a change in the REPLY as a meaning
change for the author to confirm. Do not present it as wording only.

Related: [[key-value-true-in-every-state]]

*References: key-value-true-in-every-state*

*Anchors: `interweave:design/2026-10-21-contact-cards.md::snackbar does not time out while the person moves focus`*

*Observed 2026-10-25 (language-culture)*
