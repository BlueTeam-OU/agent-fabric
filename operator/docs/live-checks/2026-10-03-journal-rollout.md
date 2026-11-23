# Before the journal's import reaches every account

Bootstrap's step 9 runs `episodic.py gzcoord-import --if-needed` on every
account (agent-fabric ADR-041 rule 9). #84's review left two questions to
settle live first:

- In which zone does the relay stamp a message?
- Does every import leave a consumer behind on the relay?

Both were measured on develop-qzapp, as the account `user`
(fabric-coordinator), against the fleet's relay. No message content was
printed or kept.

## The relay's timestamps

Six of this account's own sends, the last six in its
`gzcoord-sent.jsonl`, were compared with the relay's record of each one:

- **The relay's fields.** A listing carries `id`, `is_json`, `sender`,
  `seq`, `ts` and `ts_full`, but no `timestamp`. The import reads
  `ts_full` first, so the field it relies on is there.
- **The zone.** `ts_full` and `ts` are the same value, in ISO 8601 with
  microseconds and an explicit `Z`, for example
  `2026-10-03T03:52:02.629506Z`. The relay stamps UTC.
- **Against the sender's clock.** The relay's time, as the import reads
  it, is 80 to 135 ms *before* the UTC `at` that `send.mjs` writes to its
  ledger once the post returns. In order:

  | seq | difference |
  |---|---|
  | 10864 | −0.135 s |
  | 10900 | −0.104 s |
  | 10937 | −0.134 s |
  | 10968 | −0.104 s |
  | 10993 | −0.080 s |
  | 10999 | −0.083 s |

  The decisions that compare against a time are birth, the ledger's epoch
  and watermark, and the role history. None of them is within a second of
  any message.

## Consumers left on the relay

The import lists from seq 1 under a consumer id made for the run and never
acknowledges. Four such ids had read the whole channel by the time of this
check: #84's import and three probes for this check.

The relay's database (`bridge_consumer_cursors`, read only, ids and counts)
holds **23 cursor rows, and none of them is one of those ids**. A listing
that never acknowledges creates no cursor. The `audit` table is empty: a
listing leaves no row there either. An import therefore leaves no state on
the relay, however often it runs.

## `--if-needed` on an account that has imported

This account had imported in #84, before the import began recording which
channels it had read to the end. So:

- **First run:** it read the channel again, 10 pages to seq 10999, in
  1.14 s. It stored nothing new: 0 sends, 0 received. The report is
  unchanged: 222 sends predate the ledger, and 163 TO-ROLE messages were to
  roles not held at the time.
- **Second run:** `every channel already imported; nothing to do` in
  0.24 s, with no request to the relay.
- **Modes.** `episodic.db` and `episodic-import.json` are both 0600.

## What it decides

The step is safe to run on every account:

- It costs at most one full read per account, under two seconds for the
  whole channel.
- After that, it is a local no-op on every bootstrap.
- It moves no cursor and leaves nothing on the relay.

Its bound is 20 s. The bound covers a relay that is slow, not one that is
large: moveto's `enter` gives all of bootstrap 30 s. An account whose first
import misses the bound says so in one line, and the next bootstrap tries
again.
