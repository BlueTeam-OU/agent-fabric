# The InterWeave dual run's parity report — 2026-11-09

The record agent-fabric ADR-064 §5 rule 11 asks for: the parity report
the owner's word on the carrier is given on. It says what the dual run
shows and what it does not hold yet. The owner decides whether to wait
for the missing items. Requested by architect-cto
(REQUEST `01a1c040`), computed by fabric-coordinator.

**Run.** 2026-11-09, by fabric-coordinator on develop-qzapp, fabric at
d4812bff (main a4b54d78 and two commits of #532, neither in the carrier).
`fabric-ctl all interweave-evidence --since 2026-10-24T00:00:00Z --until
2026-11-09T17:50:06Z --out <dir>` answered `ok` from all 30 accounts:
7 584 arrival lines, 5 237 delivery records, every journal `ok`. Then
`gzcoord-carrier parity --window <the same> --collected <dir>`, once
alone and once with each `--relay-drill`:
2026-11-05T15:50:19Z–16:08:24Z
([the 18-minute drill](2026-11-05-relay-down-drill.md)) and
2026-11-07T22:19:40Z–23:20:19Z
([the hour](2026-11-07-relay-down-drill-hour.md)). The tool's output is
filed unedited in
[`2026-11-09-interweave-parity-computed.md`](2026-11-09-interweave-parity-computed.md):
every missed pair with its cause, and both drill sections. The rows the
tool reads but does not print (each drill pair's arrivals, showings and
acknowledgements, the first acknowledgement line per account, the
totals) are filed from the same collection in
[`2026-11-09-interweave-parity-rows.md`](2026-11-09-interweave-parity-rows.md).
Every time below comes from one of the two files. What follows reads
them.

## What the window holds

| item rule 11 names | in the window |
|---|---|
| every (`MESSAGE-ID`, addressee) pair | 3 987 pairs, from 30 accounts |
| missed, per carrier | relay 24, InterWeave 919 (below) |
| duplicate copies, per carrier | relay 37, InterWeave 516 |
| `FROM` mismatches | 0 on both |
| sent, no copy arrived, no receipt | none |
| delivered to an addressee that was away (first copy over 60 s after minting) | relay: 185 direct, 5 role, 14 broadcast; InterWeave: 59 direct, 1 role, 0 broadcast |
| compressed / chunked | 0 compressed, 10 chunked, 2 708 sent plain |
| a `TO-ROLE` recipient | **held**: 100 pairs addressed to a role |
| the rollback drill (carrier off mid-window, nothing lost) | **missing**: never run |
| the relay-outage drill | run twice, **not judged as passing** (below) |

**The 919 InterWeave misses** all have the same cause: the sender
recorded no InterWeave delivery, so the carrier never had the message.
906 of them were minted on 10-24 to 10-26 (10-24 124, 10-25 675,
10-26 107, by each MESSAGE-ID's UUIDv7 time). Why the senders had no
delivery then was not traced to rollout dates. The other 13 are from
10-27 to 11-07 and are listed in the computed file. The receiver did not
lose any of them.

**The 24 relay misses.** 20 are the rule 13 exchanges between
python-dev-02 and python-dev-03, on 10-25 and 10-28: messages sent by
the carrier alone, on purpose
([0.1.0](2026-10-25-interweave-two-accounts.md),
[0.2.0](2026-10-28-interweave-two-accounts-0-2-0.md)). One is the
11-05 drill's probe to devex-tooling. The relay refused it ("not sent")
and it was never resent. Three are to ux-designer-01 today (08:41,
09:09, 16:22Z). That account's arrival log has had no relay copy since
03:52Z, while the carrier still delivers to it. The likely reading is
that no watch has fetched from the relay since, so the copies are still
waiting there and are not lost. That was not checked against the relay.

**Duplicate copies** (InterWeave 516) mean a copy received more than
once. Rule 9's journal collapses them, and nothing here shows a session
seeing one twice. The cause was not traced in this run.

## The relay-outage drills

The tool first printed **A PROPERTY FAILED** for both drills. Read
against the evidence, that verdict came from two flaws in the judge,
not from the carrier. #534 fixed both, and the re-run over the same
collection (at the end of the computed file) reads both drills
**UNSETTLED, none failed**: on 11-05, 1 pair exercised; on 11-07, 4
pairs exercised; for each, the acknowledgement cannot be told. The
flaws were:

1. **The acknowledgement is read as "no" where nothing was logged.**
   `gzcoord-acks.jsonl` was added on 2026-11-08 (e4424b06), after both
   drills. Its first line on any account is 2026-11-08T17:05:31Z. Every
   "relay copy back, acknowledged: no" in the computed file therefore
   means the log did not exist yet. The relay did not refuse anything.
   `AckLog`'s own docstring says "not acknowledged" is meant to be a
   fact (an `ok: false` line), not a missing line.
2. **Pairs that neither carrier held during the drill are judged as if
   the carrier alone held them.** The judge counts a pair as "carrier
   alone" whenever the relay copy came after the drill ended. It does
   not ask whether the InterWeave copy came during the drill. Four
   pairs had their InterWeave copy arrive outside the drill, within a
   second of the relay copy: 11-05 to architect-cto-01 and
   rust-ui-dev-02 (16:10Z), 11-07 to rust-ui-dev-02 (23:20:41Z) and
   11-07 22:19:48Z to devex-tooling (11-08 07:26:57Z). The carrier did
   not hold any of them during the outage, so they prove nothing about
   the drill. When their senders sent them is not in the collection.
   Apart from the acknowledgement (flaw 1), they fail only on "first
   shown by the relay".

What the drills do show, pair by pair, where the carrier alone held the
message during the outage:

| drill | pair | carried in | shown to the session | shown again when the relay copy came | relay copy acknowledged |
|---|---|---|---|---|---|
| 11-05 | probe → devex-tooling | 15:51:48Z | once, by InterWeave, at 16:09:28Z by its shown ledger (the 11-05 record left this unverified; the watch had ended at the 15-minute budget, defect 3 of that record) | no relay copy ever came | nothing to acknowledge |
| 11-07 | → python-dev-03 (the probe) | 22:20:29Z | once, by InterWeave, 22:20:41Z | no (relay copy 23:23:32Z) | not measurable |
| 11-07 | → rust-ui-dev-01 | 22:24:29Z | once, by InterWeave, 22:24:36Z | no (relay copy 23:20:48Z) | not measurable |
| 11-07 | → ux-designer-01 | 22:23:56Z | once, by InterWeave, 22:24:10Z | no (relay copy 23:21:29Z) | not measurable |
| 11-07 | → devex-tooling | 22:30:10Z | once, by InterWeave, 22:30:10Z | no (relay copy 23:21:33Z) | not measurable |

In the hour-long drill, four messages that only the carrier held reached
their sessions within 14 s of arriving. None was shown again when the
relay returned with its copy. Rule 11's third property (the relay copy
is acknowledged) cannot be read for either drill: the record it needs
did not exist yet. The hour-long drill's "not shown again when the watch
restarts" is not exercised by these rows either. Each pair has a
single showing, and the collection records no watch restart, so
nothing shows a restart between a pair's showing and its relay copy.

## What it lacks, for the owner's decision

- **The rollback drill.** It was never run: the InterWeave carrier
  switched off mid-window, with nothing lost.
- **A relay-outage drill whose acknowledgements are logged.** Any drill
  after 2026-11-08T17:05Z would do. The judge was fixed by #534
  (6323913f).
- Optional, not named by rule 11: the cause of the 516 InterWeave
  duplicate copies, and the relay's side of ux-designer-01's three
  pending pairs.

The `TO-ROLE` item, which the request expected might be missing, is
present: 100 pairs.
