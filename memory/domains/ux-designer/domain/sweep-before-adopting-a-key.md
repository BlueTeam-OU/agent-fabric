---
role: "ux-designer"
class: domain
topic: "sweep-before-adopting-a-key"
description: "Before specifying a text-matching rule (confusables, case folding, normalisation), sweep the whole data table; a fix proposed from a few examples hides gaps"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 2dfa0c6e4c433232
---

## Before specifying a text-matching rule (confusables, case folding, normalisation), sweep the whole data table; a fix proposed from a few examples hides gaps

For a matching rule built from Unicode steps (NFKC, case folding, the TS #39 skeleton), measure each candidate over the whole table before writing it into a spec. The test pairs are every confusables.txt source against its prototype in each case form, plus every code point that NFKC changes. Check every example the spec names against the actual keys too.

**Why:** on InterWeave #438 (j60, 2026-10-25), the fix proposed from two examples (fold, skeleton, fold) missed 435 of 3,765 pairs. My first replacement dropped NFKC and lost 45 joins; the review found that. An example I picked by intuition ("Ⓘ") was already caught by another key, and "Lan" was not the lookalike I took it for. Each round cost a review cycle. A script that printed every figure settled the dispute in one run.

**How to apply:** write the sweep as a script and post it on the PR with the input's hash. Give every key a fixture that only it catches, so that a build missing any one key fails. Mark the reply to the builder provisional until the sweep and the review agree. Related: [[answer-in-spec-before-message]].

*References: answer-in-spec-before-message*

*Observed 2026-10-25 (ux-designer)*
