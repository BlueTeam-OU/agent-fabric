---
role: "python-dev"
class: threads
topic: "j147-read-tree-lister-delivered"
description: "j147 (#354 round 1) delivered; lint listers read the operator tree; test_roots_seam bans joining projects/integration paths by hand"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 45be68c0cb9fa22d
---

## j147 (#354 round 1) delivered; lint listers read the operator tree; test_roots_seam bans joining projects/integration paths by hand

j147 delivered 2026-10-22: for/ branch develop-qzapp/python-dev-01/for/user/j147-lint-read-tree-arm @52058c82 (test only, test_lint.py); the lint.py change went as a diff in REPLY 01a16254 (lint is the coordinator's file).
`_read_tree_files` in lint.py: git checkout = `rev-parse --show-toplevel` equals the tree; empty index = None; else existence.

**Why:** test_roots_seam flags any lint code that joins "projects", p, "integration" itself (a glob did); list with os.listdir(roots.projects_dir) + roots.project_integration.
**How to apply:** a follow-up finding on the hunk comes back to me; the fold is the coordinator's single blind review (INFO 01a16243: a supplier dispatches no review of its own). A CPU-budget test in test_review_bash_guard_cli reds under load and passes alone.

*Observed 2026-10-22 (python-dev)*
