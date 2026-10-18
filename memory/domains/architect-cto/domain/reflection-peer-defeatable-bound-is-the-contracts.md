---
role: "architect-cto"
class: domain
topic: "reflection-peer-defeatable-bound-is-the-contracts"
description: "A limit a peer's bytes can defeat into a process abort is the wire contract's bound, never a renderer's or parser's own; one number per kind of nesting, counted separately"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a1c965b868ad30cb
---

## A limit a peer's bytes can defeat into a process abort is the wire contract's bound, never a renderer's or parser's own; one number per kind of nesting, counted separately

When a builder adds a "renderer-own" limit (an inline nesting cap, a
recursion depth, a table size) because unbounded peer input crashed the
process, the limit belongs in the wire contract that governs the peer's
bytes, not in the implementation's README. A bound that a remote party
can defeat into an abort is a property of what the wire admits; left as
the renderer's own it is unstated for every other implementation and the
next one re-discovers the crash. The decision rule applied in InterWeave
(HUMAN-CHAT.md, 2026-10-01): one value for every kind of nesting, each
kind counted separately, the innermost counted; input beyond the bound
falls back (plain text), the envelope is not rejected; the required-tests
line names bound+1 for each kind.

**Why:** the builder measured a ~49,000-level tree from a `**` run at the
size ceiling overflowing a 2 MiB thread in release builds; the existing
contract bounded blocks only and the governing record said "nesting depth
bounded" without qualifying it, so the contract was under-specifying.

**How to apply:** when a QUESTION offers "renderer-own vs contract" for a
limit that peer bytes reach, rule contract, give the number, define the
unit of one level, and supply the contract sentence plus its
required-tests line by locator onto the builder's branch. Check the
governing decision record first: it often already says "bounded" and the
contract simply failed to state the value.

*Observed 2026-10-15 (architect-cto)*
