---
role: "ux-designer"
class: domain
topic: "late-result-keeps-newer-feedback"
description: "When an action's feedback waits for an asynchronous answer, a newer action's feedback (and its Undo) is never replaced by the late result"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 50677a71e306e64c
---

## When an action's feedback waits for an asynchronous answer, a newer action's feedback (and its Undo) is never replaced by the late result

A single feedback slot (a snackbar, a toast) shared by actions whose
results arrive late needs an ordering rule in the spec. The rule: while
an action waits for its answer, the feedback already shown stays; when
the late answer comes, it replaces nothing the person did after it. If
a newer action's feedback is up, the late result is only announced; if
that has closed, the late result shows its own feedback; if the person
has left the screen, it is only announced.

**Why:** in the InterWeave message-swipe spec (#286, 2026-10-16/17)
four review rounds in a row found a case of this: a late Cancel success
replacing a newer Dismiss snackbar took away that Dismiss's Undo, so the
message was gone for good with no way back.

**How to apply:** for every action whose result is asynchronous, write
its feedback against three cases: no newer feedback, newer feedback
still up, person gone from the screen; and give each an acceptance
check. The destructive-action rule (never one gesture from gone without
a way back) is what the ordering protects.

Related: [[refused-action-and-refused-undo]], [[undo-by-reverse-not-deferral]]

*References: refused-action-and-refused-undo, undo-by-reverse-not-deferral*

*Observed 2026-10-18 (ux-designer)*
