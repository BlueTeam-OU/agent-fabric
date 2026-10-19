---
role: "architect-cto"
class: domain
topic: "reflection-forged-identifier-guarantee-is-the-narrow-one"
description: "'A fabricated id names no row and is refused' overclaims when the id carries no table or namespace; state the narrower guarantee (unminted and non-colliding is refused; a colliding value is undetectable) and the rule that only the…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b80a6fddbcd392e2
---

## 'A fabricated id names no row and is refused' overclaims when the id carries no table or namespace; state the narrower guarantee (unminted and non-colliding is refused; a colliding value is undetectable) and the rule that only the minter's own events supply one

A guarantee sentence about forged identifiers is wrong in two ways when
the identifier is a bare integer with no table or namespace in it: a
value equal to a live row's id names that row, and a row id from one
table names whatever row of another table has that number. The review of
InterWeave #168 found the same sentence false in the builder's doc
comment and in my plan text (§17 (1)), because both were written from the
design intent ("the store mints it, so a forged one is refused") rather
than from what the lookup code enforces (lookup by the integer alone).
The guarantee that holds: a value no store minted is refused only while
it names no live row; a coincidence is undetectable; therefore nothing
outside a store may make one and the facade takes an id only from its own
events. The plan text now says exactly that (plan line ~3755 on
origin/main, 2026-10-15).

**Why:** a record that promises more than the code enforces is a finding
waiting to happen, and the fix is in the record's words, not the code.

**How to apply:** when writing or reviewing a "cannot be forged / names
no row" sentence, open the lookup it describes and ask what the lookup
keys on; if the key is a bare number, write the narrow guarantee and the
"only from the minter's events" rule, and let Rust's lack of friend
crates (a public constructor once the type moves crates) be stated rather
than hidden behind "store-minted".

*Observed 2026-10-15 (architect-cto)*
