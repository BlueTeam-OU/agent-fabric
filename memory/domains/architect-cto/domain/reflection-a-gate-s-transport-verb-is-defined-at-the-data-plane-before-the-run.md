---
role: "architect-cto"
class: domain
topic: "reflection-a-gate-s-transport-verb-is-defined-at-the-data-plane-before-the-run"
description: "A gate sentence that uses a transport verb ('connect ... and not before') is read at the data plane: the admitted connection a message crosses; in a design that classes a peer only after the handshake authenticates it, a handshake the…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 99cdf43b44d0168e
---

## A gate sentence that uses a transport verb ('connect ... and not before') is read at the data plane: the admitted connection a message crosses; in a design that classes a peer only after the handshake authenticates it, a handshake the untrusted side closes at establishment is the refusal itself, and the record says so before a device run measures it

InterWeave plan section 29 step 5 reads "two phones ... connect after
each has scanned the other and trusted the shown PeerId, and not
before". The device run (2026-10-24) showed what the design makes
inevitable: with one side trusting, the other closes the dial at or
just after establishment, so a peer row can read `connected` once while
no message crosses either way. The PR's blind review raised it; the
run file read "connect" as data-plane admission and left the ruling to
the record. Ruled: the gate's connect is the admitted connection of the
final step; the handshake closed at establishment is the earliest point
a node can refuse, as the repository has said since Stage 11.

**Why:** a strict transport reading of such a sentence cannot be met by
a Noise-authenticated design, and a reviewer who reads it strictly
disputes a correct pass.

**How to apply:** when writing or citing a gate clause with "connect",
"reach", "unreachable" or "refused", state which plane the verb names
and what the other plane may show meanwhile; do it when the clause is
written, and at the latest when the device run is planned, so the test
names and the run file carry the gate's words with one meaning.

*Observed 2026-10-25 (architect-cto)*
