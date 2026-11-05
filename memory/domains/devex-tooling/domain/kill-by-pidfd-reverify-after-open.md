---
role: "devex-tooling"
class: domain
topic: "kill-by-pidfd-reverify-after-open"
description: "ending a tool's child processes robustly — TERM, grace, KILL, wait — without hitting a reused pid; and the test traps that hid it (j268, audit F15)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3d262b2235e8feff
---

## ending a tool's child processes robustly — TERM, grace, KILL, wait — without hitting a reused pid; and the test traps that hid it (j268, audit F15)

To end processes found by a /proc scan without ever signalling a reused pid:
os.pidfd_open(pid), THEN re-check ownership (session/cwd/uid) on that pid — the
fd now pins the process, so a pid reused before the open is refused by the
check, and one that dies after it makes pidfd_send_signal a no-op. A pidfd reads
ready (select) once its process exits, child or not: that is the bounded wait
after KILL. killpg(pgid) is safe only while the leader is your unreaped child
(os.waitid WNOHANG|WNOWAIT succeeds); once reaped and the group is empty the id
can be a stranger's. Always run the KILL pass after the grace, not only when the
grace ran out: a member that handled TERM may have forked first.
Test traps: Popen.poll() reaps — check "reaped by cleanup" with waitid WNOWAIT
BEFORE poll(); never monkeypatch os.close (subprocess uses it, the next git call
deadlocks on its own pipe); a KILL lands too fast for "not waited for" to show —
record the wait calls in a scripted test instead.
Code: agent-fabric tools/fabric/github/trial_worktree.py claim/signal_all/cleanup
(branch develop-qzapp/devex-tooling/for/user/j268-trial-merge-f14-f15). Related:
[[proc-scan-not-atomic-against-fork]].

*References: proc-scan-not-atomic-against-fork*

*Observed 2026-11-01 (devex-tooling)*
