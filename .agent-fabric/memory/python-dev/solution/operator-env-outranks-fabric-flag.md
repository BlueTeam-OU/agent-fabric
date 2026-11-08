---
role: "python-dev"
class: solution
topic: "operator-env-outranks-fabric-flag"
description: "AGENT_FABRIC_OPERATOR outranks --fabric/engine= in roots.py, so a tool run with --fabric still writes memory/ into the operator tree"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 076252d79ed5b360
---

## AGENT_FABRIC_OPERATOR outranks --fabric/engine= in roots.py, so a tool run with --fabric still writes memory/ into the operator tree

`roots.operator_root(engine=...)` returns an exported AGENT_FABRIC_OPERATOR before the engine tree a caller was handed, so `assemble.py --fabric X` wrote domain/shared slices to the operator tree (j88, PR 460). AGENT_FABRIC_ROOT, AGENT_FABRIC_WORKING_COPY and cwd did not redirect when `--fabric`/`--working-copy` were given. Fix: `assembler/intake.py open_layout` sets the operator to `--fabric`.

**Why:** an "is the write confined" test must aim every root variable, HOME and cwd at a decoy and snapshot it; probing one variable at a time found the cause.
**How to apply:** any tool with a `--fabric`/`--root` flag that writes through `roots.*(engine=)` has the same seam; check it before trusting the flag. Reading another account's checkout is denied by the classifier, so cross-account checks go to someone with access.

*Anchors: `tools/fabric/assembler/intake.py::ENV_OPERATOR`, `tools/fabric/roots.py::operator_root`*

*Observed 2026-11-02 (python-dev)*
