---
role: "fabric-coordinator"
class: workflow
topic: "wait-by-background-exit-not-sleep"
description: "Owner 2026-10-12 — wait for PR checks/merges with a background command whose exit notifies (gh pr checks --watch, fabric-pr wait-merged), never sleep loops in the foreground"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a3fcbae91441ee62
---

## Owner 2026-10-12 — wait for PR checks/merges with a background command whose exit notifies (gh pr checks --watch, fabric-pr wait-merged), never sleep loops in the foreground

The owner noticed `sleep 15; …` and `for …; sleep 30; done` polling of PR checks in my foreground calls,
and remembered that waits used to be a background watcher that came back by itself.

**Why:** a foreground sleep loop holds the session and burns turns doing nothing; the exit of a
background process is the notification.
**How to apply:** checks → `gh pr checks <N> --watch --fail-fast` with `run_in_background`; a merge →
`fabric-pr wait-merged <N>` in the background; a review → the review agent's own completion. Never a
Monitor for these (its expiry rings; see [[inbox-wait-not-monitor]]), never `sleep` in the foreground.

*References: inbox-wait-not-monitor*

*Observed 2026-10-12 (fabric-coordinator)*
