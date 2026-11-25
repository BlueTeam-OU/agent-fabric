# `fabric-ctl <account> state` and `FABRIC_STATE_READ=op` under dual — 2026-11-23

agent-fabric ADR-029 rule 16 moves the readers of an account's newest state
record from the relay's stored history to a question asked of the account
(the `state` op, #640; `states` reads through it under the second carrier or
under `FABRIC_STATE_READ=op`). Until this check the op had been exercised by
its suites only. Whether a real fleet answers it needed a read-back.

**Run.** 2026-11-23 about 16:52Z to 16:53Z on develop-qzapp, from
python-dev-02, main at e4384768 plus the branch's one test commit (07518414,
which touches no code). The fleet's `control_carrier` is `dual` (the
override line `states` printed says so). Each command ran from the working
copy's `bin/fabric-ctl`.

## Result

| command | outcome |
|---|---|
| `fabric-ctl python-dev-02 state` | exit 0; one row: `working  python-dev  1` (the caller's own record, answered by its own agentd) |
| `fabric-ctl python-dev-01 state` | exit 0; one row: `working  python-dev  1`, asked of that account's agentd |
| `fabric-ctl all state --json` | read for the first two accounts only: each `status: ok`, `op: state`, a v1 `state` record whose `from` and `address` agree with the account asked, `carrier: "interweave"`, `relay_copy: "same"`; the two answers took 10 and 11 ms. The other 28 accounts' JSON was not read; the next row covers all 30 |
| `fabric-ctl all state` | 30 rows, one per placed account, none `unknown`; states working, idle or blocked, with role and session count |
| `FABRIC_STATE_READ=op fabric-ctl all states` | stderr said `FABRIC_STATE_READ=op: state records are asked of the accounts, not read from the relay (control_carrier is 'dual')`; 30 rows, the same states as the `state` table taken seconds apart |

- What the override does not touch: `state` is an op under any carrier, so
  of the commands run here `FABRIC_STATE_READ` changes only `states`; it
  also moves `fabric-jobs waits` and the pool holder's reads, not run here.

## Not verified

- The JSON form (`from`, `address`, carrier) was read for two accounts,
  not 30.
- Each of the 30 accounts' records was not compared with its own file; the
  agreement checked is between the `state` op and `states` under the
  override, and the record's `from` against the address asked.
- An unreachable or silent account (an `error`, not an empty record) was not
  provoked on the live fleet; it is the suite's (`tests/test_control_state_op.py`).
- A fleet with `control_carrier` set to the second carrier alone was not run.

Recorded by python-dev-02 (REPLY 01a20954, correction 01a20a29); committed
by fabric-coordinator, the directory being outside python-dev's entry.
