---
role: "fabric-coordinator"
class: solution
topic: "routing-change-needs-managed-reinstall"
description: "after a routing/effort.json change merges, every review dispatch is denied (\"agent file says effort high, launch resolves medium\") until the owner reinstalls managed settings at main's sha"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a99ddb17585c2c35
---

## after a routing/effort.json change merges, every review dispatch is denied ("agent file says effort high, launch resolves medium") until the owner reinstalls managed settings at main's sha

2026-11-12: 8d38edf2 moved code-plan and code-review to effort high. Agent files are written from the
login's checkout at launch, but the dispatch guard runs from the managed snapshot
(/usr/local/lib/agent-fabric/managed/current, then fabric-80e612ff, older than 8d38edf2), whose routing
still said medium. So every review class dispatch on the host was denied. python-dev-03 and
rust-services-dev-01 reported it, and a relaunch did not help. `fabric-managed check` showed "drifted".
The owner ran `! sudo ~/projects/agent-fabric/bin/fabric-managed install --sha <origin/main sha>`.
After that, reviews dispatched again in running sessions with no relaunch: #573 round 3, and my #578.

**How to apply:** after any merge that touches routing/ or the guards, run `fabric-managed check` and
ask the owner for the install before agents hit the denial. Job j810 is the design fix: the guard
should not compare against a snapshot that is behind the routing the agent file was written from.
Related: [[adr-043-managed-settings-option-1]], [[adr-068-managed-reinstall-gates-readback]].

A similar lag affects the commit hooks, but there it is the main checkout's code, not the snapshot
(core.hooksPath = ~/projects/agent-fabric/policies/githooks). A branch that changes adr.py's generated index format
must commit with `git -c core.hooksPath=$PWD/policies/githooks commit`, or the old adr.py refuses the
new index as stale (j768, #578).

*References: adr-043-managed-settings-option-1, adr-068-managed-reinstall-gates-readback*

*Anchors: `tools/fabric/guards/dispatch_guard.py::launch_pins`*

*Observed 2026-11-12 (fabric-coordinator)*
