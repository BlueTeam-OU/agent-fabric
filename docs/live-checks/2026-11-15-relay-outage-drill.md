# 2026-11-15 — the relay-outage drill, run again with the backfill deployed

The relay-outage drill of agent-fabric ADR-064 §5 rule 11, run a second
time on the owner's word. The 2026-11-12 run
([2026-11-12-interweave-drills.md](2026-11-12-interweave-drills.md))
left two things unexercised: the backfill (#590), which landed the day
after it, and the watch's restart and 15-minute give-up, which its
logs could not show. This run covers both. It is the evidence for item 3
of gate 1 in `docs/proposals/gzcoord-interweave-only-cutover.md`. It
decides nothing by itself: the gate is the owner's word, on this record.
Run and filed by fabric-coordinator on develop-qzapp (job j794).

## The drill

| | UTC, 2026-11-15 |
|---|---|
| announced (`01a1ddf9`, broadcast) | 06:51:33 |
| `gzcoord-relay.service` stopped | 06:58:20 |
| drill window | 06:58:26 – 07:33:27, 35 min 1 s |
| `fabric-ctl all ping` with the relay down | 06:58:47, 30 of 30 `ok` (InterWeave alone) |
| relay started again; end announced (`01a1de20`) | 07:33:27; 07:33:51 |

The fleet ran fabric ca82ece0, which includes #620, so each watch logs
its starts and ends. The carrier ran on all 30 accounts. The parity
window is 06:50:00 – 07:45:00.

## How it was computed

Collected on 2026-11-17, two days after the drill:
`fabric-ctl all interweave-evidence --since 2026-11-15T05:50:00Z --until
2026-11-17T21:00:00Z --out <dir>`. All 30 accounts answered `ok`, with
1 436 arrival lines and 933 delivery records. Then `gzcoord-carrier
parity --window 2026-11-15T06:50:00Z 2026-11-15T07:45:00Z --collected
<dir> --relay-drill 2026-11-15T06:58:26Z 2026-11-15T07:33:27Z`, on
fabric 0a68bf5e. The tool's output is filed unedited in
[2026-11-15-relay-outage-drill-computed.md](2026-11-15-relay-outage-drill-computed.md).

A first collection, on 2026-11-15 at 07:58, read the drill UNSETTLED.
The relay copy of `01a1de05` (ux-designer-01 to language-culture-en)
had not come back. The owner then paused the fleet and switched the
host off. The second collection reads that copy; why it was late is
traced below.

## Control

What tells a real pass from a silent one is that the relay was absent for
the pairs counted as the carrier's: `gzcoord-relay.service` was stopped
at 06:58:20 and `fabric-ctl all ping` answered 30 of 30 `ok` over
InterWeave alone at 06:58:47. A pair counts as the carrier's alone only
when its InterWeave copy arrived inside the drill and its relay copy did
not (the computed file's definition), so it could only have reached its
session by the carrier. The twelve such pairs below are read from there;
a backfill that never ran would leave them with no relay copy at all,
not a late one.

## What it shows

**78 pairs, nothing missed.** The relay delivered all 78. InterWeave
delivered 76 and missed none. The other two pairs are the coordinator's
own broadcasts, addressed back to their sender. The carrier never sends
a message to its sender (ADR-064 rule 6), so the tool does not count
them. No duplicates on either carrier, and no `FROM` mismatches. No
`TO-ROLE` pair fell in the window.

**The three properties hold.** Twelve pairs were held by the carrier
alone, to seven accounts. Each was shown to its session once, by
InterWeave. None was shown again. Every relay copy came back and was
acknowledged.

**The fourth property holds: the relay's record by backfill.** Every
one of the twelve has a `posted` backfill row in its sender's log. The
delays run from 473 s to 2 094 s, the age of each message when the relay
returned. No hand resend was asked for: the drill-end broadcast said
there was nothing to resend. On
2026-11-12 this property failed by the age bound, because the backfill
was not yet deployed.

**The watch gave up, and restarted, inside the outage.** All 30
accounts' watches gave up at least once (exit 5, 51 give-ups in all).
The first wave came at 07:13:26, 15 minutes after the stop: the
give-up bound. 28 accounts started a watch again inside the drill,
most of them after a give-up, and none of those restarts showed a
message again. By 07:40, 29 of 30 accounts had re-armed.

**The one late relay copy is a session that did not re-arm.**
language-culture-en's watch gave up at 07:21:24 and nothing started it
again until 21:10:59. In between, the host was off for the owner's move,
from about 08:00. The backfill had posted the relay copy of `01a1de05`
at 07:33:59. The InterWeave copy was shown at 07:04:56, and
the relay copy was acknowledged at 21:11:01, two seconds after that
watch started. The drill-end broadcast `01a1de20` reached the
account's carrier at 07:33:51, but with no watch running it was shown
only at 21:11:00. Nothing was lost, but for about 40 minutes before
the host went off, the session could not be reached.

## #573's real-carrier read-back

The read-back #573 left undone (cutover plan, gate 1 item 1, W1) has
two halves. python-dev-03's probe of 2026-11-17
([2026-11-17-backfill-real-carrier-readback.md](2026-11-17-backfill-real-carrier-readback.md))
refused the relay at one sender. Its message was read only after both
copies existed, so it shows once-only where the copies meet. This
drill gives the order that probe leaves open: shown from the carrier
first, then the relay copy returns and is not shown again. It was not a
separate run. #573's own read-back used a
private relay and no second account. Here the fleet's agentd ran the
backfill against the real relay, and the message went through the real
carrier to a second account. Each of the twelve pairs above shows the
three facts: shown once, found on the relay after its return, and a
`gzcoord-backfill.jsonl` line. The tool computes them from three
logs: the addressee's arrivals and acknowledgements, and the sender's
backfill log.

One pair, traced by hand from those logs. The message is `01a1de19`,
from python-dev-04 to this account (develop-qzapp/user):

| UTC | log | what |
|---|---|---|
| 07:26:02 | python-dev-04 deliveries | queued to InterWeave, `done` |
| 07:26:03 | user arrivals | `interweave`, verdict `ok` |
| 07:26:27 | user shown | shown once, `via` interweave |
| 07:33:55 | python-dev-04 `gzcoord-backfill.jsonl` | `posted`, `delay_s` 473, 28 s after the relay was started |
| 07:34:55 | user arrivals, acks | the relay copy arrives and is acknowledged, not shown again |

The relay copy's arrival verdict is `unauthenticated`, like every relay
copy this account took from 2026-11-14 to 11-17. The relay carries no
signature, so this is not something the backfill caused.

Not verified here: that the backfilled body is byte-identical to the
journal on the real relay (#573's private-relay run checked it). Also
the 12 h age bound on the fleet (no row was that old), and a `TO-ROLE`
pair (none fell in the window).

## What it decides, for the owner

- **Gate 1 item 3 is met.** `--relay-drill` reads this drill as
  passing, not UNSETTLED. It lasted past 15 minutes, the give-up was
  seen fleet-wide, and watches restarted inside the outage without
  showing anything twice.
- **The backfill closes the gap j798 names.** No session resent anything by
  hand, and the relay's record holds every message the carrier alone
  carried.
- **A watch that gives up still depends on the session ending a turn.**
  An idle session whose watch gives up stays deaf until something
  starts a turn, the same pattern as the 2026-11-07 drill. Where the
  carrier leads, the give-up follows the carrier, not the relay (the
  tool's own definition, above the watch lines). So under InterWeave
  only this finding matters for a carrier outage, which no drill has
  run yet.

## Not verified

- Why language-culture-en did not re-arm between 07:21:24 and the
  host's power-off: its pane was not read at the time.
- A carrier outage under InterWeave only (the watch's give-up with the
  carrier as primary). This drill stopped the relay, not the carrier.
- Gate 1 item 4: this window is 55 minutes long, not a soak.
