---
role: "python-dev"
class: workflow
topic: "wave8-no-node-fixes"
description: "during Wave 8 (control plane to Python), a behaviour change for runtime/control/*.mjs goes into the Python port, not the Node, even a fix"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9a337fd25d9c68f9
---

## during Wave 8 (control plane to Python), a behaviour change for runtime/control/*.mjs goes into the Python port, not the Node, even a fix

On 2026-10-09 the owner overrode fabric-coordinator's reading of ADR-040
Wave 8 rule 8 ("the remaining Node takes fixes where it is"). A
finished, mutation-checked Node fix (j5: sessions.mjs said an unreadable
session-state.json as `sessions: "unreadable"`) was not pushed. Its
contract and mutation cases went to the holder of that module's Python
port (python-dev-01 for sessions/ctl). Coordinator INFO 01a11e4e. #127
merged without it (5267e2ab).

**Why:** the owner wants the port to carry new behaviour, so that there
is one place to change and the parity harness is not chasing a moving
Node.

**How to apply:** before changing any runtime/control/*.mjs while Wave 8
is open, ask whether the change belongs in the Python package
tools/fabric/control/ instead. Give the module's port owner the contract
and the mutation list, not a Node commit. The Wave 8 split: -01 the wire
and security core, sessions; -02 the ops; -03 the processes and the
cutover. See [[forge-port-queue]].

*References: forge-port-queue*

*Observed 2026-10-09 (python-dev)*
