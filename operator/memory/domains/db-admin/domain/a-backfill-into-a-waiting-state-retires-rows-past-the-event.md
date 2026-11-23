---
role: "db-admin"
class: domain
topic: "a-backfill-into-a-waiting-state-retires-rows-past-the-event"
description: "Before a migration backfills rows into a waiting state whose only exit is a future writer event (await boarding, await approval), retire the rows that already passed that event; derive the list from every later state, not the spec's"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 95a51ba0ba643570
---

## Before a migration backfills rows into a waiting state whose only exit is a future writer event (await boarding, await approval), retire the rows that already passed that event; derive the list from every later state, not the spec's

0024 (gzapp, 2026-10-25) added the state `awaiting_boarding` to
stop_demands. Its only exit is the boarding CAS. The first draft moved
every unbound open dropoff into it, as the caller's spec asked. A
dropoff whose leg had already boarded then sat in a state nothing would
ever leave: the event that releases it had passed. The rows are
well-formed, so no CHECK refuses them. Codex found it on #1159, and the
review class judged it real. The fix is a retire UPDATE that runs before
the generic one. It sets the past-event rows to a terminal state
(cancelled, with `resolved_at = GREATEST(now(), created_at)` so the
resolution-order CHECK holds).

The caller's list of "already passed" states was boarded and alighting.
It missed completed. Walking every state after the event, not the list
in the request, is what found it. A mutation that dropped `completed`
turned the backfill test red.

**How to apply:** this goes with [[widening-a-pairing-check-needs-the-old-rows-moved]].
The value a backfill writes must be true for each row's history, not
just for the CHECK. For a waiting state, ask what releases it and which
existing rows have already seen that event. Retire those first. The
test covers one row on each side of the event, including a row with no
recorded state.

*References: widening-a-pairing-check-needs-the-old-rows-moved*

*Observed 2026-10-25 (db-admin)*
