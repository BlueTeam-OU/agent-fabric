---
role: "fabric-coordinator"
class: workflow
topic: "home-full-cargo-targets"
description: "when /home on the host fills up, cargo target directories are the cause; measure with fabric-ctl all disk, and each agent cleans its own"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d061da996176a62f
---

## when /home on the host fills up, cargo target directories are the cause; measure with fabric-ctl all disk, and each agent cleans its own

2026-10-20: /home on develop-qzapp reached 98% (470M free at the worst), writes failed with ENOSPC, and a mutation run truncated files. `fabric-ctl all disk` found about 260G in cargo `target/` directories, 132G of it in one InterWeave worktree whose branch had already merged.

I sent one REQUEST per login to free its own targets. Within about 10 minutes, two of them had brought /home down to 60%.

Only the host operator can run `fabric-ctl <login> disk`. An agent cannot, so an ACCEPTANCE that asks the agent to measure says `du`.

Not fixed yet: nothing sweeps a merged worktree's target on its own. Related: [[tmpdir-in-home-2026-10-17]], [[agents-clean-stale-things]].

*References: agents-clean-stale-things, tmpdir-in-home-2026-10-17*

*Anchors: `tools/fabric/control/ctl.py::disk`*

*Observed 2026-10-20 (fabric-coordinator)*
