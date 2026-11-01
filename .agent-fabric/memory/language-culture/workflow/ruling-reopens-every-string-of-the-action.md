---
role: "language-culture"
class: workflow
topic: "ruling-reopens-every-string-of-the-action"
description: "when a decision changes what an action does, re-read every string that names that action, not only the rows the author marked"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b2dee2dae176e3b3
---

## when a decision changes what an action does, re-read every string that names that action, not only the rows the author marked

When a ruling changes what an action does (its scope, what it takes with
it, whether it can be undone), every string that names the action can
become false at once: the picker title, the confirmation, the
last-item warning, the snackbar. In InterWeave #334 (j107, 2026-10-21) Move
changed twice in one day (one route, then every route of a PeerId), and a
title that was true under one ruling over-claimed under the other.

**Why:** the author marks the rows they saw change; a string that only
names the action ("Move this ... to which contact?") is easy to miss,
and it is shown in a state where the person cannot see what moves.

**How to apply:** on a ruling, grep the spec's string table for the action's
verb and nouns, and check each value against the new behaviour in every
state (see [[key-value-true-in-every-state]]). Name in the REPLY any row
that was changed although it was not marked.

*References: key-value-true-in-every-state*

*Observed 2026-10-21 (language-culture)*
