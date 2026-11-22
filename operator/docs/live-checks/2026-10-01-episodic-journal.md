# 2026-10-01 — the episodic journal's ground: the relay's history, and a journal call's cost

ADR-041 keeps each agent's GZCoord messages in its own journal, written
at the crossing. Before building on the relay, this records what it
actually offers, and what one journal call costs on develop-qzapp, as
user, Claude-Bridge 1.3.0, fabric-python 3.13.15.

## What the relay holds

Read from the relay database in read-only mode:

| channel | messages | seq | from |
|---|---|---|---|
| `gzapp:gzcoord` | 4,379 | 1–10280 | 2026-09-11 |
| `fabric:control` | 5,894 | 864–10279 | 2026-09-17 |

The two selftest channels hold one message each. Bodies are whole,
about 1.9 KB on average. Retention is off: the package keeps everything
unless `retention_days` is set, and nothing sets it here.

## How a reader can page it

A history reader must read from the first message, without moving any
agent's cursor. Measured through the HTTP API with this account's token
(sequence numbers only were printed):

- `GET /api/messages?channel=…&limit=N` returns the newest page;
  `since_seq` is not a parameter and is ignored.
- `GET /api/messages?…&since_id=<message id>` pages forward from that
  message: after seq 3 came 4, 5, 6.
- `GET /api/messages?…&consumer_id=<a consumer the relay has not seen>`
  starts at seq 1, and listing does not move that consumer's cursor (a
  second identical call returned 1, 2, 3 again).
- `full=1` is needed for the body; without it a record carries a
  preview.

So an import opens with a fresh consumer name and pages by `since_id`,
500 records at a time, and no agent's inbox is disturbed.

## What a journal call costs

`episodic.py`, run as a subprocess as `send.mjs` and `inbox.mjs` will
run it, against a scratch journal, 60 calls each:

| call | p50 | p95 |
|---|---|---|
| `gzcoord-in`, one 2 KB record | 326 ms | 539 ms |
| `gzcoord-out-pending`, 2 KB | 345 ms | 460 ms |

The time was imports, not SQLite. `-X importtime` put 130 ms in
`runtime/identity.py`'s import (subprocess, argparse) and 80 ms in
`secret_store.py`'s. The module now reads the three facts it needs
itself, and a call takes about 250 ms. Most of what remains is the
standard library on a busy VM: `json` pulling in `re` and `enum`, about
120 ms, and a bare `python -c pass` ranged from 30 to 100 ms across
runs.

120 rows took 532 KB.

## What it decides

- The backfill reads the relay API as the account, with a fresh consumer
  name and `since_id` paging; it never opens the relay database.
- A subprocess per call is acceptable:
  - the inbox calls once per page that holds a message for the agent,
    and most pages hold none;
  - a send calls twice, which is small beside its network round trip.
- No daemon until a measured need: the plan's P0 bar.

## Read back live, on the coordinator's own account

The journal code ran in this account's real sessions: `send.mjs`, and
the inbox watch restarted on the new receive path. The messages were
real ones to and from python-dev-01.

- **Outbound.** Two sends, an INFO and a QUESTION, each became one
  outbound row marked accepted. `fabric-history` showed both,
  oldest first. The database file is 0600 in the account's state
  directory.
- **Inbound.** python-dev-01's REPLY to the QUESTION was delivered by
  the watch and journaled before the watch acknowledged it: one inbound
  row.
- **Thread.** `fabric-history --thread <the QUESTION's id>` returned the
  question and its reply, and so did starting from the reply.
- **Status.** `fabric-status` reported the journal's episode count and
  last write.
- **Timestamps.** The relay's timestamp carried microseconds where the
  journal's own carry seconds. Both are now stored to the second.

The hold path (a journal that cannot write) is proven by the suites
rather than live. A live failure would mean breaking a real account's
journal.
