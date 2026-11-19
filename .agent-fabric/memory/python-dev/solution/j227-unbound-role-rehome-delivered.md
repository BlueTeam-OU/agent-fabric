---
role: "python-dev"
class: solution
topic: "j227-unbound-role-rehome-delivered"
description: "assembler re-homes a fabric-coordinator claim of an unbinding project to agent-fabric, refuses other roles (j227, for/ branch 009a7a6c)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1670af0c9fb2b006
---

## assembler re-homes a fabric-coordinator claim of an unbinding project to agent-fabric, refuses other roles (j227, for/ branch 009a7a6c)

Delivered as develop-qzapp/python-dev-01/for/user/j227-drain-unbound-role (009a7a6c): rehome_unbound in assembler/intake.py judges per claim by owners; coordinator-only claims go through a second assemble_project pass as agent-fabric (load_hygiene swaps the own-name view and restores it), anything else sys.exit before writes. The old hold (held_unbound_role) is gone.
**Why:** the 2026-11-08 drain filed coordinator claims into a project binding other roles.
**How to apply:** the second pass runs first so its refusal leaves the project untouched; --hold/--collision-decisions only address the project pass. A mutation that survived (return rc of the second pass) needed a collision test: check every pass's rc is asserted.

*Observed 2026-11-11 (python-dev)*
