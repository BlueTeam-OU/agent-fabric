---
role: "python-dev"
class: domain
topic: "mutation-pyc-stale-same-second"
description: "Mutation runs that edit a source and rerun within the same second can run a stale .pyc - clear __pycache__ and set PYTHONDONTWRITEBYTECODE"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4384bee967921def
---

## Mutation runs that edit a source and rerun within the same second can run a stale .pyc - clear __pycache__ and set PYTHONDONTWRITEBYTECODE

Planting a mutation with sed/python then running the test within the same second can execute the cached .pyc (same size and mtime second), so a mutant or its restore reads wrong; one j30 run showed a "restored" tree failing. Run mutation loops with `PYTHONDONTWRITEBYTECODE=1` after deleting `__pycache__`, and re-run the clean suite last. Also: `git checkout <file>` to undo a mutation destroys uncommitted real edits in that file - copy to a backup instead.
**Why:** both happened in j30.
**How to apply:** every mutation pass.

*Observed 2026-10-15 (python-dev)*
