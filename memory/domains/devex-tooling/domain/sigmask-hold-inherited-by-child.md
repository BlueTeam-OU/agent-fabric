---
role: "devex-tooling"
class: domain
topic: "sigmask-hold-inherited-by-child"
description: blocking signals around a Popen spawn blocks them in the child too; put the mask back in preexec_fn
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 24af931351fd7077
---

## blocking signals around a Popen spawn blocks them in the child too; put the mask back in preexec_fn

A `pthread_sigmask(SIG_BLOCK, …)` held across `subprocess.Popen` (to record the
pid before a handler can run) is inherited by the child through fork and exec:
`restore_signals` resets dispositions only, never the mask. The child and all
under it ran with TERM/INT/HUP blocked, so `timeout`'s TERM at the bound and
cleanup's TERM never landed (a 1 s bound ran 6 s). Fix: `preexec_fn=lambda:
signal.pthread_sigmask(signal.SIG_SETMASK, held)`, safe in a single-threaded
caller. Test it by reading the child's `SigBlk:` from `/proc/self/status`
against the caller's, plus a 1 s bound timed (agent-fabric PR 482 round 1 F1,
f91bfe40). Related: [[kill-by-pidfd-reverify-after-open]].

*References: kill-by-pidfd-reverify-after-open*

*Observed 2026-11-04 (devex-tooling)*
