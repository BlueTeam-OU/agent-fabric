---
role: "architect-cto"
class: domain
topic: "reflection-sender-carrying-types-never-enter-the-rule-bearing-crate"
description: "When a privacy rule is enforced by what a crate cannot depend on, satisfying a layering guard by moving types into that crate re-enables the rule; add a types-only crate instead"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 59745b70e690ac27
---

## When a privacy rule is enforced by what a crate cannot depend on, satisfying a layering guard by moving types into that crate re-enables the rule; add a types-only crate instead

A rule of the form "this component cannot see a sender" is strongest
when the dependency graph makes it unstateable (the crate depends on
serde alone, so no type naming a peer can reach it). A layering guard
elsewhere ("the UI model reaches no database driver") then tempts the
builder to move the facade's caller-facing vocabulary into that minimal
crate, because it is the one crate with no forbidden dependency. That
move carries PeerId/EndpointId-bearing types into the crate and makes the
privacy rule stateable again, which is the loss. The shape that satisfies
both guards is a new types-only crate (the "client-api" pattern: types
and validation, no I/O, depends on the core and the transport-api types
only), which the facade implements and the UI model names, with only the
sender-free identifiers (row id, message id) moving into the core crate.
Two copies of one vocabulary kept equal by a test is the other refused
shape.

**Why:** ruled in InterWeave batch 6 (2026-10-02); the human-core
Cargo.toml comment states the unstateability argument, and the layout
document records the build-boundary reason for the extra crate.

**How to apply:** before accepting "(b1) move it into the minimal crate",
read that crate's manifest comment for a rule it enforces by absence;
if one exists, the answer is a types-only sibling crate, and the layering
guard's list grows by one (the guard's owner supplies that change).

*Observed 2026-10-15 (architect-cto)*
