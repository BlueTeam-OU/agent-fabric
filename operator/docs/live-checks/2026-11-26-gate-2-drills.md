# 2026-11-26 — gate 2's drills: a carrier outage, and two accounts in carrier-only through a relay hour

Gate 2 of `docs/proposals/gzcoord-interweave-only-cutover.md` (§4) asks
for a carrier-outage drill, two accounts in `carrier-only` through a relay
stop of an hour with every GZCoord function exercised, and W12's
read-back. Both drills ran on the owner's word of 2026-11-26 ("Now,
tonight", given in the coordinator's session), at night, so traffic was
light. Every account ran fabric cfd65a1e and was in `carrier-record`
beforehand, 0 stranded (`fabric-ctl all interweave`). Run and filed by
fabric-coordinator on develop-qzapp (job j918). The computed report is
[2026-11-26-gate-2-drills-computed.md](2026-11-26-gate-2-drills-computed.md).
This record decides nothing by itself: the gate is the owner's word.

**How it was computed.** The evidence was collected twice with
`fabric-ctl all interweave-evidence --since 2026-11-26T00:30:00Z --until <T>`,
from all 30 accounts: first with `--until 2026-11-26T03:20:00Z` (the
UNSETTLED reading below), then with `--until 2026-11-26T07:10:33Z`,
which finished at 07:10:51Z. Both collections were judged with
`gzcoord-carrier parity --window 2026-11-26T00:30:00Z 2026-11-26T02:20:00Z
--collected <dir> --carrier-drill 2026-11-26T00:40:58Z 2026-11-26T01:11:46Z
python-dev-03 --relay-drill 2026-11-26T01:15:56Z 2026-11-26T02:16:13Z`.
The second collection's output is filed unedited. Its line "Arrivals were
collected 60 minutes beyond each edge of the window" is the renderer's
fixed margin. The collection itself reached 07:10:33Z, so it holds the
07:09:06Z relay copies counted below.

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
| the watch | ended on delivery, re-armed; never gave up | ended on delivery and re-armed (01:16:45Z), started again at 01:19:44Z after no end line, never gave up (watch log, in the computed report); its REPLY: armed 01:19Z and still running at 01:32Z |

`fabric-pr arm 708 --dry-run --any-owner --authorization <id>` was the
only PR the pair could name. It refused on #708's missing claude review
before it read any grant, and printed nothing about the message. So the
journal read of a grant with the relay down is still unshown. Before
that, each session's job-copy hook refused the dry run as a publish
until the session switched jobs.

**Verdict (`--relay-drill`): the three properties hold, and the fourth.**
13 pairs were held by the carrier alone, shown once, never shown again,
and their relay copy came back acknowledged. The backfill posted each
one to the relay after its return, 414 s to 3618 s late. No watch on
any of the 30 accounts gave up during the hour.

Read first from the 03:20Z collection, the drill was UNSETTLED on two
pairs to ux-designer-01 (`01a21595-4ce7`, `01a2159d-f506`). What
follows was observed by the coordinator:
- **From ux-designer-01's watch log** (`fabric-ctl ux-designer-01
  interweave-evidence`, read at 03:21Z, 06:10Z and 07:10Z): the watch
  ended on a delivery at 02:10:05Z, and its next start was 07:09:32Z.
- **In the session's pane** (read through the fleet deck at about 07:00Z):
  it sat at a confirmation prompt from the fabric's own
  `runtime/claude-code/hooks/self-kill-guard.py`. The prompt was raised
  on a `gh pr create` whose body was written by a quoted heredoc.
- **Replaying that command through the guard** reproduces the prompt.
  It needs a `'` inside the double-quoted `--title` after the heredoc,
  and the same body with a plain title passes. So the guard read data
  as commands: a false positive, filed as job j1103.

The coordinator declined the prompt in that pane at about 07:05Z, on
the owner's word, and the session re-armed its watch. The second
collection's acknowledgement log shows both relay copies read and
acknowledged at 07:09:06Z, and its report puts relay misses at 0,
down from 3.

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
pair's relay hour passes on every message it carried, and five of the
six functions were exercised. The sixth, `arm --authorization`, was not:
it needs one dry run, in `carrier-only` with the relay down, against a
reviewed PR below its minimum, so the arm reaches the grant check. The
night window also carried less traffic than "a working hour" implies.
