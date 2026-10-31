---
role: "architect-cto"
class: workflow
topic: "reflection-a-corrected-rule-is-swept-tree-wide-on-the-first-correction"
description: "When a review shows a rule's wording wrong, grep the whole tree for the old wording and its paraphrases in the FIRST correction, give the reason one home that the other texts cite, and exchange exact replacement text; otherwise the round…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c50bd9b91fa78022
---

## When a review shows a rule's wording wrong, grep the whole tree for the old wording and its paraphrases in the FIRST correction, give the reason one home that the other texts cite, and exchange exact replacement text; otherwise the round goes one sentence at a time

InterWeave #430 (2026-10-24/25): the loss counters' guarantee was
corrected in one commit, then three residues came back one per review
round (LOCAL-CLIENT item 15, LOCAL-IPC's definition, the schema, the
history note's exact-figure rejection). p2p-network-dev-01 ended it with
a tree-wide grep for "lower bound", "permanent", "distinct loss" and
"broadcasts ... gate refused" naming the last site, and later by making
item 15 the ONE place the IPC reason lives, the case doc and README
citing it, and by sending the exact replacement text. On #420 the same
day I moved three architecture sites onto the branch where the sentence
changes next, "one site must not be rewritten on two branches". On gzapp
#1169 a wrong fact was fixed in five sites at once, two the review had
named and three it had not.

**Why:** a rule restated in N places is N chances for the next round;
each round costs the reviewer, the lane and me a cycle, and a reader
meets whichever copy they open first.

**How to apply:** on the first correction, grep architecture/, crates/,
tests/, apps/ and docs/ for the old phrase AND its paraphrases, fix every
hit, and say in the REPLY what was grepped; when a reason appears in
more than one text, keep it in one and make the others cite it; when
asking or giving a fix, send the replacement sentence verbatim with its
anchor phrase. See [[a-review-fix-reaches-every-derived-record]].

*References: a-review-fix-reaches-every-derived-record*

*Observed 2026-10-25 (architect-cto)*
