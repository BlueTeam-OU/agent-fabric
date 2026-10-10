---
role: "fabric-coordinator"
class: workflow
topic: "suite-in-a-worktree-lints-wrong"
description: "Corpus lint from a worktree of the fabric reads the running checkout; a ../agent-fabric/ INDEX finding is now a real finding"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 403860fe5ac860b2
  - e12de21ec9930091
---

## Corpus lint from a worktree of the fabric reads the running checkout; a ../agent-fabric/ INDEX finding is now a real finding

The fabric's own memory is read from the running checkout (`working_copy_for`; tests/test_layout.py), so `tests/run.sh` and corpus lint run from a worktree of agent-fabric no longer report false INDEX drift. A worktree is fine for folding, committing and the suite that gates a push.

`AGENT_FABRIC_ROOT` still overrides the fabric root (`FABRIC_ROOT`, tools/fabric/layout.py), so unset it for a lint of the tree you stand in (`env -u AGENT_FABRIC_ROOT`). A lint finding naming `../agent-fabric/` for the fabric's own `.agent-fabric/` now deserves a real look, not a shrug. Related: [[run-suites-as-ci-before-push]], [[lint-before-commit]].

*References: lint-before-commit, run-suites-as-ci-before-push*

*Observed 2026-10-10 (fabric-coordinator)*
