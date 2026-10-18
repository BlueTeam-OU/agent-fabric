---
role: "rust-ui-dev"
class: domain
topic: "refusal-leaves-tree-untouched"
description: A refused start or lock acquire must judge every existing directory before creating anything, and its test must assert the directory is absent too
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 47f3bfda09a2f62c
---

## A refused start or lock acquire must judge every existing directory before creating anything, and its test must assert the directory is absent too

Code that creates a private directory and then checks the ancestors' permissions refuses
correctly but leaves a new directory behind under the very parent it judged unsafe. Order:
walk the directories that EXIST, outermost first, judge each, stop at the first missing one,
and only then create. The refusal test must assert the whole tree is as it was -- the
directory absent, not only "no store file exists", which is what let the defect pass.

The same class came back a week later: with the state root MISSING under a refused
ancestor, the existence loop broke at the first missing directory, a recursive create built
the whole tree, and only then were ancestors judged. The rule that held: judge the NEAREST
EXISTING ancestor before any mkdir, create the missing components one at a time (0700),
adopt a component that appears meanwhile only if it is our private directory -- and put
that in the one shared create function, so every caller (locks, key writers, store) gets
it. Test both shapes: an existing refused directory, and a missing one under a refused ancestor.

*Observed 2026-10-15 (rust-ui-dev)*
