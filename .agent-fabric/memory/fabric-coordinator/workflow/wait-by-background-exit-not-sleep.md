---
role: "fabric-coordinator"
class: workflow
topic: "wait-by-background-exit-not-sleep"
description: "Owner 2026-10-12 — wait for PR checks/merges with a background command whose exit notifies (fabric-pr wait-merged; checks only with gh pr checks --watch --interval 120), never sleep loops in the foreground"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4a390ac264ff03f2
  - a3fcbae91441ee62
---

## Owner 2026-10-12 — wait for PR checks/merges with a background command whose exit notifies (fabric-pr wait-merged; checks only with gh pr checks --watch --interval 120), never sleep loops in the foreground

The owner noticed `sleep 15; …` and `for …; sleep 30; done` polling of PR checks in my foreground calls,
and remembered that waits used to be a background watcher that came back by itself.

**Why:** a foreground sleep loop holds the session and burns turns doing nothing; the exit of a
background process is the notification.
**How to apply:** merges → `fabric-pr wait-merged <N>` in the background (budget-aware,
backs off x1.5 to 5 min since #335); checks before an arm → `gh pr checks <N> --watch
--interval 120`, never the bare `--watch`, which polls GraphQL every 10 s against the one quota the
whole fleet shares (core 0/5000 on 2026-10-20; the owner: find another strategy than polling,
python-dev-02's REQUEST 01a157f9 makes wait-merged budget-aware); a review → the review agent's own completion. Never a
Monitor for these (its expiry rings; see [[inbox-wait-not-monitor]]), never `sleep` in the foreground.

*References: inbox-wait-not-monitor*

*Anchors: `tools/fabric/github/wait_merged.py::--interval`*

*Observed 2026-10-20 (fabric-coordinator)*
