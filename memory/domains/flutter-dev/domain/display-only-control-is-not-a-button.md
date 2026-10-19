---
role: "flutter-dev"
class: domain
topic: "display-only-control-is-not-a-button"
description: A control that only shows something (a compass, a status) must not be exposed to the screen reader as a button, and its tooltip must not merely repeat its label.
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d59382c3311a8017
---

## A control that only shows something (a compass, a status) must not be exposed to the screen reader as a button, and its tooltip must not merely repeat its label.

Both locale holders, independently and from a cold screen-reader pass,
raised the same thing on the passenger map's compass (a 48 dp round
chrome control that does nothing on tap): announced as a button, a
listener hears "Compass, button", presses it, and cannot tell a dead
button from their own mistake. No label fixes that — the ROLE adds it.
The ge holder added: a long-press tooltip that repeats the label tells
the listener nothing; and if a live value is ever exposed, it updates on
focus or when it crosses to another named point, never per degree.

**How to apply:** for chrome that sits beside real actions but does not
act, give it image/status semantics (`Semantics(image: true, …)` or
`excludeSemantics` on the tap wrapper, no `button: true`), name it with a
noun rather than the neighbours' verb form, and either drop the tooltip
or give it its own sentence. Check it in the semantics tree in a widget
test, not only visually.

*Observed 2026-10-18 (flutter-dev)*
