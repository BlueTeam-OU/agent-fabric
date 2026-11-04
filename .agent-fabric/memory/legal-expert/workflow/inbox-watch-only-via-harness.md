---
role: "legal-expert"
class: workflow
topic: "inbox-watch-only-via-harness"
description: "Start the GZCoord inbox watch only as a harness background Bash task; a detached one (& disown) cannot be killed and its delivery is lost"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "legal-expert-ch"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 230af286ab79db01
---

## Start the GZCoord inbox watch only as a harness background Bash task; a detached one (& disown) cannot be killed and its delivery is lost

Run `gzcoord-inbox --until-delivery` only as a Bash call with `run_in_background: true`. Never start it from a shell with `& disown` or `>/dev/null`.

On 2026-10-25 I started one detached by mistake (pid 1824688, output sent to /dev/null). The PreToolUse hook refuses to kill an inbox watch, by pattern or by pid. gzcoord-inbox also refuses to run a second watch. So the detached watch holds the watch mark until it ends on its own, and any message it delivers is consumed with no notification.

**How to apply:** if this happens again, do not try to kill it. When it ends, read `fabric-history` for anything delivered in that window, then arm the watch the proper way.

*Anchors: `runtime/claude-code/hooks/watch-on-stop.py::gzcoord-inbox --until-delivery`*

*Observed 2026-10-25 (legal-expert)*
