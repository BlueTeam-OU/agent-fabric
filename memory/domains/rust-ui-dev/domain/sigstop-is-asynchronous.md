---
role: "rust-ui-dev"
class: domain
topic: "sigstop-is-asynchronous"
description: "kill -STOP returns before a multi-threaded process is stopped; a test that needs it stopped must wait for every /proc/<pid>/task/*/stat to read T"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: herdr
    working_copy: herdr
derived_from:
  - 03f34c4360b7d1cb
---

## kill -STOP returns before a multi-threaded process is stopped; a test that needs it stopped must wait for every /proc/<pid>/task/*/stat to read T

`kill -STOP <pid>` (kill(2)) returns before the target is stopped. The kernel wakes one thread to start the group stop, and the other threads run user code until that thread is scheduled. Under CPU load that can take milliseconds.

Measured 2026-10-18 on InterWeave (j109, PR BlueTeam-OU/InterWeave#299):
- 0.3 ms after kill returned, the daemon was still `R`.
- It then served a client's IPC close 8 ms later.
- The desktop-e2e case `a_second_signal_while_closing_ends_the_client_at_once` failed 3 times in 70 runs under 12 niced busy loops on 10 CPUs. It never failed in 20 quiet runs.
- After the fix it passed 100 of 100 under the same load.

The fix: `harness::stop` waits until every thread of the process reads `T`.

The rule: a test whose precondition is "process X is stopped" waits on /proc state; it never trusts kill's return. To reproduce a CI-only flake, run the case in a loop under niced CPU load; a quiet loop hides it.

Related: [[zbus-fd-cloexec-window]]

*References: zbus-fd-cloexec-window*

*Observed 2026-10-18 (rust-ui-dev)*
