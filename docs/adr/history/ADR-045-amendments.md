# ADR-045 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-08 — The engine root honours AGENT_FABRIC_ROOT until stage 4

Rule 1 said `engine_root()` is the code's own location. The seam's first
implementation (python-dev-03, #119) kept honouring `AGENT_FABRIC_ROOT`
when it is set: every wrapper and test fixture sets it, and in production
it names the code's own location anyway, so dropping it would have
rewritten every fixture for no change in behaviour. It is accepted as a
transition until stage 4, when the operator's data moves out and the
variable stops meaning both trees. Meanwhile a fixture that stands in
for instance data sets `AGENT_FABRIC_OPERATOR`, so the double meaning the
record ends is not extended.

### Amendment 2026-11-11 — The operator repository is named, and the move has a plan

The owner created the operator repository on 2026-11-10 as
`BlueTeam-OU/blueteam-fabric`, private and empty. `docs/split/inventory.md`
had named it `gzapi-org/blueteam-fabric` and is corrected. It is not one of
the settings repositories (`BlueTeam-OU/agent-fabric-settings`, and the
one gzapi-org has): each of those holds one organisation's arming policy
for `fabric-pr arm`, stays its own repository and takes nothing from this
move.

The extraction's order is written in `docs/split/move-plan.md`. The list
comes from `tools/fabric/roots.py`. The files move inside this repository
first, behind one changed default and with shims for the readers outside
the seam, and only then cross into the operator repository. The owner chose on 2026-11-11 to classify
`docs/adr/` record by record. An organisational record moves with its
number, and the engine keeps that number reserved. Rule 4 forbids
renumbering, not moving. A mixed record may also be split: the
engine's part keeps the number, and the organisation's part becomes an
operator record that cites it. Engine CI reads the operator's main for the
signing check through a read-only deploy key (the owner, the same day).

The Scope line, rule 1 and §8 named a `runtime/control/roots.mjs`. It
was deleted with the Node control plane on 2026-10-10 (a20b4159), and
those mentions are struck.

### Amendment 2026-11-11 — Rule 2's list matches the tree

Rule 2's list did not match the tree it describes. The review of #557
found the gap, and `tools/fabric/roots.py` is the source of the
corrected list. `identities/personas/` and the clients registry are
instance data, and `roots` already resolved both under the operator's
tree. `routing/policies/` (account switching, availability, the review
grade) is instance data too: it records how this fleet chooses, and
`roots.routing_policy` resolves it there. The inventory had classed it
with the routing defaults. Nine of the fifteen `policies/*.json` files
are the guards' exception lists: each one names engine modules that a
checker admits, and it changes with that code. Rule 2 therefore keeps
them with the guards in the engine, and `docs/split/move-plan.md` step A
moves them out of `policies/`.
