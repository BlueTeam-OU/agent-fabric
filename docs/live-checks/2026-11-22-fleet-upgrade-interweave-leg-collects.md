# A fleet upgrade's InterWeave leg after the held restart — 2026-11-22

*Host develop-qzapp, account `user` (fabric-coordinator), job j868. This is
the read-back for j852 and BlueTeam-OU/agent-fabric#594 (merged
2026-11-14T06:26Z as `9b295fe6`). With #594, a fabric-ctl session open on
agentd's socket holds that agentd's restart for new code, for at most
`HOLD_MAX_S`. The claim covers the operator's own `control-arrivals.jsonl`
as of 2026-11-22T19:13Z. Only the operator's account writes `ctl` rows to
that log.*

## The question

j852 reported a fleet upgrade on 2026-11-13. The operator's own agentd
answered its own `upgrade`, exited for new code and closed fabric-ctl's
socket. Every reply after that came only by the relay. That is harmless
under `dual`. With control on InterWeave alone, those replies are lost.
The fix has to keep the InterWeave leg collecting every reply when the
operator's agentd restarts during the run.

## What was measured

For each `upgrade` request since 2026-11-14T12:00Z, count the accounts whose
reply fabric-ctl read on each carrier (`who=ctl`, `kind=reply`, `op=upgrade`):

```python
for r in rows:                       # ~/.local/state/agent-fabric/agents/user/control-arrivals.jsonl
    if r["who"] == "ctl" and r["kind"] == "reply" and r["op"] == "upgrade":
        seen[r["in_reply_to"]][r["carrier"]].add(r["from"])
```

| window (Z) | runs | InterWeave replies | relay-only |
|---|---|---|---|
| 11-14 12:21 – 11-15 00:04 | 7 | 29 of 30 | `user` (the operator itself) |
| 11-15 05:52 – 11-22 19:12 | 47 | 30 of 30 | none of the 30 (`fabric-probe`, which is not in the upgrade table, answers by relay) |
| 11-17 13:58, 11-22 16:24:50 | 2 | 0 | all 30 |

The agentd journal shows the operator's agentd exiting with "the fabric
moved (upgrade fabric)" during runs in the second row. Five of them were on
11-22, at 00:49, 08:37, 09:44, 13:41 and 16:24:47Z. On the 16:23Z run, for
example, it answered its own upgrade at 16:24:46Z and then exited. That
run's InterWeave leg still read all 30 replies, the operator's own included.

## What it decides

- **j852 is closed.** In every run that started with the operator's socket
  up, the InterWeave leg collected every reply after the restart.
- **The first row came before the self-loopback.** In those 7 runs, the
  operator's own agentd logged no InterWeave `request` row for its own
  upgrade. The loop-back (j245) did not reach it until 11-15 05:51Z, so this
  gap was not caused by the restart. It has not appeared since.
- **The third row is a run sent while the operator's agentd was down.**
  The 16:24:50Z run was sent 3 s after the agentd's 16:24:47Z exit. systemd
  restarted it at 16:24:53Z. fabric-ctl found no socket, sent by relay alone
  and said so (`_second_carrier`). The 29 InterWeave copies of the replies
  reached the new agentd with no waiter. With control on InterWeave alone,
  the same run says that nothing was sent. The reply is not silently lost,
  so this does not block carrier-only. To avoid it, start the next run once
  the operator's agentd is back up. The 11-17 13:58Z run has the same
  shape: two minutes after a run, with 29 no-waiter rows. The journal no
  longer has 11-17, so its restart is not confirmed.
- The 2026-11-22T19:12Z distribution (`fabric-ctl all upgrade fabric`) found
  all 30 accounts already on `4f5b61d5`, so it restarted no agentd and
  exercises nothing in this record.
