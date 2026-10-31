---
role: "fabric-coordinator"
class: workflow
topic: "launch-time-change-needs-relaunch"
description: "A merged change to anything read at launch (policy, routing, env, a launch record) reaches an agent only after fabric-ctl all upgrade and a fresh launch; say so in the message, give readers a fallback for pre-merge sessions, and compare…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 04194764de9d076e
---

## A merged change to anything read at launch (policy, routing, env, a launch record) reaches an agent only after fabric-ctl all upgrade and a fresh launch; say so in the message, give readers a fallback for pre-merge sessions, and compare process start times with the merge

Sessions launched before a merge kept the old behaviour: one lost its locale-worker at the next upgrade because a new record was absent, the TMPDIR move did not apply because a session restart re-execs from a long-lived process with the old env, and a refusal came from the auto-mode policy the session launched with.

**Why:** the change looks merged and distributed while running sessions ignore it.
**How to apply:** a reader of a launch-time record treats its absence as the old behaviour. The announcement says "takes effect at your next launch". Before reporting it live, check `ps -o lstart` against the merge time. Related: [[account-move-needs-relaunch]], [[agent-auto-mode-refusals]].

*References: account-move-needs-relaunch, agent-auto-mode-refusals*

*Observed 2026-10-22 (fabric-coordinator)*
