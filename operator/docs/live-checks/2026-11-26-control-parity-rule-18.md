# 2026-11-26 — control parity for ADR-029 rule 18, with an interweave-stop drill

*Host develop-qzapp. Run and filed by fabric-coordinator (account `user`, job
j1071). This is the third run of `gzcoord-carrier control-parity`, and the first
that holds everything rule 18 asks of the report the owner's word is given on: every
request id and addressee with the carriers of the request and of the reply, p50 and
p95 per carrier, each miss with its cause, and an `interweave-stop` drill
mid-window. The interim record
[2026-11-25-control-parity.md](2026-11-25-control-parity.md) found one gap, the
minutes after an `upgrade fabric`. python-dev-04 closed it in #709 (j163). The tool's
output is filed unedited as
[2026-11-26-control-parity-rule-18-computed.md](2026-11-26-control-parity-rule-18-computed.md),
and the same run's `--json` as
[2026-11-26-control-parity-rule-18-computed.json](2026-11-26-control-parity-rule-18-computed.json).
The JSON has the per-pair fields the Markdown leaves out: each pair's op and time, its
latency per carrier, and the request carriers of the drill's pairs.
The tool measures and the owner decides. The owner's word is quoted at the end.*

## What was run

The fleet was sent `upgrade fabric` to 50e27625 (#709) at 09:16:44Z. The accounts' agentds
ran #709's code from the times shown under *The request's carriers* below. Each of the 30
roster accounts' `control-arrivals.jsonl` was read as that account with
`fabric-host develop-qzapp run --as <login> -- grep -a …`, on the owner's one-time
permission. The files were collected 2026-11-26 about 10:51Z. `-a` is there because
the files of p2p-network-dev-01 and -02 hold a non-text byte. No read failed: every
`.err` is empty.

```sh
gzcoord-carrier control-parity --window 2026-11-26T09:10:00Z 2026-11-26T10:30:00Z \
  --drill 2026-11-26T09:32:01Z 2026-11-26T09:43:51Z \
  --operator user --arrivals <login>=<file> …
```

Re-running the command on the same files at 11:03Z gave byte-identical output. The
same run with `--json`, filed beside it, gives the per-pair figures below. Its counts:
0 lines skipped, 0 pairs `unrecorded`, 0 malformed timeouts.

## Result, outside the drill

| carrier | delivered | missed | p50 | p95 |
|---|---|---|---|---|
| relay | 967 | 0 | 3 s | 46 s |
| interweave | 967 | 0 | 3 s | 45 s |

The window holds 967 pairs of 39 requests, from 30 addressees. Every pair came by both
carriers. Every cause count is 0: no-waiter, late, relay-only, timeout and no-session.

The pairs by op: identity 422, gateway 420, upgrade 60, secrets-sync 60, jobs 3,
usage 2.

**Why p95 is 46 s here and was 5 s on 11-25.** The 60 `upgrade` pairs are the only
pairs that took 30 s or more. They took up to 240 s on both carriers, since an
upgrade's reply comes after the upgrade itself. They are 6 % of this window's pairs,
so they set the 95th percentile. In the 37.5-hour interim window, reads swamped them.
The slowest read here is identity at 22 s on the relay and 21 s on InterWeave.

**The upgrade gap is closed.** Two `upgrade fabric` runs fall in the window, at
09:13:09Z and 09:16:44Z. The ten minutes after them, 09:13:09–09:26:44Z, hold
300 pairs of 10 requests. All 300 came by both carriers. On 11-24 and 11-25 the same
spans held 254 of the 255 pairs that were not `both`.

**The request's carriers.** Of the 967 pairs, 781 had the request reach the
addressee by both carriers. The other 186 pairs, whose addressees log only the
InterWeave arrival, belong to the ten requests sent from 09:11:38Z to 09:20:27Z. They
are all the pairs of the first nine requests, and 3 of the 30 pairs of the tenth. The
relay request line is #709's own addition, and older agentd code wrote none:
python-dev-04 said so in its REPLY 01a2172b. So these pairs show addressees whose agentd
was not yet on #709. The requests at 09:17:44Z and 09:18:23Z, after the upgrade was
sent, are InterWeave-only for all 30 accounts. The request at 09:20:27Z is
InterWeave-only for rust-ui-dev-01, rust-ui-dev-02 and `user`, and has both request
lines for the other 27. Every pair after 09:20:27Z has both request lines. No pair in
the window lacks an InterWeave request line.

## The interweave-stop drill

The drill ran on the owner's word ("now is ok"), with broadcast 01a21731 at
09:30:28Z. `interweave-stop` was run on python-dev-02 and python-dev-03 and was done at
09:32:01Z. During the stop, the operator asked ping, identity, gateway, state and
presence. `interweave-start` brought the units back by 09:43:51Z, and the end
broadcast was 01a2173e.

The tool keeps the drill's pairs out of the carrier rows above:

| | pairs | requests |
|---|---|---|
| inside the drill | 174 | 58 |
| both carriers (the 28 accounts still on InterWeave) | 114 | |
| relay only, all to python-dev-02 and python-dev-03, 30 each | 60 | |
| unanswered | 0 | |

By op, the relay-only pairs are identity 15, gateway 14, state 11, ping 10 and
presence 10. All 174 drill pairs have both request lines, InterWeave's and the relay's.
The Markdown's drill list prints no request carrier, but the JSON's `in_drill` rows do. So **every request was still answered**, which is what rule 18 asks of
the drill. For the 60 relay-only pairs, the answer came from the relay alone. Under
`control_carrier` naming InterWeave alone, those reads would have gone unanswered, and
the two accounts would have read as unknown for the 12 minutes of the stop.
Rule 18's fallback for an account the carrier cannot reach applies only to actions
and to the carrier's own relay-only ops. A plain read has no such fallback.

**The drill's requests also arrived late by InterWeave.** For each of the 60 relay-only
pairs, the addressee's file also has an InterWeave `request` line, dated after its
units came back. python-dev-02's lines run 09:42:50–09:46:27Z, and python-dev-03's run
09:43:21–09:47:33Z. These copies came 9 to 15 minutes after their requests, well past
the 30 s `ttl_s`. The operator's file has no InterWeave reply to any of them, so none
was answered twice or answered late. This record shows that no answer came. It does
not show which rule stopped one: the seen-set, the ttl, or fabric-ctl having already
left.

## What is still open from the interim record

The interim record left three pairs without a cause: the two `relay-only` pairs from
11-24 and 11-25, and python-dev-04's off-upgrade `late` pair at 2026-11-24T14:48:51Z.
They are still without a cause. Nothing like them occurs in this window.

## What it decides

- On this window, control by InterWeave matched the relay. The InterWeave column has
  0 misses in 967 pairs, including the minutes after two upgrades.
- During the drill, every request was answered. The relay answered alone for the two
  stopped accounts.
- The report has the four parts rule 18 names, and the owner's word below was given
  on it.

**The owner's word**, 2026-11-26 about 11:00Z, in the coordinator's session, after
this report and gate 2's drills: "Interweave must become the only transport as soon as
you have completed eventual remaining steps". ADR-029 is amended on the same pull
request (A 2026-11-26) to record the word and this report. Under `dual` nothing
changes: the relay stays the record and is posted and read first, as the code's
definition of `dual` says. InterWeave becomes the transport of record when
`control_carrier` names it alone. That switch waits for the steps gate 3 of
`docs/proposals/gzcoord-interweave-only-cutover.md` names, because the deck's state dots
and the relay-only ops still ride the relay.
