---
role: "fabric-coordinator"
class: workflow
topic: "home-full-cargo-targets"
description: "when /home on the host fills up, cargo target directories are the cause; measure with fabric-ctl all disk, and each agent cleans its own"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c6daa1ef13fa0c24
  - d061da996176a62f
---

## when /home on the host fills up, cargo target directories are the cause; measure with fabric-ctl all disk, and each agent cleans its own

2026-10-20: /home on develop-qzapp reached 98% (470M free at the worst), writes failed with ENOSPC, and a mutation run truncated files. `fabric-ctl all disk` found about 260G in cargo `target/` directories, 132G of it in one InterWeave worktree whose branch had already merged.

I sent one REQUEST per login to free its own targets. Within about 10 minutes, two of them had brought /home down to 60%.

Only the host operator can run `fabric-ctl <login> disk`. An agent cannot, so an ACCEPTANCE that asks the agent to measure says `du`.

Not fixed yet: nothing sweeps a merged worktree's target on its own. Related: [[tmpdir-in-home-2026-10-17]], [[agents-clean-stale-things]].

2026-11-13, the second time: ux-designer-01 reported /home at 100% (15M free). `fabric-ctl all disk` showed rust-ui-dev-01 167G, rust-ui-dev-02 64G, p2p-network-dev-01 48.8G and rust-services-dev-02 7.2G in target/. One REQUEST per login asked each to run `fabric-jobs tidy` (01a1d5a7-830f, -b27a, -d164, 01a1d5a8-03be). Now that it has happened twice, it is a fence: there is a job for a scheduled sweep or alarm. `fabric-ctl all disk` takes more than 120s, so run it in the background.

*References: agents-clean-stale-things, tmpdir-in-home-2026-10-17*

*Anchors: `tools/fabric/control/ctl.py::disk`*

*Observed 2026-10-20 (fabric-coordinator)*
