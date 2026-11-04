---
role: "domain-transit"
class: workflow
topic: "job-intake-homes-project-requests-in-agent-fabric"
description: "a REQUEST sent with PROJECT agent-fabric becomes a job homed in agent-fabric even when the work is in another repo; the commit guard then blocks it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "domain-transit"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 09e8f7cea20f1e1b
---

## a REQUEST sent with PROJECT agent-fabric becomes a job homed in agent-fabric even when the work is in another repo; the commit guard then blocks it

REQUEST 01a16cdc-019f-754d-91fe-e93901e19280 asked for work in [redacted]-shop-transit, but its header said PROJECT agent-fabric. Intake queued it as job j15 with working copy ~/projects/agent-fabric and a worktree agent-fabric-j15-…, which is the wrong repository.

The PreToolUse guard then refused `git commit` in ~/projects/[redacted]-shop-transit (ADR-037 rule 3), and fabric-jobs has no command to move a job to another working copy.

What worked: `fabric-jobs add "<artifact>" --working-copy <the right copy> --topic …`, then drop the wrong job pointing at the new one, then `fabric-jobs switch`.

**How to apply:** at the start of a requested job, check that `fabric-jobs show` names the repository the work is in, before editing anything.

*Anchors: `bin/fabric-jobs::--working-copy`*

*Observed 2026-10-24 (domain-transit)*
