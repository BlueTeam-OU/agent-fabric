---
role: "language-culture"
class: workflow
topic: "render-print-needs-fabric-root"
description: "launch_prompt.py --print and lint (python3 -m fabric.lint) in a branch worktree read the main clone unless AGENT_FABRIC_ROOT is set"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3ea0bfe31a370de5
---

## launch_prompt.py --print and lint (python3 -m fabric.lint) in a branch worktree read the main clone unless AGENT_FABRIC_ROOT is set

`tools/fabric/launch_prompt.py --print` run in a job worktree reads `layout.FABRIC_ROOT`,
the main clone, not the branch's tree; set `AGENT_FABRIC_ROOT=$PWD` and grep the output for
the new text, or the size you check is the old prompt's (j53, 2026-10-15).
The same holds for lint: `PYTHONPATH=tools:runtime:lib python3 -m fabric.lint` without the
variable still reports a translates_digest lag the branch has fixed (j80, 2026-10-24).

*Observed 2026-10-31 (language-culture)*
