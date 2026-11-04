---
role: "p2p-network-dev"
class: domain
topic: "a-blocking-lookup-in-a-fail-closed-check-is-fail-stuck"
description: "An OS lookup that can hang (getpwuid_r/getgrgid_r through sssd/LDAP) inside a fail-closed security check makes it fail-stuck; give the read a deadline on a helper thread, cap leaked threads with a gate that WAITS (not refuses) under one…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c249eb39298fa8af
---

## An OS lookup that can hang (getpwuid_r/getgrgid_r through sssd/LDAP) inside a fail-closed security check makes it fail-stuck; give the read a deadline on a helper thread, cap leaked threads with a gate that WAITS (not refuses) under one budget per caller, and inject the gate through the test seam so parallel tests don't share it

A check that refuses when it "cannot read" an answer does not fail closed
if the read can simply never return: a hung name service blocks the start.
Three design mistakes came up in turn on InterWeave #236 (2026-10-09,
ADR-0028 "The name-service read is bounded"):

1. **No deadline.** The private-group predicate's NSS reads had no bound.
   Fix: run them on a helper thread with `recv_timeout`, refuse on expiry
   naming the cause, and leave the thread to finish or leak.
2. **"One leak per start" was false.** The predicate also runs on every
   trust-overlay write in a running daemon, so each admin call under a hung
   service would leak one more thread. Fix: a process-wide gate allowing at
   most one outstanding read.
3. **A gate that refuses also refuses healthy work.** Two threads judging
   at the same moment: the second was refused although the service was
   fine. Fix: a caller that finds the gate taken WAITS (Mutex + Condvar),
   and the wait and its own read share one budget counted from its
   request, so a slow-then-hung read refuses at 5 s, not 5 + 5 s. The gate
   is given back by a Drop on the helper thread, panics included.

A test trap: the process-wide gate made two existing tests refuse each
other, because Rust tests in one binary run in parallel threads of one
process (257 of 300 runs of the filter failed). The fix put the gate behind
the trait seam the fakes already implement (`NameService::outstanding()`,
a required method with no default), so each fake carries its own gate and
production returns the process's.

**How to apply:** for any syscall or library lookup inside an admission or
security predicate, ask whether it can block forever. If it can, give it a
deadline, a bounded leak, a wait-don't-refuse gate and one budget per
caller. Put any process-global state the check uses behind the same seam
its tests fake. Verify with a sleeping fake and the mutations "recv instead
of recv_timeout", "refuse instead of wait" and "release without notify".

*Observed 2026-10-25 (p2p-network-dev)*
