---
role: "p2p-network-dev"
class: domain
topic: "systemd-exit-status-via-execstoppost"
description: how to observe the exit status a systemd unit saw when SuccessExitStatus= makes it a success (not journalled); and $$ escaping in unit command lines
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 438a5928d8fac0b4
---

## how to observe the exit status a systemd unit saw when SuccessExitStatus= makes it a success (not journalled); and $$ escaping in unit command lines

A run that systemd counts a success (exit 0, or a status named by
`SuccessExitStatus=`) leaves no status line in the journal: "Main process
exited, code=…, status=…" is logged at debug for a success, notice only
for a failure. `ExecMainStatus` is reset when a restart starts the next
run, the same way `Result=` is (see [[systemd-result-resets-on-restart]]).
The oracle that works is an additive drop-in line
`ExecStopPost=/bin/sh -c 'echo "$$EXIT_CODE $$EXIT_STATUS" >> <file>'`.
`$$` is a literal `$` to the manager, so the shell expands the two
variables systemd sets for ExecStopPost. Measured 2026-11-03 with
transient `systemd-run --user` units: `exit 75` under
`SuccessExitStatus=75` → `exited 75`; a self-SIGKILL → `killed KILL`;
`exit 0` → `exited 0`. The same `$$` rule mangles a `sh -c '… $$'`
passed to `systemd-run` as ExecStart: put such a command in a script file.
Used in InterWeave #533
(`tests/desktop-e2e/tests/user_units.rs`, `Installed::exits`).

*References: systemd-result-resets-on-restart*

*Observed 2026-11-03 (p2p-network-dev)*
