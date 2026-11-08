---
role: "fabric-coordinator"
class: workflow
topic: "local-corpus-lint-red-interweave-index"
description: "tests/run.sh red locally with \"1 suite(s) FAILED\" while CI is green — corpus lint on a local InterWeave clone's INDEX.md drift"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8f37f81522ddbb45
---

## tests/run.sh red locally with "1 suite(s) FAILED" while CI is green — corpus lint on a local InterWeave clone's INDEX.md drift

2026-11-07 (j626, BlueTeam-OU/agent-fabric#506 head a38d9e45): the local full run ended `1 suite(s) FAILED`;
the only red was `== corpus lint` (tools/fabric/lint.py) listing `interweave:.agent-fabric/memory/<role>/INDEX.md ... the index has drifted`
(ux-designer, rust-ui-dev). CI, which has no InterWeave clone, was green on the same head.
Find the red suite by the `== <name>` header blocks at the end of the log, not by grepping FAIL (nested
runner tests print FAILED lines that pass). The fix is an InterWeave-half drain (`tools/fabric/assemble.py`), not the branch.

*Anchors: `tests/run.py::corpus lint`*

*Observed 2026-11-07 (fabric-coordinator)*
