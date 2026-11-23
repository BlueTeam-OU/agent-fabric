---
role: "ux-designer"
class: domain
topic: "bounded-loss-is-a-choice"
description: "when a memory bound must drop something the person cannot get back, no drop order fixes it; make crossing the bound the person's informed choice"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 61ee7120347e3bfc
---

## when a memory bound must drop something the person cannot get back, no drop order fixes it; make crossing the bound the person's informed choice

When a bound has to drop content that has no other copy (read-unkept messages held only in RAM),
look for which drop order loses nothing. If none does, make crossing the bound the person's
choice, with the consequence stated before they commit, and mark where content went.

Writing a cleverer drop order instead is a trap. On InterWeave #472 (start window, j74), "drop
the end furthest from the person" still dropped the newest rows when paging up (re-review F11).
It also let one conversation push another's rows out (F12). Two review rounds went on that rule.
What held was today's order kept as is, with a limit row asking before paging past the bound.

**Why:** with direction-of-travel paging, every order loses the end the person came from.

**How to apply:** first ask whether the loss is avoidable. If it is not, design the prompt and the
marker, not the order. Related: [[undo-by-reverse-not-deferral]], [[review-fixes-open-new-questions]].

*References: review-fixes-open-new-questions, undo-by-reverse-not-deferral*

*Observed 2026-10-27 (ux-designer)*
