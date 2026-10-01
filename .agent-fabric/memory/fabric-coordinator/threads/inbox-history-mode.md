---
role: "fabric-coordinator"
class: threads
topic: "inbox-history-mode"
description: "To do: gzcoord inbox.mjs needs a history-listing mode (a seq range, addressed-to-me only, HELLO/GOODBYE filtered) — an agent planned ~400 --replay calls to read 3808..4200; replay already fetches 500 records per call"
tier: 2
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
  - 871b6a3f62ac6d6d
---

## To do: gzcoord inbox.mjs needs a history-listing mode (a seq range, addressed-to-me only, HELLO/GOODBYE filtered) — an agent planned ~400 --replay calls to read 3808..4200; replay already fetches 500 records per call

Raised by the owner on 2026-09-25, quoting an agent's own plan: "Since
there's no history-listing mode, I'll need to loop --replay calls one at a
time over the range and filter out the HELLO/GOODBYE broadcasts, checking
the TYPE line to find messages actually addressed to me. That's roughly 400
calls covering messages from 3808 through 4200." The owner: "this can be
also a valuable implementation, take note".

What exists: `communication/gzcoord/scripts/inbox.mjs` has `--follow`,
`--wait`, `--held`, `--replay <seq|message-id>`; `replay()` already calls
`/api/messages?limit=500&full=1` and discards all but one record. So a
history mode is one relay call (or a few pages with since_id), not one per
message.

Shape to build: `inbox.mjs --history [--from <seq>] [--to <seq>]` listing,
for this login, the records addressed to it (TO its address, TO-ROLE its
role, or BROADCAST that is not HELLO/GOODBYE) — the same addressee rule and
SPEC §17 handling the watch applies, bodies shown only when addressed.
**HELLO and GOODBYE are always filtered out** (the owner, 2026-09-25: "history
must filter out HELLO and GOODBYE") — no switch to bring them back; presence
is a different question from "what was sent to me".

Measured 2026-09-25: the relay returns at most 500 records per call
(`limit` above 500 is ignored; seq 3509..4359 that day), its ids are UUIDs
and `since_id` pages only forward — so history covers the relay's last 500
records, and a `--from` older than that must be said, not silently shortened.
Existing i18n keys cover the output (`inbox.head`, `replay.title`,
`inbox.others-header`), so no locale dictionary needs new strings.
An attempt to write it on 2026-09-25 was stopped by a safety classifier
mid-edit (nothing landed); not retried in that session. Tooling only: no wire change, so
not a protocol decision (SPEC stays frozen). Belongs in a fabric PR with a
test against the relay fake. See [[request-dies-with-its-session]] — a
history read is also how a session recovers a request its cursor moved past.

*References: request-dies-with-its-session*

*Observed 2026-09-25 (fabric-coordinator)*
