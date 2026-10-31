---
role: "python-dev"
class: solution
topic: "lint-warning-count-depends-on-neighbours"
description: "corpus lint's warning count depends on checkouts beside the tree (origin working copies); a test comparing two trees must put both among the same neighbours (#262, j157)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 326a92ef51d8e498
---

## corpus lint's warning count depends on checkouts beside the tree (origin working copies); a test comparing two trees must put both among the same neighbours (#262, j157)

memory_check judges a path a slice cites from another origin project (`../<working_copy>`, or a `../NAME/...` citation) stale-hard only when that checkout is beside the tree; absent beside it the path is `unchecked` and silent. So lint on a checkout in ~/projects with siblings warns more (24 vs 18, 2026-10-14) than the same tree cloned into a lone temp dir. The operator-copy case was red only on logins with siblings, green here and in CI.

**Why / how to apply:** a test that compares lint over two trees must clone into a directory holding symlinks to the checkout's neighbours (among_neighbours in the case), and its probe tree in its own directory. Reproduce such a login with empty sibling directories (InterWeave, gzapp) beside the checkout, then remove them. A failure message that shows only a 600-char tail hides this: print the diff (#260).

*Anchors: `tools/fabric/memory_check.py::status`, `tests/test_roots_readers.py::case_lint_with_an_operator_copy_says_what_it_says_without_one`*

*Observed 2026-10-14 (python-dev)*
