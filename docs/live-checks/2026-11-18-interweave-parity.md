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
mismatch, no pair recorded as sent with no copy and no receipt. At
collection every account was in `relay-record` with nothing stranded
(`fabric-ctl all interweave`, 2026-11-18: 30 of 30 `relay-record`, 30
of 30 stranded 0). The mode's history over the window is not read
here; plan §6 moves the first accounts only on gate 1's word. Every
time, id, bound and mode below that the tool's output does not print is
filed, as the lines it came from, in
[`2026-11-18-interweave-parity-rows.md`](2026-11-18-interweave-parity-rows.md).

## How it was computed

On 2026-11-18, on develop-qzapp, with `gzcoord-carrier` run from the
main checkout at 562474c8 (#645 merged):
`fabric-ctl all interweave-evidence --since 2026-11-14T00:00:00Z
--until 2026-11-18T02:00:00Z --out <dir>`, all 30 accounts `ok`, each
account's `meta.json` `journal: ok` and `complete: true`, run between
01:39 and 01:47Z, over an hour after the window's end. Then `gzcoord-carrier parity --window
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
| `01a1db67-e363` to user | 2026-11-14T18:53:03Z | 2026-11-15T23:57:42Z, a second relay copy; the first arrived at 2026-11-14T18:53:02Z (user's `arrivals.jsonl`) |
| `01a1de05` to language-culture-en | 2026-11-15T07:04:30Z | 21:11:00Z |
| `01a1de20` to language-culture-en | 2026-11-15T07:33:51Z | 21:11:00Z |
| `01a1de35` to language-culture-en | 2026-11-15T07:56:46Z | 21:11:00Z |

`01a1de05` and `01a1de20` are the drill record's; `01a1de35` was made
at 07:56:35, after the drill. All three wait on the same cause: that
account's watch gave up during the outage and nothing started it again
until 21:10:59, after the host's switch-off. Re-collected from
2026-11-14, all four pairs leave the window, their first copy being
before 10:00 on 2026-11-15 (InterWeave's for the three to
language-culture-en, the relay's, by one second, for `01a1db67-e363`),
and nothing else changes:
566 pairs became 562, the relay's count with them, InterWeave's 560
unchanged, and the away table lost the same pairs (relay direct 48 to
46, broadcast 2 to 0). That run's output is filed unedited in
[`2026-11-18-interweave-parity-control.md`](2026-11-18-interweave-parity-control.md). The relay served `01a1db67-e363` a second time 29 hours later, to a
watch that had started at 23:57:42; user's `acks.jsonl` acknowledges it
at 23:57:43, and `shown.jsonl` has it shown only on 2026-11-14, so the
copy was admitted quiet, not shown twice. It is a relay copy and before
the window, so the report counts no duplicate.
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
- The 19 direct and 1 role InterWeave pairs that arrived over 60 s
  after their MESSAGE-ID was made are not traced. The receiving carrier
  writes an arrival line whatever its session does, so a stopped watch
  is not their cause; what remains is the addressee's carrier down, the
  sender's outbox retrying, or an id minted well before the send. None
  is a miss. Under gate 1 they are the carrier's latency, and the soak
  (D8) reads them from the senders' `deliveries.jsonl`.
