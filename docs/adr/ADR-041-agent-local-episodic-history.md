# ADR-041 — Agent-local episodic history: exact messages kept above the transport

**Date:** 2026-10-01
**Status:** Accepted
**Ratified:** owner, 2026-10-01, by the merge of agent-fabric #78 (30c99471), which carried it, as §8 provided
**Decision Makers:** the owner (the design, after a written review of what history the fleet keeps); drafted by fabric-coordinator
**Scope:** `tools/fabric/episodic.py` (the journal), `tools/fabric/history.py` and `bin/fabric-history` (retrieval), the journal calls in `communication/gzcoord/scripts/send.mjs` and `inbox.mjs`, the per-agent `episodic.db` in the account's runtime state
**Pillar:** P1
**Evidence:** docs/live-checks/2026-10-01-episodic-journal.md

## 1. Context and Problem

An agent's record of what it said and was told lived in two places it does
not own: the relay that carries GZCoord, whose history is a property of
today's carrier, and the harness's own transcripts. The relay happens to
keep every message (4,379 on the fleet's channel since 2026-09-11, with
retention off), but a carrier is not bound to: a peer-to-peer carrier may
keep no offline store by design, and the relay database is host state with
no backup (ADR-033). The inbox acknowledged each page before printing it,
and the sender recorded only an id and a hash after the post: a message
lost between the carrier and the session was gone from both sides. The
owner reviewed what history the fleet should keep and decided it belongs to
each agent, above the transport, separate from curated memory, working
state and the control plane.

## 2. Decision

Each agent keeps an **episodic journal**: a SQLite database in its own
runtime state (`<state>/agents/<login>/episodic.db`, ADR-003) holding the
exact GZCoord messages it sent and the ones addressed to it, written at the
moment they cross the carrier — before the post when sending, before the
acknowledgement when receiving. The journal is GZCoord's, not the
carrier's: the carrier is recorded as provenance and never decides what is
kept. It is evidence of what was said, ranked below the tree, curated
memory and the job list (ADR-013), and it is never injected into a
session's context on its own: `fabric-history` reads it when asked.

## 3. Alternatives Considered

- **Read the carrier's history when needed.** Rejected: it ties memory to
  one carrier's retention; the next may keep nothing, and today's keeps
  only what nobody has cleared.
- **One central journal for the fleet.** Rejected: raw conversation would
  cross account boundaries, and one database would be a single point of
  failure (ADR-034).
- **Index the harness's transcripts.** Kept for later and separate: the
  hook and transcript shapes are to be measured first, and GZCoord's
  durability must not wait on them.
- **A central import from the relay database.** Rejected for the backfill:
  that database is the coordinator's host state, and the coordinator does
  not write into other accounts' homes. Each agent imports its own history
  through the relay API, as itself.

## 4. Rationale

Writing at the crossing is the one point where the message is certain to
exist and where nothing yet depends on it: a journal that fails there can
still stop a send or withhold an acknowledgement, so no message is
presented or sent unremembered. Keeping it per agent keeps the privacy
boundary GZCoord already has (an agent reads what is addressed to it), and
needs no service. Measured cost is one short subprocess per page that holds
a message for the agent and two per send, and no prompt tokens.

## 5. Binding Rules

1. The journal is per agent, in its own runtime state, directory 0700 and
   files 0600; it records the agent id it belongs to and refuses to open
   for another (ADR-039: a reused login is a new agent).
2. Only GZCoord application messages enter it: those the agent sent and
   those addressed to it (TO its address, TO-ROLE a role it held, or
   BROADCAST). Control-plane traffic, presence and others' messages never
   do, whatever channel or carrier brings them.
3. Outbound, the message is journaled as pending before the carrier post,
   then marked accepted or failed; a send whose pending row cannot be
   written is refused. Failed marks only a pending row: a message the
   carrier accepted stays accepted when a later retransmission fails.
4. Inbound, the addressed messages of a page are journaled before the page
   is acknowledged; if that fails, nothing from the first of them on is
   acknowledged, since a carrier's acknowledgement may be a cursor that
   passes everything before it, and the carrier shows them again. A
   message is keyed as the inbox parsed it; one with no MESSAGE-ID is
   keyed by its body's hash, never refused.
