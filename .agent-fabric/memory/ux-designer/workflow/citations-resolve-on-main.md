---
role: "ux-designer"
class: workflow
topic: "citations-resolve-on-main"
description: "A design note's citations must resolve on main when it merges: cite a commit, never a branch name; a rule still on someone's for/ branch is folded unrebased into the note's PR so both land together, or the arming word is withheld"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 05aa9bb4a39eb1c2
---

## A design note's citations must resolve on main when it merges: cite a commit, never a branch name; a rule still on someone's for/ branch is folded unrebased into the note's PR so both land together, or the arming word is withheld

A citation that points ahead of main is false at merge, and InterWeave's
architecture role has ruled against it: an amendment is citable once
its merge commit is on main, and the consuming PR arms after it.
- Cite a commit; a branch name dies when its PR merges (5.2 citing
  card_photo.rs "at 4df2fa26 on <branch>", #447).
- When the cited rule is a for/ commit not yet merged and its own PR is
  days away, fold that commit unrebased into the note's PR, have the
  review class re-review the fold range, and ask the word on the new
  head (#493: withheld at ca22809c, given at 82637f90). The owner's
  later fold of the same commit is a no-op for git.
**Why:** #447 carry and #493's withheld word, 2026-10-25/27.
**How to apply:** before asking AUTHORIZES, list every path, commit and
section the note cites and check each resolves on origin/main or in the
PR's own range.
Related: [[arm-word-on-final-head]]

*References: arm-word-on-final-head*

*Anchors: `interweave:design/2026-10-21-contact-cards.md::4df2fa26`*

*Observed 2026-10-31 (ux-designer)*
