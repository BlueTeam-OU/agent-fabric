---
role: "python-dev"
class: solution
topic: "store-tree-confinement-j111"
description: "j111 #483 — secret-store incoming tree judged (empty tree of the store's format, first-contact paths), write_confined, resume fallback; review-dispatch traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 30878fa3bf548033
---

## j111 #483 — secret-store incoming tree judged (empty tree of the store's format, first-contact paths), write_confined, resume fallback; review-dispatch traps

#483 (merged 2026-11-04): `trust._tree_reason` diffs base..tip, or the store's own empty tree (`git hash-object -t tree /dev/null`: a hard-coded SHA-1 id breaks sha256 stores; `diff-tree --root <tip>` compares a non-root commit with its parent and a merge with nothing). Allowed paths: `.gpg-id`, `.agent-id`, `env/NAME.gpg`, `state/<id>.*`, `recovery/<id>.*`, `settings/**` (any name settings_put commits except `.git*`/dot parts); only mode 100644. First-contact bundle/clone paths verify no signature, so they call `require_tree` (records the refusal). `core.write_confined` = O_NOFOLLOW dir chain + fd-relative create/rename; `check_confined` for two-file writes. The old tests/test_addenda.py symlink case had to change (store refuses the tree before the loader). `fabric-resume` fallback now needs an owned dir (exit 3).

Process traps: a code-review Agent prompt must carry the dispatch block (a placeholder prompt wasted a dispatch); a big re-review brief can be passed as "Read this file" plus the dispatch header; `fabric-review save <pr> <round>` for each posted round before `next`, and `next` takes `--pr` once saved; security-boundary files need a review-class review before arm even with the owner's word; arm needs an open P3 deferred (`--defer "<head8>:F<n>" why`); full suite waits for the host slot and a stuck queue run is stopped with TaskStop, not pkill.
**Why:** cost several retries. **How to apply:** judge the tree from the empty tree of the store's format; save rounds; defer or fix P3 before arm.

*Anchors: `tools/fabric/secretstore/trust.py::_tree_reason`, `tools/fabric/secretstore/core.py::write_confined`*

*Observed 2026-11-04 (python-dev)*
