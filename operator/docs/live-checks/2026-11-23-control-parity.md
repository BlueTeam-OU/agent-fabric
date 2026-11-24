# Control parity, relay and InterWeave side by side — 2026-11-23

*Host develop-qzapp, account `user` (fabric-coordinator), job j956. The
first run of `gzcoord-carrier control-parity` (#655) over a
week of `control_carrier` `dual`, 4.4 days of it with recorded pairs. It is a first measurement toward the report ADR-029
rule 18 asks for before control names InterWeave alone, not that report: see
*What rule 18 still needs* below. The tool measures;
the owner decides.*

## What was run

Each account's `~/.local/state/agent-fabric/agents/<login>/control-arrivals.jsonl`,
read as that account (`fabric-host develop-qzapp run --as <login> -- cat …`),
all 30 roster logins, collected 2026-11-23 ~21:40Z:

```sh
gzcoord-carrier control-parity --window 2026-11-16T00:00:00Z 2026-11-23T00:00:00Z \
  --operator user --arrivals <login>=<file> … --json > cp.json
```

The Result table is the tool's own summary. Every figure after it is computed from
`cp.json`'s `pairs` list, one dict per (request, addressee) with `outcome`,
`cause`, `op`, `t`, `<carrier>_s` and `unrecorded`:

```python
P = json.load(open("cp.json"))["pairs"]
rec = [p for p in P if not p.get("unrecorded")]      # the measurement
unrec = [p for p in P if p.get("unrecorded")]        # in window, before any `sent` line
Counter((p["outcome"], p.get("cause")) for p in rec)  # the outcome table
Counter(p["op"] for p in rec if p.get("cause") == c) # its by-op column, per cause c
Counter(Counter(p["id"] for p in rec if p.get("cause") == "no-waiter").values())  # bursts
# p50/p95 over rec: nearest rank of p["<carrier>_s"] where present
```

The per-pair listing itself is the tool's output, kept with the arrival logs
that produced it, not in this repository.

Only the operator's file gives pairs and causes (the tool's contract); the
other 29 are listed and contribute nothing yet.

## Result

| carrier | delivered | missed | p50 | p95 |
|---|---|---|---|---|
| relay | 128075 | 72 | 1 s | 5 s |
| interweave | 125036 | 786 | 1 s | 5 s |

Causes of InterWeave's misses: no-waiter 693, relay-only (cause unknown) 21,
timeout 72.

The tool's p50 and p95 above include the unrecorded pairs, which it times from
the first copy's arrival, not from a request. Over the 79,883 recorded pairs
alone, nearest rank: relay p50 2 s, p95 6 s; InterWeave p50 2 s, p95 5 s.

Two lines were skipped as unreadable. Both are runs of NUL bytes: line 8306 of
p2p-network-dev-01's file and line 9199 of p2p-network-dev-02's. Neither is in
the operator's file, the only one the tool reads pairs from, so neither changes
a pair.

The window holds 128,147 pairs. 48,264 of them are `unrecorded`: replies to
requests made before fabric-ctl wrote a `sent` line, which starts at
2026-11-18T13:50:52Z. The tool's own `unrecorded` field (89,096) counts the whole
file, not the window; 48,264 is the count of pairs in the window. The tool counts
an unrecorded pair as delivered by each carrier that brought a copy, and never as
missed. 2,325 of them came by the relay alone, 1,484 of them fabric-probe's.
That is why the InterWeave row adds up to 125,822, not 128,147.
The **79,883 recorded pairs** are the measurement:

| outcome | pairs | requests | by op |
|---|---|---|---|
| both carriers | 79,097 | | |
| relay only, no-waiter | 693 | 82 | identity 407, gateway 247, upgrade 29, jobs 6, session 3, ping 1 |
| relay only, cause unknown | 21 | 10 | gateway 10, identity 6, ping 5 |
| neither (timeout) | 72 | 9 | gateway 37, identity 34, upgrade 1 |

- The InterWeave leg answered 99.02 % of recorded pairs; the relay 99.91 %.
  The 72 timeouts are misses of both carriers, so they say nothing between them.
- Under dual, the InterWeave leg missed **714 replies (0.89 %)** that the relay
  delivered. Whether control on InterWeave alone would have lost them is
  **not shown**: a no-waiter miss can be a measurement of dual itself (fabric-ctl
  stops reading once the relay copies are in, or the request went by relay
  alone while the operator's agentd was down) rather than a loss. No-waiter means the operator's agentd routed the reply and no fabric-ctl
  session was waiting for it.
- The no-waiter misses are mostly bursts. 23 requests account for 562 of the
  693 misses, each losing 19–29 accounts, which is most or all of the fleet:
  identity 14, gateway 8, upgrade 1. The other 59 requests lost one to ten
  accounts each, and 38 of them lost one.
- The operator's agentd journal starts 2026-11-23T18:14Z: the earlier lines
  are rotated away, so this record does **not** show whether the bursts coincide with the operator's
  agentd restarting. The 2026-11-22 record
  (2026-11-22-fleet-upgrade-interweave-leg-collects.md) names that restart as
  one known source of no-waiter.
- The fabric-probe login (no roster row) appears only in the unrecorded pairs,
  where every pair is relay-only: counted in the relay's delivered, never as an
  InterWeave miss.

## What it decides

- **Parity is not shown.** Under dual the InterWeave leg missed about one
  recorded reply in 112, and until each miss has a cause it cannot be counted
  as harmless. `control_carrier` stays `dual`, and ADR-029
  rule 18 does not yet name InterWeave alone.
- Next, the no-waiter cause must be found (python-dev-04, j160) and closed, and the 21 unexplained
  pairs explained. A later run with `--drill`, over a window starting after that fix, is
  the report the owner's word is asked on (*What rule 18 still needs*).

## What rule 18 still needs

ADR-029 rule 18 asks for four things: every request id and addressee with its
carriers, p50 and p95 per carrier, each miss with its cause, and an
`interweave-stop` drill mid-window with every request still answered. This
record has the first in the tool's per-pair output and the second over recorded
pairs. It has the third except for the 21 pairs whose cause is unknown, and it
has no drill. The report the owner's word is asked on is a later run of the same
command with `--drill START END` over a window that starts after the no-waiter
fix and holds an `interweave-stop` drill.
