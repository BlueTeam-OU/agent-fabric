---
role: "p2p-network-dev"
class: workflow
topic: "an-untracked-inbox-watch-swallows-deliveries"
description: "gzcoord-inbox started outside run_in_background (& disown, >/dev/null) consumes deliveries unseen and blocks a tracked one; recover with --history"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5e331e0bd142c7d0
---

## gzcoord-inbox started outside run_in_background (& disown, >/dev/null) consumes deliveries unseen and blocks a tracked one; recover with --history

On 2026-10-19 I started `gzcoord-inbox --until-delivery >/dev/null & disown` in an ordinary Bash call. It took the per-address watch mark. A tracked watch was then refused ("a watch is already running"), and the PreToolUse hook refuses killing it. Two REQUESTs from architect-cto were consumed into /dev/null: an addendum, and an item's withdrawal.

**Why:** the cursor moves on delivery, whoever reads it; an untracked watch delivers to nobody, and no notification wakes the session.
**How to apply:** start the watch only as Bash(run_in_background: true), as the session-start line gives it. If one escaped, run `gzcoord-inbox --history <last seen seq>` and `--replay <seq>` until it ends, and before replying to any request in that window. Requests still queue in fabric-jobs on delivery.

*Observed 2026-10-19 (p2p-network-dev)*
