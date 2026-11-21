# The fleet's carrier-record soak — 2026-11-19

Gate 2's first item in the cutover plan
([`docs/proposals/gzcoord-interweave-only-cutover.md`](../proposals/gzcoord-interweave-only-cutover.md)
§4, D8 as the owner shortened it on 2026-11-18): every account in
`carrier-record` for one day with no stranded delivery. Read by
fabric-coordinator for job j947.

**Result.** The soak held on every measure the plan's step-back list
names, and turned up one send the carrier did not accept
(below, "Traced"). Over the window 2026-11-18T13:18:00Z to
2026-11-19T13:17:00Z the fleet carried 441 pairs (MESSAGE-ID,
addressee), 9 of them to a `TO-ROLE` recipient. InterWeave delivered
436 of them, plus 3 sender-own copies that the tool counts separately, and missed 2. All 1,076
delivery records in the collection are `done`: none `blocked`, none
outstanding. Parity found no pair recorded as sent with no copy and
no receipt, no duplicate InterWeave copy and no `FROM` mismatch. No
account stepped back.

## How it was read

On 2026-11-19, on develop-qzapp, from the main checkout at 45628272:

- **Modes.** At 13:35Z, `fabric-ctl all interweave --json`
  answered 30 of 30 accounts `carrier-record`, version 0.3.0, pinned,
  both units up, channel `ok`, stranded 0. Each account's
  `transport_mode.set_at` is the time of its last move: python-dev-03
  2026-11-18T10:40:45Z, python-dev-02 11:24:45Z, 27 accounts
  13:16:55Z, user 13:17:08Z. None is later, so no account's mode was
  rewritten during the window. The window starts at 13:18:00Z, the
  first whole minute after the last move.
- **Evidence.** At 14:20Z, `fabric-ctl all interweave-evidence --since
  2026-11-17T12:00:00Z --until 2026-11-19T14:20:00Z --out <dir>`
  answered 30 accounts `ok`. Each `meta.json` reads `journal: ok`,
  `complete: true` and `backfill_log.send_rows: true`. The collection
  starts about 25 hours before the window and ends 63 minutes after
  it, past `parity.MARGIN_S` (3600 s) at both edges. The 2026-11-18
  report's Control section shows why a narrow leading edge produces
  false misses.
- **Parity.** `gzcoord-carrier parity --window 2026-11-18T13:18:00Z
  2026-11-19T13:17:00Z --collected <dir>`. The output is filed
  unedited in
  [`2026-11-19-carrier-record-soak-computed.md`](2026-11-19-carrier-record-soak-computed.md).
  The closing note about 60 minutes is the tool's constant text; the
  leading edge here is wider.
- **Delivery states.** A script read every account's
  `deliveries.jsonl` and counted states: `done` 1,076, nothing else.

## Against the step-back list (plan §6)

| trigger | read | how |
|---|---|---|
| a delivery outstanding past an agreed age | none | no delivery record outside `done` across the whole collection; the `stranded` column (older than `position.STRANDED_AFTER_S`, 600 s) 0 on 30 accounts at 13:35Z and on 2026-11-18 at 15:35Z |
| a `blocked` code other than `NotInRoster` | none | no delivery record `blocked`, `NotInRoster` included |
| a roster that fails to verify | not read directly | the `interweave` op does not report the roster's verification. Indirect: no `NotInRoster`, user's carrier counts `unrostered: 0`, and InterWeave carried every pair but 2 |
| an account off the channel | none | channel `ok` and both units active on 30 of 30 at 13:35Z; between the reads it is shown only by the deliveries |

The `stranded` column is a read at one moment: a delivery stuck for
hours and receipted before 13:35Z would not appear in it. The delivery
records are kept, so the counted states above cover that case for every
delivery the collection holds.

## The misses

