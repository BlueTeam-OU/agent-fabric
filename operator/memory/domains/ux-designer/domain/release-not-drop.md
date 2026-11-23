---
role: "ux-designer"
class: domain
topic: "release-not-drop"
description: "a memory ceiling over rows that keep a stored copy is a silent release with load-on-reach gaps, never the limit row"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 8788f71b3c27ac09
---

## a memory ceiling over rows that keep a stored copy is a silent release with load-on-reach gaps, never the limit row

When a memory bound covers content that is still stored (unread, kept), releasing it loses nothing,
so the person is not asked: a warning claiming an irreversible loss would be false. Released runs
become gaps that load from either side as an edge does. And a bound-full prompt is skipped wherever
the rows still to load hold nothing that would be lost (known from an existing count), or the
person is asked to accept a loss that would not happen (PR #488, rounds 1 and 5).
**Why:** the review of #488 found the U4 "a page early" and the kept-only gap both asking for no loss.
**How to apply:** any bounded list design; pair with [[bounded-loss-is-a-choice]].

*References: bounded-loss-is-a-choice*

*Observed 2026-10-27 (ux-designer)*
