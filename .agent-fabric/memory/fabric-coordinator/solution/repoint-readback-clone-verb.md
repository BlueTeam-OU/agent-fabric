---
role: "fabric-coordinator"
class: solution
topic: "repoint-readback-clone-verb"
description: "after a repository move, reading back each account's clone origin — status shows none; clone verb does, with caveats"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c84a71ba56d13e58
---

## after a repository move, reading back each account's clone origin — status shows none; clone verb does, with caveats

`fabric-ctl all status` prints no working copy's remote. The per-clone origin read-back is
`fabric-ctl <login>... clone <id>` (never `all`): on a present clone it reports `origin` keep|set|unreadable
(tools/fabric/control/clone.py, project_clone.plan_origin). Caveats: it compares against the registry's SSH
remote only (bootstrap's `repoint` keeps the clone's scheme), so `set` on an https clone switches it to SSH; and
it reads only `~/projects/<id>`. Which accounts hold a clone: `fabric-ctl all branches` (working-copy names).
Landed as repo-lifecycle step 11, commit 94b108f5 on #437 (j453).

*Anchors: `tools/fabric/control/clone.py::plan_origin`, `tools/fabric/project_clone.py::registry_remote`, `policies/repo-lifecycle/SKILL.md::fabric-ctl all branches`*

*Observed 2026-10-31 (fabric-coordinator)*
