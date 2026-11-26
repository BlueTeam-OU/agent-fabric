# 2026-11-26 — gate 2's drills: a carrier outage, and two accounts in carrier-only through a relay hour

Gate 2 of `docs/proposals/gzcoord-interweave-only-cutover.md` (§4) asks
for a carrier-outage drill, two accounts in `carrier-only` through a relay
stop of an hour with every GZCoord function exercised, and W12's
read-back. Both drills ran on the owner's word of 2026-11-26 ("Now,
tonight", given in the coordinator's session), at night, so traffic was
light. Every account ran fabric cfd65a1e and was in `carrier-record`
beforehand, 0 stranded (`fabric-ctl all interweave`). Run and filed by
fabric-coordinator on develop-qzapp (job j918). The computed report,
`gzcoord-carrier parity` over the evidence collected at 03:20Z, is
[2026-11-26-gate-2-drills-computed.md](2026-11-26-gate-2-drills-computed.md).
This record decides nothing by itself: the gate is the owner's word.

## Drill A: python-dev-03's carrier stopped for 31 minutes

| | UTC, 2026-11-26 |
|---|---|
| announced (`01a2154b`, broadcast) | 00:40:26 |
| `fabric-ctl python-dev-03 interweave-stop` | 00:40:58, daemon and client inactive |
| two probes from `user` (`01a2154d-5d54`, `01a2154d-648a`) | 00:42:01, 00:42:03; `gzcoord-send` exit 0 |
| `fabric-ctl python-dev-03 interweave-start` | 01:11:00 asked, 01:11:46 daemon and client active |

**Verdict (`--carrier-drill`): passes.** Both probes were held by the
sender's outbox (`done`), delivered at 01:12:24Z, after the window, one
copy by each carrier (the relay's is the mirror, normal in
`carrier-record`), and shown once. Only two pairs were made inside the
window: the night's traffic to that account was the probes.

## Drill B: python-dev-02 and python-dev-03 in carrier-only, relay stopped one hour

| | UTC, 2026-11-26 |
|---|---|
| announced (`01a21569`, broadcast) | 01:12:24 |
| `interweave-mode --mode carrier-only`, python-dev-02 / python-dev-03 | at once / answered 01:15:27, about three minutes |
| `systemctl --user stop gzcoord-relay.service` | 01:15:56 |
| REQUESTs to the pair (`01a2156c-996f`, `01a2156c-be62`) | 01:16:08, 01:16:18; exit 0, "the InterWeave carrier is the record" |
| relay started | 02:16:13 |
| pair back to `carrier-record`; `fabric-ctl all ping` | 02:16:27; 30 of 30 |
| end announced (`01a215a4`, broadcast) | 02:16:41 |

**The functions, as each of the pair ran them and reported** (REPLYs
`01a2156d-a7db`, `01a2156e-34e1`, `01a2157b-032c`, `01a2157b-5d0a`):

| function | python-dev-02 | python-dev-03 |
|---|---|---|
| a REQUEST's job intake | queued as j188 on delivery | queued as j187 on delivery |
| send | each REPLY arrived by InterWeave | as python-dev-02 |
| replay (`gzcoord-inbox --replay`) | exit 0, the journal row, sender verified by a carrier | as python-dev-02 |
| `fabric-jobs add --request` | exit 1, "already j188" (the intake had it) | exit 1, "already j187" |
| `fabric-pr arm --authorization` | **not exercised**: see below | **not exercised** |
| the watch | ended on delivery, re-armed; never gave up | ran through without ending |

`fabric-pr arm 708 --dry-run --any-owner --authorization <id>` was the
only PR the pair could name. It refused on #708's missing claude review
before it read any grant, and printed nothing about the message. So the
journal read of a grant with the relay down is still unshown. Before
that, each session's job-copy hook refused the dry run as a publish
until the session switched jobs.

**Verdict (`--relay-drill`): UNSETTLED. Nothing failed, and 2 of 13 pairs
cannot be told yet.** 11 pairs were held by the carrier alone, shown
once, never shown again, and their relay copy came back acknowledged.
The fourth property holds for all 13: the backfill posted each one to
the relay after its return, 414 s to 3618 s late. The two open pairs
(`01a21595-4ce7`, `01a2159d-f506`) are to ux-designer-01. Its watch
ended on a delivery at 02:10:05Z and logged no start after that (read
at 03:21Z), so no relay copy was ever read back. That is a
session not re-arming, not a carrier fault. The same account accounts
for the report's 3 relay misses (the third is `01a215a4`, after the
drill). No watch on any of the 30 accounts gave up during the hour.

## W12's read-back

With the relay down: `fabric-ctl all presence` answered 30 of 30 in
9 s, and `fabric-ctl python-dev-02 jobs` answered in 6 s. `gzcoord-send`'s
presence check passed for both REQUESTs. Presence and the queue are off
the relay's outage path.

## What still reads the relay

- **The fleet deck's dots.** The owner saw every agent as idle during
  the hour. Under control `dual` agentd posts the state stream to the
  relay, and the deck shows an account with no fresh record (two
  heartbeats) as idle (`docs/fleet-deck/tab-states.md`). The sessions
  were running throughout. This is gate 3's state-stream replacement.
- **`fabric-jobs list`'s priorities.** python-dev-02's list said "the
  state stream could not be read (the relay is unreachable): stored
  priorities decide". It still worked.

## What follows for gate 2

Gate 2 lists four items. The day's soak was filed on 2026-11-19. The
carrier-outage drill passes, and W12's read-back holds. The carrier-only
pair's relay hour is short of passing on two counts:
- ux-designer-01's two unsettled pairs;
- one function not exercised: `arm --authorization`, against a PR
  that reaches the grant check.

The first settles by collecting again once ux-designer-01's watch has
read the relay. The second needs one dry run on a reviewed PR below
its minimum, in `carrier-only` with the relay down. The night window
also exercised less traffic than "a working hour" implies.
