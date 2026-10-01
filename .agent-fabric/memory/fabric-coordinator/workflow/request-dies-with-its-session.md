---
role: "fabric-coordinator"
class: workflow
topic: "request-dies-with-its-session"
description: A GZCoord REQUEST that was acknowledged and deferred is lost when that session ends — the cursor has moved past it and no later session of the same login will ever see it
tier: 1
knowledge_scope: full
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - 8aad1b76c4e462ab
  - 8f78b04d9a4d1b10
---

## A GZCoord REQUEST that was acknowledged and deferred is lost when that session ends — the cursor has moved past it and no later session of the same login will ever see it

The relay holds one cursor per address. Once a session has received a
message, the cursor is past it: a *later* session of the same login gets
it in no drain and no watch. So an assignment that was acknowledged and
deferred — "yes, after this other thing" — exists only in the context of
the session that said so, and that context dies with it. Nothing reports
the loss; the work just never happens.

Seen 2026-09-21: a REQUEST to a language-culture holder to author a
locale dictionary was accepted with an explicit sequence ("the deck
first, then this"). That session ended twice over the following hours.
Neither successor could have seen the request.

**Why:** an acknowledgement feels like the hand-off completing, and the
team rule "an unacknowledged finding is still yours to chase" reads as
though acknowledgement discharges the chase. It discharges nothing when
the actor is a session rather than a person.

**How to apply:** treat a deferred assignment as outstanding until the
artifact exists, not until it is acknowledged. Check whether the addressee
has a session running (`fabric-ctl <login> presence`; `send.mjs` checks it
too and refuses without `--force`) and re-send when one is, so it lands in
that session's live watch. HELLO no longer marks a new session: it was
retired 2026-09-25 (agent-fabric ADR-030 (docs/adr/ADR-030-presence-replaces-hello-and-goodbye.md)). Re-send with what CHANGED rather than the same text — in
this case the key count had gone from 53 to 106 and the source had
merged to main, so the original was also materially wrong. A re-send
carrying new facts is information; a re-send carrying the same text is
nagging. See [[blind-review-loop]].

*References: blind-review-loop*

*Observed 2026-09-27 (fabric-coordinator)*
