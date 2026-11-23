# Control parity, relay and InterWeave side by side — 2026-11-23

*Host develop-qzapp, account `user` (fabric-coordinator), job j956. The
first run of `gzcoord-carrier control-parity` (#655) over a full
week of `control_carrier` `dual`. It is the report that ADR-029 rule 18
asks for before control names InterWeave alone. The tool measures;
the owner decides.*

## What was run

Each account's `~/.local/state/agent-fabric/agents/<login>/control-arrivals.jsonl`,
read as that account (`fabric-host develop-qzapp run --as <login> -- cat …`),
all 30 roster logins, collected 2026-11-23 ~21:40Z:

```sh
gzcoord-carrier control-parity --window 2026-11-16T00:00:00Z 2026-11-23T00:00:00Z \
  --operator user --arrivals <login>=<file> … [--json]
```

Only the operator's file gives pairs and causes (the tool's contract); the
other 29 are listed and contribute nothing yet.

## Result

| carrier | delivered | missed | p50 | p95 |
|---|---|---|---|---|
| relay | 128075 | 72 | 1 s | 5 s |
| interweave | 125036 | 786 | 1 s | 5 s |

Causes of InterWeave's misses: no-waiter 693, relay-only (cause unknown) 21,
timeout 72. Two lines were skipped as unreadable.

The window holds 168,979 pairs. 89,096 of them are `unrecorded`: replies to
requests made before fabric-ctl wrote a `sent` line, which starts at
2026-11-18T13:50:52Z. The tool counts those as delivered but never as missed,
since an account that did not answer cannot be seen for them.
The **79,883 recorded pairs** are the measurement:

| outcome | pairs | requests | by op |
|---|---|---|---|
| both carriers | 79,097 | | |
| relay only, no-waiter | 693 | 82 | identity 407, gateway 247, upgrade 29, jobs 6, session 3, ping 1 |
| relay only, cause unknown | 21 | 10 | gateway 10, identity 6, ping 5 |
| neither (timeout) | 72 | 9 | gateway 37, identity 34, upgrade 1 |

- The InterWeave leg answered 99.02 % of recorded pairs; the relay 99.91 %.
  The 72 timeouts are misses of both carriers, so they say nothing between them.
- InterWeave alone would have lost a further **714 replies (0.89 %)**.
  No-waiter means the operator's agentd routed the reply and no fabric-ctl
  session was waiting for it.
- The no-waiter misses are mostly bursts. 23 requests account for 562 of the
  693 misses, each losing 19–29 accounts, which is most or all of the fleet:
  identity 14, gateway 8, upgrade 1. The other 59 requests lost one to ten
  accounts each, and 38 of them lost one.
- The agentd journal for 2026-11-18..23 holds no start or stop line, so this
  record does **not** show whether the bursts coincide with the operator's
  agentd restarting. The 2026-11-22 record
  (2026-11-22-fleet-upgrade-interweave-leg-collects.md) names that restart as
  one known source of no-waiter.
- The fabric-probe login (no roster row) appears only in the unrecorded pairs,
  where every pair is relay-only. That is expected and counted in nothing.

## What it decides

- **Parity is not shown.** On this week, control on InterWeave alone would have
  lost about one reply in 112. `control_carrier` stays `dual`, and ADR-029
  rule 18 does not yet name InterWeave alone.
- Next, the no-waiter cause must be found and closed, and the 21 unexplained
  pairs explained. A later run of the same command over a window starting
  after that fix is the report the owner's word is asked on.
