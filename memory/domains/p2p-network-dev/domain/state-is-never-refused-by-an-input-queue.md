---
role: "p2p-network-dev"
class: domain
topic: "state-is-never-refused-by-an-input-queue"
description: "A bounded input queue mixing presses with STATE (edits, focus): refuse only presses, coalesce state in place, hold nothing aside; three #170 rounds came from violating this"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 0bf04c0b3388ed35
---

## A bounded input queue mixing presses with STATE (edits, focus): refuse only presses, coalesce state in place, hold nothing aside; three #170 rounds came from violating this

#170 (ui-slint) went three review rounds on ONE invariant: input resolves in the person's order and nothing typed is lost. Each round's fix created the next instance:
- R1: a refused focus change left stale state. Fix: focus is never refused, but the fix coalesced it by retain-and-append.
- R2: retain-and-append MOVED focus past later selections, so a conversation never shown with focus was read. A refused edit, held aside as a "dirty draft" and reported first, let a queued send carry later text.
- R3: reporting the dirty draft last instead dropped it when a queued Select changed the conversation.
The fix that ended the loop changed the data model: an edit is STATE like focus, so it is never refused and stays in the queue.

The rule:
- In a bounded queue, refuse only presses (inputs that can be repeated).
- State inputs (an edit, a focus change) are never refused. They coalesce IN PLACE only, into an entry whose replacement changes what no input between them resolves to: the last input for that key.
- Nothing the person did is held outside the queue.
- The bound then comes from the alternation: state entries ≤ the other entries + 1. Here that is 4 × cap + 3, pinned exactly by a test.

**Why:** every out-of-queue holder or moving coalescer reorders an input relative to another. Each patch fixed the trace a reviewer named and broke an adjacent one.

**How to apply:** for any queue that mixes presses and state (UI, a command channel), write the order rule first. At the second same-invariant finding, apply [[review-loop-same-invariant-escalate]]: enumerate every coalesce, refuse and hold-aside path and change the model, not the site.

*References: review-loop-same-invariant-escalate*

*Observed 2026-10-02 (p2p-network-dev)*
