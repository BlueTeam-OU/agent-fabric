---
role: "ux-designer"
class: domain
topic: "client-estimate-never-denies"
description: A client never disables a choice on its own estimate of server state (its clock, a cache); it offers the choice, lets the server refuse, and designs the refused state; a hint may mark, never deny
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6d84b564092f9b23
---

## A client never disables a choice on its own estimate of server state (its clock, a cache); it offers the choice, lets the server refuse, and designs the refused state; a hint may mark, never deny

My advice for gzapp's calibration tile picker applied this rule on one
side and broke it on the other: tiles older than 47 h stayed offered
"since the client cannot know about roll-ups", yet tiles not yet closed
by the browser's clock were withheld (disabled slots, capped date). A
browser clock behind the server's then denied tiles the server serves.
gzapp ADR-017 §5 rule 14 states it: the device clock may decide when to
ask the server, never deny.
**Why:** gzapp #1186 review (2026-10-27), recorded as an accepted
deviation from my 01a1761f.
**How to apply:** for every disabled or hidden choice, ask what decides
it; if the authority is the server, offer the choice, propose the
likely one first, show "available from …" beside it as a hint, and
specify the refused state (what it says, the way to a valid choice).
Related: [[unknown-is-not-a-default]], [[refused-action-and-refused-undo]]

*References: refused-action-and-refused-undo, unknown-is-not-a-default*

*Observed 2026-10-31 (ux-designer)*
