---
role: "fabric-coordinator"
class: solution
topic: "stale-project-settings-double-guard"
description: "Why reviews dispatched from six project repos were refused 'model unset' (2026-11-01, fixed by j549, agent-fabric #458): a project's old .claude/settings.json ran the dispatch guard a second time after the managed entry stripped model"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ddfb1915509f3a66
---

## Why reviews dispatched from six project repos were refused 'model unset' (2026-11-01, fixed by j549, agent-fabric #458): a project's old .claude/settings.json ran the dispatch guard a second time after the managed entry stripped model

2026-11-01, blueteam.ee #16 (j498): two `code-review` dispatches with `model: fable` and no
`run_in_background` were both denied as `model "unset"`. The cause was blueteam.ee's committed
`.claude/settings.json`, rendered in 23c208a from the workspace template at agent-fabric dce67dba.
Its Agent hook runs `agent-fabric/runtime/claude-code/hooks/agent-dispatch-guard.sh` with no
stand-down clause. Once the managed guard is installed (ADR-043), the managed entry allows the
dispatch and strips `model`, and the project copy then refused the stripped input. The same render
is in InterWeave, agent-fabric-guards, gzapi.brand, gzapi.ge and gzapp.

Fixed by j549, agent-fabric #458 (merged 2026-11-02, 1b90ade8): each
runtime/claude-code/hooks/*.sh forwarder now stands down by itself when
/etc/claude-code/managed-settings.json names its guard, so the stale project copies no longer refuse.
Reviews from those working copies work again after a relaunch; blueteam.ee #17 (j657, 2026-11-09)
was reviewed from one.

**Why:** a project's committed settings are a render of the template at one fabric commit, and they do
not move when the template does; a guard that a project copy runs must tolerate running twice.
**How to apply:** when a dispatch is refused in one project only, compare its `.claude/settings.json`
with the template on origin/main before suspecting the dispatch itself.
Related: [[review-dispatch-no-run-in-background]].

*References: review-dispatch-no-run-in-background*

*Anchors: `agent-fabric:runtime/claude-code/hooks/agent-dispatch-guard.sh::cannot_run`, `agent-fabric:runtime/claude-code/workspace/settings.json::agent-dispatch-guard`*

*Observed 2026-11-09 (fabric-coordinator)*
