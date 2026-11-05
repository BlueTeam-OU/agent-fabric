---
role: "fabric-coordinator"
class: workflow
topic: "arm-with-tree-gate-when-pr-adds-it"
description: "arming a PR that changes arm.py's gates — the bare fabric-pr runs main's arm and skips the new gate"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2a7d4683050fbc5c
---

## arming a PR that changes arm.py's gates — the bare fabric-pr runs main's arm and skips the new gate

`fabric-pr` on PATH resolves to the main checkout's bin/fabric-pr, so a PR that adds an arm gate is armed by the OLD gate. On #437 (2026-10-31) the bare dry run would have armed silently with F2 open; `AGENT_FABRIC_ROOT=$PWD bin/fabric-pr arm …` from the PR's worktree refused on F2 and on 5 blocked jobs, and the arm then recorded each --defer / --defer-job.

**Why:** the arming comment is the record; a deferral that the old gate never asked for leaves no trace.
**How to apply:** when the PR touches tools/fabric/github/arm*.py, dry-run and arm with the worktree's bin/fabric-pr. Related: [[arm-reads-every-rounds-open-findings]].

*References: arm-reads-every-rounds-open-findings*

*Observed 2026-10-31 (fabric-coordinator)*
