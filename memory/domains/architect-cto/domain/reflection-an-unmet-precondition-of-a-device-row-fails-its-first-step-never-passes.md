---
role: "architect-cto"
class: domain
topic: "reflection-an-unmet-precondition-of-a-device-row-fails-its-first-step-never-passes"
description: "A device row whose precondition only the owner can establish (a wipe, a pairing, a phone placed) asserts that precondition in its first step so an unmet one fails, never passes; the rows that need no owner's act run first, and the…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d4baea5aeee9f794
---

## A device row whose precondition only the owner can establish (a wipe, a pairing, a phone placed) asserts that precondition in its first step so an unmet one fails, never passes; the rows that need no owner's act run first, and the destructive step waits for the owner's word even when it was the agreed order

Stage 21's two-phone rows (2026-10-24): "fresh" meant `pm clear` on a
shared phone, which p2p-network-dev-02 would not run without the
owner's word. They reversed the agreed order and ran row 1 (no wipe)
first; the pair case was written so a phone that was not cleared
"shows up as a failure, never as a pass" (trusted before the trust
step); and the one remaining question to the owner was the wipe alone.
Row 2 then ran three times on cleared data in the hour after the word.

**Why:** a precondition the run cannot make true is the one it can
most easily assume; a row that passes on a stale profile proves the
stale profile, and a destructive act on a shared device is the owner's
whichever order a plan agreed.

**How to apply:** when planning device rows, split them into those
that need an owner's act and those that do not, run the second group
first, and put the owner one question when the act is the only thing
left; require every owner-made precondition to be asserted by the
row's first step with a named failure; a run file names the act and
the word it ran under.

*Observed 2026-10-25 (architect-cto)*
