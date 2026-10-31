---
role: "fabric-coordinator"
class: workflow
topic: "hook-fixtures-copy-module-list"
description: A new import in any script a test copies into a scratch fabric (commit_hooks.py and its test_contributors/test_githooks_cli fixtures first) breaks that fixture, which copies a fixed module list; only the full run shows it
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e14b806ada2239c4
---

## A new import in any script a test copies into a scratch fabric (commit_hooks.py and its test_contributors/test_githooks_cli fixtures first) breaks that fixture, which copies a fixed module list; only the full run shows it

2026-10-20, j305: commit_hooks.py gained `import agent_text` and `import hidden_unicode`. The agent ran the hook's own
test files (green) but tests/test_contributors.py and tests/test_githooks_cli.py copy roots.py, commit_kind.py,
commit_hooks.py by name into a scratch fabric, so every hook run there died on ModuleNotFoundError; only the full
tests/run.sh showed it (fixed in 8ded7a86).

The same holds beyond commit_hooks: any fixture that copies scripts into a scratch fabric must copy every module they import (seen again in the W43 reflection).

**How to apply:** a brief that adds an import to any copied module names the fixtures that copy it (grep tests/ for the module's
filename being copied) and runs them. Related: [[new-test-own-tree-and-scratch]], [[fold-then-full-suite]].

*References: fold-then-full-suite, new-test-own-tree-and-scratch*

*Anchors: `tests/test_contributors.py::what commit_hooks.py imports from tools/fabric/`*

*Observed 2026-10-22 (fabric-coordinator)*
