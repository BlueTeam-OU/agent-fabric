# 2026-11-04: does an idle account's harness-restart bring its session back without an Enter?

**Why.** ADR-048 §5 rule 4 (A 2026-11-04) says the harness pane runs `enter --wait`
except once, after `fabric-ctl <login|all> harness-restart` of an account whose
sessions are all idle, when it runs `--resume`. The verb (agent-fabric #478) reads
the result back itself: a new MainPID for the unit, then a session whose claude
started after the restart, from the account's own presence. This records what it
read on develop-qzapp.

**What decides it.** A row `restarted` means the verb saw both. A working account
must be `refused` with nothing stopped.

**Measured on develop-qzapp, 2026-11-04, by fabric-coordinator (`user`), fabric at
da2a3d9f (main with #478):**

| account | state before | when | verb's row |
|---|---|---|---|
| flutter-dev-02 | working (12:48Z), then idle | 13:56Z | `restarted  new server (MainPID 303091); session running since 2026-11-04T13:56:12.670Z` |
| p2p-network-dev-02 | idle since 12:33:36Z | 12:48Z | `restarted  new server (MainPID 3511303); session running since 2026-11-04T12:48:52.710Z` |
| python-dev-03 | idle since 12:47:07Z | 12:49Z | `restarted  new server (MainPID 3517755); session running since 2026-11-04T12:49:46.250Z` |

flutter-dev-02 was taken by a loop that read `fabric-ctl flutter-dev-02 states`
every 150 s and ran the restart only once the state read `idle`; until then
nothing was run on it.

**Not measured here.** The earlier `fabric-ctl all harness-restart` of 12:02–12:10Z,
which another session of this role ran, is not in this record: its rows were not
kept. The marker's removal on a failed restart was not exercised live; it is
covered by `tests/test_harness_restart.py` only. Own account `user` was not
restarted (it would end the session).

**Decision.** The exception holds as built: an idle account's session came back
by itself on all three accounts, each read back by the account's presence.
