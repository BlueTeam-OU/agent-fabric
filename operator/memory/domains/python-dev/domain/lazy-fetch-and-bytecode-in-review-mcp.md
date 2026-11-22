---
role: "python-dev"
class: domain
topic: "lazy-fetch-and-bytecode-in-review-mcp"
description: "promisor clones fetch on a missing object despite protocol.allow=never; -I does not imply -B; how to prove both"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 82979c9a95c94139
---

## promisor clones fetch on a missing object despite protocol.allow=never; -I does not imply -B; how to prove both

In a partial (--filter=blob:none) clone a missing commit/blob starts a `git fetch` child; `-c protocol.allow=never` only makes that child fail. Stop it with `--no-lazy-fetch` (argv) and `GIT_NO_LAZY_FETCH=1` (env), git 2.44+. Prove it with GIT_TRACE: count `run_command` lines containing ` fetch` (0 with the switch, 1 without = positive control), plus .git/config bytes+mtime. Test each switch alone by patching the argv/env builder.
`python -I` does not imply `-B`: add `-B` to the launcher and `sys.dont_write_bytecode = True` before imports; test on a copied tree with the module line removed so the launcher's -B is what is proved.
Seen in #358 round 2 (j153, for/user/j333-review-server c9150a2a). Any git child (review_coverage.diff_paths) has the same class.

*Observed 2026-10-24 (python-dev)*
