---
role: "fabric-coordinator"
class: workflow
topic: "suite-in-a-worktree-lints-wrong"
description: "tests/run.sh run from a worktree outside ~/projects fails corpus lint with false INDEX drift (../agent-fabric/ links); run the suite in the real checkout"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e12de21ec9930091
---

## tests/run.sh run from a worktree outside ~/projects fails corpus lint with false INDEX drift (../agent-fabric/ links); run the suite in the real checkout

2026-10-02, Wave 6: the full suite run from a scratchpad worktree of agent-fabric failed only corpus lint, with "agent-fabric:.agent-fabric/memory/python-dev/INDEX.md does not list ../agent-fabric/identities/roles/python-dev/charter.md". The same tree linted clean from ~/projects/agent-fabric.

**Why:** lint takes the worktree as the fabric root but finds the registered agent-fabric working copy at ~/projects/agent-fabric, a different directory, so it expects the cross-repository `../agent-fabric/` link form for the fabric's own index.

**How to apply:** a worktree is fine for folding and committing; the suite and lint that gate a push run in ~/projects/agent-fabric with the branch checked out. A lint finding that names `../agent-fabric/` for the fabric's own `.agent-fabric/` is this artifact. Related: [[run-suites-as-ci-before-push]], [[lint-before-commit]].

*References: lint-before-commit, run-suites-as-ci-before-push*

*Observed 2026-10-02 (fabric-coordinator)*
