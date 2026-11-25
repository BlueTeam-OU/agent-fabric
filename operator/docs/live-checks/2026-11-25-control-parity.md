# Control parity after the no-waiter fix — 2026-11-25

*Host develop-qzapp, account `user` (fabric-coordinator), job j1071. The
second run of `gzcoord-carrier control-parity`, over 37.5 hours that start
once python-dev-04's j160 fix (#697, follow-ups #701 and #704) was live.
It is an interim record, not the report ADR-029 rule 18 asks the owner's
word on: that report still needs the request's relay carrier and an
`interweave-stop` drill (*What rule 18 still needs*). The tool measures;
the owner decides.*

## What was run

Each account's `control-arrivals.jsonl`, the lines dated 2026-11-24 or
later, read as that account (`fabric-host develop-qzapp run --as <login>
-- grep …`), all 30 roster logins, collected 2026-11-25 ~22:15Z:

```sh
gzcoord-carrier control-parity --window 2026-11-24T08:32:00Z 2026-11-25T22:00:00Z \
  --operator user --arrivals <login>=<file> … --json > cpA.json
```

**Why the window starts at 08:32:00Z.** #697 merged at 2026-11-24T08:24Z
and the fleet was upgraded at 08:26:44Z. The fix's `ctl.py` half writes
`timeout_s` on each `sent` line. The first such line is at 08:32:15Z, so
the fix was live on the operator from then. The window is one contiguous
span up to collection, and it keeps every upgrade inside it, including
the ones at 2026-11-25T08:21Z and 21:33Z.

Every count below is computed from `cpA.json`'s `pairs`. "Request by
InterWeave" is read from the addressees' own files: a pair counts as
requested by InterWeave when the addressee's file has an `agentd`
`request` line with carrier `interweave` for that id. The nine upgrade
times are the operator's `upgrade` `sent` lines.

## Result

| carrier | delivered | missed | p50 | p95 |
|---|---|---|---|---|
| relay | 27552 | 57 | 2 s | 5 s |
| interweave | 27354 | 127 | 2 s | 5 s |

The tool's causes: no-waiter 98, late 98, relay-only 2, timeout 57,
no-session 0. A `late` pair is no miss of the carrier alone (the tool's
CAUSE paragraph), so it is in neither `missed` count. No line was
skipped as unreadable, and no pair in the window is `unrecorded`.

The window holds **27,609 pairs of 1,080 requests**:

| outcome | pairs | of which the addressee got the request by InterWeave |
|---|---|---|
| both carriers | 27,354 | 27,354 |
| relay only, late | 98 | 98 |
| relay only, no-waiter | 98 | 45 |
| relay only, cause unknown | 2 | 1 |
| neither (timeout) | 57 | 27 |

## Where the misses are

**Every pair that is not `both`, but one, was asked in the ten minutes
after an `upgrade fabric`.** Across those ten-minute spans there are 65
requests and 1,515 pairs, and 254 of the pairs are not `both`. Outside
them there are 1,015 requests and 26,094 pairs, and 26,093 are `both`.
The exception is one `late` pair, python-dev-04's reply to the identity
request `01a20e07` at 14:48:51Z. It came by InterWeave 7 s after the
request, after fabric-ctl had left; that hour has no upgrade, and its
cause is not known.

The twelve requests behind the post-upgrade pairs:

