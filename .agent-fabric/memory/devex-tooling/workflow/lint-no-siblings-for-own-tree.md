---
role: "devex-tooling"
class: workflow
topic: "lint-no-siblings-for-own-tree"
description: "tools/fabric/lint.py reports sibling projects' memory-index drift; --no-siblings is the clean check of agent-fabric's own tree"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9f884302bed4be92
  - d9a796536612e0cc
---

## tools/fabric/lint.py reports sibling projects' memory-index drift; --no-siblings is the clean check of agent-fabric's own tree

`python3 tools/fabric/lint.py` in an agent-fabric worktree also lints the sibling working copies' `.agent-fabric/memory/*/INDEX.md` (gzapp, interweave) and exits 1 on their drift: 10 findings on 2026-10-13, identical at the base commit. `python3 tools/fabric/lint.py --no-siblings` lints this tree alone and was clean for j119 (a78d7641).

**Why:** the remit asks for a clean lint before every commit; the sibling findings are other roles' and not caused by the change.

**How to apply:** before committing in agent-fabric, run `lint.py --no-siblings`; when the plain run fails, compare its findings with the base before calling them pre-existing.

**In tests/run.sh too (2026-10-31, j263):** run.py's "corpus lint" step runs the plain lint, so a local CI-env run ends `tests/run.sh: 1 suite(s) FAILED` with `FAILED_SUITES=0` above it, from sibling INDEX drift alone (agent-fabric-gateway, gzapp, herdr, interweave). Report FAILED_SUITES and name the lint step as sibling-only, after `--no-siblings` is clean; CI has no sibling checkouts.

*Observed 2026-10-31 (devex-tooling)*
