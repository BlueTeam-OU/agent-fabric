---
role: "fabric-coordinator"
class: workflow
topic: "drain-fabric-project-bundle-last"
description: "In a multi-project drain, assemble agent-fabric's own project bundle LAST (or re-run it): another bundle's new or re-described domain slice leaves agent-fabric's role INDEX.md drifted"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1d9de5d8af0c93c2
---

## In a multi-project drain, assemble agent-fabric's own project bundle LAST (or re-run it): another bundle's new or re-described domain slice leaves agent-fabric's role INDEX.md drifted

2026-10-28, architect-cto-01's drain (j403, #417 round 9 F16): I assembled the agent-fabric bundles first, then gzapp's and InterWeave's against the same fabric root. Those runs added one domain slice and re-described another under `memory/domains/architect-cto/`, and agent-fabric's own `.agent-fabric/memory/architect-cto/INDEX.md` (which lists the role's domain slices) was not rebuilt by them, so the corpus lint failed at the head. Re-running the agent-fabric bundle (same stamp, same claims) rebuilt it: d8e6170c. Running a project's half with `--working-copy` on a scratch worktree is fine for the fabric side; the project's own commit waits until the fabric commit is on main (fabric-ref).

**Why:** each assemble run re-indexes only the working copy it is given; the fabric's own project is a working copy like any other.

**How to apply:** order the bundles agent-fabric last, then `AGENT_FABRIC_ROOT=<wt> lint.py --no-siblings` must be clean before the commit. Run the suite with `AGENT_FABRIC_ROOT=<wt>` too: this session's root is the launch checkout, and test_registry_id loaded its stale control/jobs.py ([[lint-in-worktree-root]]).

*References: lint-in-worktree-root*

*Anchors: `tools/fabric/assemble.py::--bundle`, `.agent-fabric/memory/architect-cto/INDEX.md`*

*Observed 2026-10-28 (fabric-coordinator)*
