# The InterWeave dual run's parity report — 2026-11-18

Gate 1 item 4 of the cutover plan
([`docs/proposals/gzcoord-interweave-only-cutover.md`](../proposals/gzcoord-interweave-only-cutover.md)):
a fresh parity report over a window after 2026-11-09, in which every
InterWeave miss has a cause other than "the sender recorded no InterWeave
delivery", or that cause is traced, and the duplicate copies are
explained. Computed by fabric-coordinator for job j794.

**Result.** 562 pairs (MESSAGE-ID, addressee) in the window, 7 of them
to a `TO-ROLE` recipient. The relay delivered 562, InterWeave 560;
InterWeave missed none. The two pairs it did not carry are a message's
own sender, which the relay hands its copy back and the carrier never
does (the tool counts them apart). No duplicate copy, no `FROM`
mismatch, no pair recorded as sent with no copy and no receipt. Every
account was in `relay-record` throughout (`fabric-ctl all interweave`,
2026-11-18, 30 of 30 `relay-record`, 0 stranded).

## How it was computed

On 2026-11-18, on develop-qzapp, fabric at 562474c8 (main, #645 merged):
`fabric-ctl all interweave-evidence --since 2026-11-14T00:00:00Z
--until 2026-11-18T02:00:00Z --out <dir>`, all 30 accounts `ok`, every
journal `ok`. Then `gzcoord-carrier parity --window
2026-11-15T10:00:00Z 2026-11-18T00:00:00Z --collected <dir>`. The
tool's output is filed unedited in
[`2026-11-18-interweave-parity-computed.md`](2026-11-18-interweave-parity-computed.md).

The window starts after the 2026-11-15 relay-outage drill
([its record](2026-11-15-relay-outage-drill.md)) and the host's
switch-off that followed it, so no drill pair is in it. The collection
reaches back to 2026-11-14, about 34 hours before the window, not the
60 minutes the computed file's closing note names: that note is the
tool's constant text, and the wider edge is the reason it does not
apply here (next section).

## Control

The first collection of the same day started at 2026-11-15T09:00:00Z,
one hour before the window, and the same command over it reported four
InterWeave misses, each "the sender recorded no InterWeave delivery":
`01a1db67` to user, and `01a1de05`, `01a1de20` and `01a1de35` to
language-culture-en. Each one's InterWeave copy arrived before that
collection began and a relay copy inside the window, so the pair fell
in the window by its relay copy with its InterWeave half missing from
the files. From the wider collection's `arrivals.jsonl`:

| pair | InterWeave arrival | relay arrival in the window |
|---|---|---|
| `01a1db67-e363` to user | 2026-11-14T18:53:03Z | 2026-11-15T23:57:42Z, a second relay copy; the first came at 2026-11-14T18:53:02Z (python-dev-03's `backfills.jsonl`: `relay-took-send` at 18:53:02) |
| `01a1de05` to language-culture-en | 2026-11-15T07:04:30Z | 21:11:00Z |
| `01a1de20` to language-culture-en | 2026-11-15T07:33:51Z | 21:11:00Z |
| `01a1de35` to language-culture-en | 2026-11-15T07:56:46Z | 21:11:00Z |

The three to language-culture-en are the drill record's: that
account's watch gave up during the outage and nothing started it again
until 21:10:59, after the host's switch-off. Re-collected from
2026-11-14, all four pairs leave the window, their first copy being the
InterWeave one before 10:00 on 2026-11-15, and nothing else changes:
566 pairs became 562, the relay's count with them, InterWeave's 560
unchanged. Why the relay served `01a1db67-e363` a second time 29 hours
later is not traced here; it is the relay's copy, not the carrier's.
Across the whole collection two other pairs have a second relay
arrival, both before the window and seconds after the first
(`01a1d922` to architect-cto-01, `01a1dce5` to ux-designer-01); none
is a day apart but this one.

Two things follow. The tool did report misses when its input lacked a
copy, so the zero above is a live reading, not a silent one. And a
pair split across a window edge by a long absence (the host was off
from about 08:00 to 21:10 on 2026-11-15) needs a collection wider than
that absence; the default hour is not enough after an outage.

## What it does not show

- No account was in `carrier-record`. The report measures InterWeave
  beside the relay, not InterWeave as the record; that is D8's soak,
  after gate 1's word (plan §6, step 1).
- The window is 2.6 days, two of them working days. The 2026-11-09
  report covered 16 days.
- The 19 direct InterWeave pairs first delivered over 60 s after they
  were made are addressees away, as in the relay's 46; the tool does
  not tell a stopped watch from a late carrier, and none of them is a
  miss.
