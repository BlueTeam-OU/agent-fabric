---
role: "fabric-coordinator"
class: workflow
topic: "drain-project-half-excludes-coordinator-bundle"
description: "A project drain half leaves out the coordinator's own bundle when that project's taxonomy binds no fabric-coordinator; move the memories to agent-fabric's memory instead"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6864d804c8a435eb
---

## A project drain half leaves out the coordinator's own bundle when that project's taxonomy binds no fabric-coordinator; move the memories to agent-fabric's memory instead

The coordinator's harvest files a memory under whatever project's working copy it was written in. For blueteam.ee (#17, review F1–F3) and gzapi.ge (#33, j658, 2026-11-09), user/<project>.tar held only agent-fabric knowledge, such as the owner's standing word on arming drain PRs. Neither taxonomy binds fabric-coordinator.

**Why:** a slice about the fabric's tools does not belong in a project's corpus. The review caught it on blueteam.ee.

**How to apply:** before assembling a project half, list `drain/user/<project>.tar`'s claims. If they are about the fabric, move the source memories into `~/.claude/projects/-home-user-projects-agent-fabric/memory/` (anchors without the `agent-fabric:` prefix) and remove them from the project memory. Then assemble from the other bundles only, with `tools/fabric/assemble.py` run from a detached agent-fabric worktree at the fabric-ref. Related: [[j650-drain-2026-11-08]], [[drain-procedures]].

*References: drain-procedures, j650-drain-2026-11-08*

*Anchors: `tools/fabric/assemble.py::--working-copy`*

*Observed 2026-11-09 (fabric-coordinator)*
