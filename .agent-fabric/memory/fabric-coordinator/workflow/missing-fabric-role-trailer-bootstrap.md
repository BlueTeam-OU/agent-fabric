---
role: "fabric-coordinator"
class: workflow
topic: "missing-fabric-role-trailer-bootstrap"
description: "A commit made in a clone without fabric hooks lacks Fabric-Role; hand-adding the trailer is refused, bootstrap then re-commit is the way"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f16efa7e145e907f
---

## A commit made in a clone without fabric hooks lacks Fabric-Role; hand-adding the trailer is refused, bootstrap then re-commit is the way

A clone registered after the last bootstrap has no core.hooksPath, so its commits lack the `Fabric-Role:` trailer, and the .agent-fabric/ authority check fails on them. Adding the trailer by hand (`git commit --amend --trailer "Fabric-Role: …"`) is refused by the auto-mode classifier as "Security Weaken". This happened on 2026-10-28, on [redacted]-shop-transit PR #2.

**Why:** the trailer is meant to come from the hook. A trailer typed in by a session proves nothing about the binding.

**How to apply:**
- Before committing in a new managed clone, check `git config core.hooksPath`.
- If it is unset, run `runtime/claude-code/bootstrap.sh` (dry-run first) and only then commit.
- If a commit already went out without the trailer: once the owner agrees, soft-reset it and re-commit, so the hook adds the trailer.

*Anchors: `agent-fabric:tools/fabric/bootstrap.py::core.hooksPath`*

*Observed 2026-10-28 (fabric-coordinator)*