**Relay, 56 pairs (35 messages).** Every one is "the addressee's inbox
recorded no relay copy". Each message's sender logged a backfill line
`present` for it. Since #651 (merged 2026-11-18T10:37Z, 50c061f9),
`send.py` writes a sent-ledger `id` only after the relay answered 2xx
(`record_sent`, otherwise `spent`). The backfill reads `present` from
that ledger or from the relay's own listing (`backfill.py`
`backfill_channel`). So the relay holds all 35, and the mirror the way
back depends on is complete for them. What is missing is the addressee
reading its relay copy. In `carrier-record` the watch waits on the
carrier, and these addressees read the relay little or not at all
(backend-dev-02, db-admin, flutter-dev-01 and web-dev-02 logged no relay
arrival in the whole collection; language-culture-en's last watch ended
`gave-up` at 2026-11-18T18:29:51Z).

**InterWeave, 2 pairs, both to user.**

- `01a1dbcb-e405` was made 2026-11-14. Its relay copy arrived again on
  2026-11-19T07:41:04Z, inside the window. Its InterWeave copy came
  long before the collection began, which parity's own line says. This is
  the edge case the 2026-11-18 report's Control section shows, not a
  miss of the soak.
- `01a1f03b-0023` is an OBSERVATION sent `TO-ROLE: fabric-coordinator`
  by rust-services-dev-01 at 2026-11-18T19:56Z, which was in
  `carrier-record` the whole time. The sender's journal holds it as
  outbound and accepted with the relay as its carrier. The collection
  derives a `relay-took-send` row from that
  (`control/carrier_evidence.py`). The sender has no InterWeave
  delivery record and no mirror-log line for it. user's journal took it
  from the relay alone. The other 8 `TO-ROLE` pairs in the window
  went by InterWeave.

## Traced: 01a1f03b

python-dev-01 traced it (REPLY `01a1f431-e266`, 2026-11-19), and the
lines it cites were read on main at 45628272. It is a send in
`carrier-record` that the carrier did not accept. It is not a path
that makes the relay the primary. In `carrier-record`, `open_transport`
(`gzcoord/transport/__init__.py`) builds the carrier as primary and the
relay as its mirror. When the primary raises, `send.py` still runs the
mirrors. The relay took a copy, and the journal row records that
acceptance under the relay's name. `carrier_not_accepted` then exits 3,
"not sent", and says "the relay took a copy of it as well".
`tests/test_gzcoord_carrier_send.py` pins this case. So plan §6 step 2
holds for the exit status, and the message reached its reader through
the mirror. Under `carrier-only`, `open_transport` builds no relay, and
the same failure posts nothing anywhere.

Still not known: why rust-services-dev-01's carrier did not accept at
2026-11-18T19:56Z (absent, failing, or its answer lost), and whether
the sender saw exit 3. It did not resend through the carrier, since no
account holds an InterWeave delivery record for the id. That sender's
own carrier log would answer both, and this read does not reach it.

**The gap this leaves in the evidence.** A failure of the primary
carrier leaves no durable line. `send.py` writes `gzcoord-mirror.jsonl`
only for a mirror's refusal. So parity cannot tell "the carrier refused
and the relay took a copy" from "the relay was the primary", and under
`carrier-only` a refused send would leave nothing for a soak to count.

## What this decides

Gate 2's first item, the one-day soak with no stranded delivery, is
met. Two caveats are named above: roster verification was read only
indirectly, and one send the carrier did not accept, with its cause
unread and no durable line for that kind of failure. The gate's other items have no record
yet: the 30-minute carrier-outage drill on one account, two accounts
in `carrier-only` through an hour's relay stop with every GZCoord
function exercised, and W12's read-back with the relay stopped.

## Since: the gap is closed (2026-11-21)

BlueTeam-OU/agent-fabric#673 (python-dev-01 j264, merged
2026-11-21T08:28Z at f73f9611) answers REQUEST `01a1f433`. A send whose
primary is the carrier now writes a `gzcoord-mirror.jsonl` line with
`as: primary` and the outcome (`absent`, `failed` or `no-answer`)
before the mirrors are asked, journal off included, and parity leads a
miss with "the carrier did not accept it at send". Every account runs
d8c876e4, which contains it (`fabric-ctl all status`, 2026-11-21). A
failure like 01a1f03b's now leaves a line for a soak to count, under
`carrier-only` too. The gate's other items stay as listed above, open
under j918.
