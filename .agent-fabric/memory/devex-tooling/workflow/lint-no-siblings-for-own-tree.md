---
role: "devex-tooling"
class: workflow
topic: "lint-no-siblings-for-own-tree"
description: "tools/fabric/lint.py reports sibling projects' memory-index drift; --no-siblings is the clean check of agent-fabric's own tree"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 003f8a1ca2f31ef3
  - 9f884302bed4be92
  - d9a796536612e0cc
---

## tools/fabric/lint.py reports sibling projects' memory-index drift; --no-siblings is the clean check of agent-fabric's own tree

`python3 tools/fabric/lint.py` in an agent-fabric worktree also lints the sibling working copies' `.agent-fabric/memory/*/INDEX.md` (gzapp, interweave) and exits 1 on their drift: 10 findings on 2026-10-13, identical at the base commit. `python3 tools/fabric/lint.py --no-siblings` lints this tree alone and was clean for j119 (a78d7641).

**Why:** the remit asks for a clean lint before every commit; the sibling findings are other roles' and not caused by the change.

**How to apply:** before committing in agent-fabric, run `lint.py --no-siblings`; when the plain run fails, compare its findings with the base before calling them pre-existing.

**In tests/run.sh too (j263):** run.py's "corpus lint" step runs the plain lint, so sibling INDEX drift alone (agent-fabric-gateway, gzapp, herdr, interweave) turns a local CI-env run red; CI has no sibling checkouts. How it shows depends on the tree:
- before agent-fabric#624 (observed 2026-10-31): the run ends `tests/run.sh: 1 suite(s) FAILED` with `FAILED_SUITES=0` above it;
- from #624 on (fabric-coordinator's report of 2026-11-16, tests/test_run.py case "a failing lint in the pool: exit 1, FAILED_SUITES=1"; #624 was still open when this was written): the lint is a pool entry of the python section, prints under `== corpus lint` and counts in FAILED_SUITES, so a lint-only red reads `FAILED_SUITES=1`.
Either way, read the `== corpus lint` block before taking a non-zero count for a failed suite. Once `--no-siblings` is clean, report the lint as sibling-only.

*Anchors: `tools/fabric/lint.py::--no-siblings`, `tests/run.py::corpus lint`*

*Observed 2026-11-16 (devex-tooling)*
