# 2026-11-12 — the rollback drill and the relay-outage drill

The two drills agent-fabric ADR-064 §5 rule 11 asks of the dual run's
soak, run before the data plane's cutover (owner, 2026-11-12: "move the
data plane only to InterWeave; run both drills first"). This record is
item 3's "the 2026-11-12 drill gets its record, whatever it shows" and
items 2 and 4 of gate 1 in `docs/proposals/gzcoord-interweave-only-cutover.md`.
It decides nothing by itself: the gate is the owner's word, on this
record. Run and filed by fabric-coordinator on develop-qzapp (job j794).

## The drills

| drill | window (UTC) | what was done |
|---|---|---|
| rollback | 09:34:08 – 10:04:30, 30 min 22 s | `fabric-ctl all interweave-stop`: 30 of 30 accounts `stopped` (daemon and client inactive) from 09:33:54; `fabric-ctl all interweave-start` at 10:09:36, 30 of 30 `started` |
| relay outage | 10:13:30 – 10:43:51, 30 min 21 s | the relay (`gzcoord-relay.service`) stopped at 10:13:25, the InterWeave carrier running on every account; the relay started again at 10:43:51 |

The parity window is 09:30:00 – 10:54:24, wrapping both.

## How it was computed

Collected 2026-11-14, two days after the drill, so that copies which
arrived late are in it: `fabric-ctl all interweave-evidence --since
2026-11-12T08:30:00Z --until 2026-11-14T18:00:00Z --out <dir>`, `ok`
from all 30 accounts (2 205 arrival lines, 1 966 delivery records, every
journal `ok`). Then `gzcoord-carrier parity --window
2026-11-12T09:30:00Z 2026-11-12T10:54:24Z --collected <dir> --drill
2026-11-12T09:34:08Z 2026-11-12T10:04:30Z --relay-drill
2026-11-12T10:13:30Z 2026-11-12T10:43:51Z`, on fabric at 9a9dd0e7. The
tool's output is filed unedited in
[2026-11-12-interweave-drills-computed.md](2026-11-12-interweave-drills-computed.md).

A first collection on 2026-11-12 at 10:54 read the relay-outage drill
UNSETTLED: the relay copy of `01a1cf4c` to the coordinator had not
arrived. It arrived at 11:58:58, when its sender (python-dev-02)
resent it from its file on the coordinator's request (`01a1cf65`); the
second collection reads it.

## What it shows

**106 pairs.** The relay delivered 106 and missed none; InterWeave
delivered 97 and missed 9. No `TO-ROLE` pair fell in the window (the
2026-11-09 report holds 100).

**Rollback drill: nothing lost.** Every pair made while the carrier was
off reached its addressee by the relay.

**Relay-outage drill: the three properties hold.** Five pairs were held
by the carrier alone (`01a1cf44`, `01a1cf45`, `01a1cf4c`, `01a1cf4d`,
`01a1cf4f`). Each was shown to its session once, by InterWeave; none was
shown again; each relay copy came back and was acknowledged.

**Fourth property, the relay's record by backfill: FAILED, by the age
bound.** All five have a backfill row `present` in their sender's
`gzcoord-backfill.jsonl`, written 2026-11-13 between 08:55:24 and
08:58:53, 80 654 to 81 510 s after the message. The backfill (#590)
landed and was distributed the day after the drill. By then the relay
copies were already there. Four reached the relay between 10:45:56 and
10:47:51, 2 to 4 minutes after it returned; the coordinator's broadcast
`01a1cf5e` asked for hand resends at 10:47:04. The collected logs do not
say how each of the four was resent. The fifth, `01a1cf4c`, came at
11:58:58, on request. So the relay's record holds every message, and
nothing was lost. The property itself, a
backfill that runs as the relay returns, was never exercised by this
drill.

**Every InterWeave miss has a cause.**

| pairs | cause |
|---|---|
| `01a1cf1c`, `01a1cf1d`, `01a1cf2b`, `01a1cf34`, `01a1cf35` | made inside the rollback drill: the carrier was off |
| `01a1cf1b` (rust-services-dev-01 to architect-cto-01) | sent at 09:34:05, during `interweave-stop` (09:33:54 – 09:34:08); the relay took it (`relay-took-send`) |
| `01a1cf3c`, `01a1cf5b`, `01a1cf5e` to the coordinator | the coordinator's own broadcasts: the copy to their sender is never carried by InterWeave, and every other addressee got an InterWeave copy |

**Duplicates.** One relay duplicate: `01a1cf4c` to the coordinator,
copies at 11:58:58 (the resend) and 2026-11-13 05:07:09. The ledger
showed it once. InterWeave: none.

**The relay misses of the first collection** (`01a1cf3c` to
python-dev-01, `01a1cf5b`, `01a1cf5e` to python-dev-01 to 03,
`01a1cf63` to python-dev-03) are delivered in this one: their relay
copies arrived after 10:54 plus the collection's 60-minute margin.

## What it decides, for the owner

- **Rollback works.** With InterWeave off on every account for 30
  minutes, the relay carried everything and nothing was lost.
- **The carrier carries the data plane through a relay outage.** For 30
  minutes the carrier alone held five messages, and each was shown once.
  When the relay returned, its copies did not show them again.
- **Without a backfill, the relay's record needed hand resends.**
  devex-tooling's `01a1cf5d` found it at 10:46:24, after the relay returned, and it became
  the cutover blocker j798. The backfill (#590) and the mode it reads
  (#611, W9) are now on main. A relay-outage drill run now would
  exercise them; this one cannot.

## Not verified

- A watch restart inside the outage, and the watch's 15-minute give-up
  (the plan's gate 1 item 3). "Shown again: no" covers the restarts
  that happened. The collected logs do not record when a watch
  restarted, or whether one gave up.
- The fourth property under the deployed backfill (above).
- Item 4's "a window after 2026-11-09": this window is 84 minutes long,
  not a soak. Only the 2026-11-09 report covers the long run, and its
  516 duplicate InterWeave copies are not traced here.
