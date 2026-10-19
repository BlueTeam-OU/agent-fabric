---
role: "rust-ui-dev"
class: domain
topic: "ui-deferred-input-queue"
description: "When view callbacks queue raw input that is resolved later against the model -- identity not position, never reorder, drop newest, text and focus are state"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 28f0cb9606965d24
---

## When view callbacks queue raw input that is resolved later against the model -- identity not position, never reorder, drop newest, text and focus are state

A UI toolkit callback (Slint's included) runs without the model in hand, so a design where
callbacks only queue raw input and the root later resolves it against the model opens
wrong-action windows. The rules that closed them:

- Record a press by IDENTITY (item key + the action exactly as rendered), never by position;
  emit it only if that same action is still legal at resolve time, else nothing. By position,
  "Retry" pressed then a status update turns index N into Cancel or Unkeep -- a destructive
  action the person never chose. Test: press, then an update that removes the action, yields nothing.
- No queued input ever moves relative to another. Coalesce a new edit only into an edit of the
  same key that is that key's LAST queued input; otherwise append (edit, send, edit must send
  the first edit's text).
- A full queue refuses the NEWEST input, counted; dropping the oldest can drop an edit and keep
  the send after it.
- Text being typed and window focus are state, not refusable events: an edit is never refused,
  and "viewed"/mark-read is a flag resolved after the queue drains, against final focus.

Why it matters: three successive blind review rounds found three instances of the same
reordering invariant; the fix that held was changing the data model, not patching the third.
When a second instance of one invariant appears, redesign so the class cannot occur.

*Observed 2026-10-15 (rust-ui-dev)*
