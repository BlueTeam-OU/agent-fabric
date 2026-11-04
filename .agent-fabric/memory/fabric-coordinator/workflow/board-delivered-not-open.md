---
role: "fabric-coordinator"
class: workflow
topic: "board-delivered-not-open"
description: "Reporting other agents' open jobs: fabric-ctl all jobs lists delivered jobs, which the agent's own session-start line does not count as open; report active/queued/paused/blocked apart from delivered"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a368c12fb4435b27
---

## Reporting other agents' open jobs: fabric-ctl all jobs lists delivered jobs, which the agent's own session-start line does not count as open; report active/queued/paused/blocked apart from delivered

`fabric-ctl all jobs` runs `fabric-jobs list --json --stored` as each login (tools/fabric/control/jobs.py), so it is
the same file the agent reads — but it includes `delivered`, and the agent's session-start line counts only active,
queued, paused and blocked (runtime/claude-code/hooks/session-start.py jobs_line). On 2026-10-18 the owner doubted my
count: 126 jobs for the other agents, of which 105 delivered, so the agents saw 21. `--stored` also leaves a cleared
blocker shown as blocked on the board, while the agent sees "blocker cleared".

**Why:** a count with delivered folded in overstates the fleet's backlog five-fold and misleads the owner.

**How to apply:** give the owner open work (active/queued/paused/blocked) and delivered as separate numbers; name
cleared blockers as such.

*Anchors: `tools/fabric/control/jobs.py::--stored`, `runtime/claude-code/hooks/session-start.py::jobs_line`*

*Observed 2026-10-18 (fabric-coordinator)*
