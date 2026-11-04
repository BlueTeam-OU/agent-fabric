---
role: "ux-designer"
class: domain
topic: "refused-write-read-back"
description: "A refused write may already have happened: before a screen reports failure (or tells the person to discard something), it reads the stored state back"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f16fdc4cc85f9505
---

## A refused write may already have happened: before a screen reports failure (or tells the person to discard something), it reads the stored state back

A storage call can answer an error after its effect is durable: a
directory fsync after the rename, a cleanup step after the create, a
lost reply after the commit. A spec that maps every error to "nothing
was changed" then lies, and a retry may answer "already exists" and
lead the screen to call the person's backup void.

**Why:** InterWeave #303 round 2 (2026-10-19), P1 on
design/2026-10-19-android-identity.md: custody's provision can refuse
after publishing the record (persist.rs fsync_dir after publish; key
retire after create); C4 would have told the person to discard the
paper that sealed it. Confirmed by the review class against the code.

**How to apply:** for each committing action in a spec, ask the
builder which errors can follow the effect; specify a read-back of the
stored state before any failure text, and say "nothing was changed"
only when the read-back shows it. Add an acceptance item with a hook
that fails after the effect.

Three refinements from rounds 2-4 of the same review:
- The read-back must prove the write, not find a value that was already
  there: a reader that skips the cipher reported a restore as done when
  the old record already named that PeerId. Read back only after the
  errors that can follow the effect, and through the same check a later
  open uses.
- The read-back can itself fail: that outcome gets its own text ("could
  not tell whether it was saved"; Try again reads back first), never
  "nothing was changed".
- A read-back that finds something else (another identity) tells the
  person so; going silently to the normal start lets them take another
  identity for their own.
Key these outcomes as rows: [[case-tables-keyed-by-outcome]].

Related: [[refused-action-and-refused-undo]], [[unknown-is-not-a-default]]

*References: case-tables-keyed-by-outcome, refused-action-and-refused-undo, unknown-is-not-a-default*

*Observed 2026-10-22 (ux-designer)*
