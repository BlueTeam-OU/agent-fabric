---
role: "ux-designer"
class: domain
topic: "acceptance-trigger-keeps-focus"
description: An acceptance check for a focus row must say how the state is forced, by a route that leaves focus where that row needs it
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - db99eb462c45c2e4
---

## An acceptance check for a focus row must say how the state is forced, by a route that leaves focus where that row needs it

A focus check is only as good as its trigger. In gzapp#1251 (admin map note, design/2026-11-10-admin-map-unavailable-state.md) three review rounds each found a check whose trigger moved focus away from where its row needed it, so the check silently tested a different row:
- pressing + or the zoom control moves focus to the map (F12), not the open details (F11);
- the header palette control moves focus out of the map (F8, not F6);
- a keyboard pan needs canvas focus and a pointer drag focuses the canvas; only a mouse-wheel zoom without clicking leaves focus in a popup field.

**Why:** every one passed review of the rows and only failed when someone traced how a tester would actually reach the state.

**How to apply:** for each focus check, write the trigger and state where focus is at the moment the state changes; for each focus row, check the route against the row's "when" cell. Also give an observable stop (e.g. "until the network log shows a new tile request"), not "pan" or "wait". See [[positions-details-only-on-map]].

*References: positions-details-only-on-map*

*Observed 2026-11-11 (ux-designer)*
