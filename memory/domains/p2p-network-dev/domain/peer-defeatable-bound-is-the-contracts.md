---
role: "p2p-network-dev"
class: domain
topic: "peer-defeatable-bound-is-the-contracts"
description: "A limit on peer-supplied input whose absence lets a peer's bytes abort the process is the wire contract's bound, never an implementation constant — raise it to the contract owner instead of choosing a local number"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b96c5eeb5a78c105
---

## A limit on peer-supplied input whose absence lets a peer's bytes abort the process is the wire contract's bound, never an implementation constant — raise it to the contract owner instead of choosing a local number

A bound that a peer's bytes can defeat into a crash or an unbounded
allocation is part of what two implementations must agree on: if one
side's limit is "the renderer's own", another implementation is free to
omit it and the peer-controlled input reaches the abort again. So a
missing bound found in code is a contract gap, not a local fix.

Case (InterWeave #166, 2026-10-01): inline markdown nesting was
unbounded; a `**` run or nested `![` up to the 196,608-byte message
ceiling built a ~49,000-level tree whose drop overflowed a 2 MiB stack in
release builds too (measured). I added a renderer-local
`MAX_INLINE_NESTING = 32` and asked. The contract owner ruled the bound
the contract's (16, the same number as block nesting, counted
separately), because the governing record already said "nesting depth
… bounded" without restricting it to blocks — the contract text had
under-specified it.

**How to apply:** when a review or a measurement finds unbounded
recursion, depth, count or size on input a peer controls, ship the
local guard if you must, but send the contract owner the measured
failure and ask for the value to be named in the wire contract; move
the constant beside the contract's other asserted bounds, and never
write "this is the implementation's limit, not the contract's" in docs.
Related: [[an-allowance-must-not-be-earned-by-what-occupies-it]].

*References: an-allowance-must-not-be-earned-by-what-occupies-it*

*Observed 2026-10-15 (p2p-network-dev)*