| request at | op | pairs | outcome (cause) | s after upgrade | InterWeave reply after |
|---|---|---|---|---|---|
| 11-24 08:32:15 | identity | 25 | relay only (no-waiter) | 331 | 91 s |
| 11-24 08:32:43 | gateway | 30 | neither (timeout) | 359 | 63 s |
| 11-24 12:23:56 | identity | 17 | neither (timeout) | 39 | 25–30 s |
| 11-24 12:24:28 | gateway | 8 | relay only (no-waiter) | 71 | 32 s |
| 11-24 13:52:38 | identity | 26 | relay only (18 late, 8 no-waiter) | 173 | 15–23 s |
| 11-24 13:52:45 | gateway | 26 | relay only (late) | 180 | 8–16 s |
| 11-24 15:48:08 | identity | 22 | relay only (late) | 208 | 11–13 s |
| 11-24 15:48:14 | gateway | 21 | relay only (late) | 214 | 5–7 s |
| 11-25 08:22:43 | identity | 10 | neither (timeout) | 85 | 23–30 s |
| 11-25 08:23:07 | gateway | 10 | relay only (late) | 109 | 6–12 s |
| 11-25 15:04:32 | identity | 29 | relay only (no-waiter) | 63 | 35 s |
| 11-25 21:34:44 | presence | 30 | relay only (28 no-waiter, 2 unknown) | 72 | 1–35 s |

"InterWeave reply after" is the time from the request to the operator's
agentd logging the reply.

**What is shown and what is inferred.** That these misses follow the
upgrades is shown by the times above. That the restart is their
mechanism is shown only for 2026-11-25T15:04, which both journals cover:

- The operator's agentd exited for the upgrade at 15:03:29Z and was
  `Started` again at 15:04:38Z. fabric-ctl sent the identity request at
  15:04:32Z, while it was down, and wrote `session-lost` at 15:04:33Z.
- backend-dev-01's agentd (its journal, read as that account) restarted
  at 15:04:10Z. It said "also on InterWeave" at 15:04:12Z and answered
  the request at 15:04:32Z. At 15:04:53Z it logged
  `interweave: reply 01a2133c…32d5 to develop-qzapp/user not sent: no
  answer from the child in -10.9651 s`. The InterWeave child had not
  taken a send 41 s after the restart, and the line states a negative
  wait.

The operator's journal begins 2026-11-24T17:15Z, so for the 11-24
requests the only evidence of a restart is the upgrade's `sent` line.

## What it decides

- **Outside an upgrade's restart, the InterWeave leg matched the relay**:
  26,093 of 26,094 pairs both, over 1,015 requests of eight ops.
- **Inside it, InterWeave lags.** It answers 5–91 s after the request,
  or not at all, while the relay answers within the op's timeout. The
  first report's question, whether a no-waiter miss is a loss or an
  artefact of dual, has this answer for the post-upgrade case: 53 of the
  98 no-waiter pairs and 30 of the 57 timeouts have no InterWeave request
  line at the addressee: under InterWeave alone those requests would
  not have reached it, and the rest were answered late. An upgrade is the moment the
  operator most needs each account's answer.
- **Parity is not shown yet**, and `control_carrier` stays `dual`.
  Before the owner is asked:
  1. The InterWeave leg must be ready when agentd says it is on
     InterWeave, or fabric-ctl must wait for it after an upgrade, the
     operator's own agentd included. Until then an upgrade costs
     InterWeave-alone control a minute or more of answers. The
     negative wait in the child's log line is part of the same finding.
  2. The two `relay-only` pairs with no cause, and the one off-upgrade
     `late` pair, need a cause.

## What rule 18 still needs

Rule 18's report has four parts:

- **Every request id and addressee with the carriers that carried the
  request and the reply.** This record has the reply's carriers, and the
  request's InterWeave arrival from the addressees' files. A request's
  relay arrival is still logged nowhere, since agentd writes no line for
  a relay copy. That needs agentd and the tool to change.
- **p50 and p95 per carrier.** In the table above.
- **Each miss with its cause.** All but the two `relay-only` pairs have
  one, but "after an upgrade" names a time, not a mechanism. The restart
  is shown as the mechanism only for 11-25 15:04.
- **An `interweave-stop` drill mid-window, with every request still
  answered.** Not run. It stops the InterWeave leg on every account, so
  it waits on the owner's slot.

The report the owner's word is asked on is a later run. Its window holds
the drill and an upgrade, and the tool behind it also reports the
request's relay carrier.