5. One row per source, direction and MESSAGE-ID. The same id again is the
   same row. An outbound id with another body is refused; an inbound one
   keeps the first copy and records the other beside it. The agent's own
   message coming back on the channel fills its outbound row only when the
   journal holds that very body; a message that merely names the agent as
   FROM is kept as received.
6. The carrier is provenance (its name and sequence), never part of what a
   history query means.
7. A history result is evidence, not current truth and not authorisation;
   `fabric-history` says so, and withholds credential-shaped values.
8. Nothing from the journal enters a session's context automatically, and
   nothing in it is promoted to curated memory without the drain.
9. An agent's past messages are imported by the agent itself, through the
   carrier as itself; a TO-ROLE message is imported only where the
   agent's own role history shows it held that role then, and a broadcast
   only from the agent's birth.
10. Rules 3 and 4 have one exception, a break-glass: `GZCOORD_JOURNAL=off`
   sends and receives without the journal, for an operator whose journal
   cannot be written. It is never silent and never untraced: every send
   and every addressed inbound record that crosses without the journal
   first appends a line to `journal-bypass.jsonl` in the agent's state
   (time, direction, MESSAGE-ID, the hash the journal would have kept,
   the carrier sequence when known; never a body), and a send a second
   line after its post with its outcome (accepted, failed or unknown)
   (A 2026-10-06),
   mode 0600, under
   `agent_lock`, and warns per send on stderr and once per inbox page on
   the inbox's stdout (its drain and its watch), where the session sees it. A
   line that cannot be written refuses the crossing, as a journal that
   cannot be written does (A 2026-10-05).

## 6. Consequences

- A message is no longer lost between the carrier and the session, on
  today's carrier or the next.
- Each send and each addressed page costs one short process.
- The journal is local: a host lost is that host's agents' history lost.
  Backup or replication is a separate decision.
- The relay's own history stays as it is, for operations; nothing here
  reads its database.

## 7. Future Evolution

The harness's conversation turns join the same journal once their hook
contract is measured. A lifecycle summary on resume, full-text indexing,
or a resident writer process are each added only on a measured need.
When a resume does read the journal, it reads the session's working
events (files edited, decisions, errors, the last request) and fetches
what a query names, ranked, never the whole record: no per-turn
injection (ADR-036). If full-text indexing is built, the recipe to
measure first is SQLite FTS5 with a stemmed and a trigram index, their
ranked lists fused by reciprocal rank, snippets cut around the matched
terms (A 2026-10-09). A
carrier that keeps no history makes the journal the only record; that is
the case this is for.

## 8. Decision Status

Accepted and in force. Rule 9's import is `episodic.py gzcoord-import`,
run once per account by bootstrap's last step and retried there until it
has read every channel to its end.

## References

- `tools/fabric/episodic.py`, `tests/test_episodic.py`,
  `docs/live-checks/2026-10-01-episodic-journal.md`.
- `tools/fabric/episodic_import.py`, `tests/test_episodic_import.py`,
  `docs/live-checks/2026-10-02-episodic-import.md`; the bootstrap step in
  `tools/fabric/bootstrap.py`.
- ADR-003 (per-agent state), ADR-013 (the memory model), ADR-033 (GZCoord's
  transports), ADR-034 (decentralization), ADR-036 (cost per verified
  result), ADR-039 (the agent id), ADR-040 (Python).

## Amendments

The body above reads current; each change's full note is in [history/ADR-041-amendments.md](history/ADR-041-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-10-05 | `GZCOORD_JOURNAL=off` is a recorded break-glass | §5 rule 10: every bypassed crossing appends an audit line first, or is refused |
| 2026-10-06 | A bypassed send records its outcome | §5 rule 10: a second line after the post, accepted, failed or unknown; a failed line only when the post provably never reached the relay |
| 2026-10-09 | What a resume reads from the journal, and how it is ranked | §7: a resume fetches the session's working events by query, ranked, never the whole record; the full-text recipe to measure first is FTS5 stemmed + trigram fused by reciprocal rank, with snippets |
