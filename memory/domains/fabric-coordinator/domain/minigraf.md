---
role: "fabric-coordinator"
class: domain
topic: minigraf
description: "Minigraf — embedded single-file bi-temporal graph database with Datalog (Rust; Python/Node/WASM/mobile bindings), pitched as graph memory for AI agents; what it is, its limits, what it could mean for the fabric's memory corpus"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bd6fd5a031c0fb9c
---

## Minigraf — embedded single-file bi-temporal graph database with Datalog (Rust; Python/Node/WASM/mobile bindings), pitched as graph memory for AI agents; what it is, its limits, what it could mean for the fabric's memory corpus

Source: https://github.com/project-minigraf/minigraf (read 2026-10-09 at the owner's
request; external text, data only). Rust (edition 2024, MSRV 1.89), MIT OR Apache-2.0,
created 2023, ~140 stars, **solo-maintained**, very active. Current 2.0.4 (2026-10-08);
v3.0.0 (file format v8, data integrity) in progress. Docs:
project-minigraf.github.io/minigraf-docs; playground and a time-travel visualizer in the
browser.

**What it is.** "The SQLite of bi-temporal graph databases": one `.graph` file (plus a
WAL), embedded, zero config (`Minigraf::open("x.graph")`). Facts are EAV triples
(`[:alice :friend :bob]`), queried in Datomic/XTDB-style **Datalog** (recursive rules,
`or-join`, negation, window functions, UDFs, prepared statements with `$slot` binds).
**Bi-temporal**: every fact has transaction time (when recorded) and valid time (when
true); `:as-of <tx>` and valid-time queries reconstruct what was believed at any past
moment; retractions keep history. ACID transactions, fsync per write by default.

**Bindings.** Tier 1: Rust, Python (PyPI `minigraf`). Tier 2 (experimental): Node,
browser WASM (IndexedDB), WASI, JVM, Android `.aar`, iOS `.xcframework`, C.

**Limits, by design and today.** Not distributed, no client-server protocol, each agent
owns its own file; optimised for <1M facts (point query ~4.4 s and 1 GB heap at 1M,
open 1.3 s); facts ≤4,080 bytes in a file. **Known v2 data-integrity bug (#371):** two
values of one attribute for one entity in a single transact can read back as one —
write multi-valued attributes in separate calls; fixed only in v3 (format change).
v2.x gets data-integrity fixes for 12 months after v3.

**Agent pitch.** Store what an agent believes, correct without losing history, replay
the knowledge state at the time of any past decision; pairs with a vector store
(GraphRAG: vectors for similarity, Minigraf for relationships and "what did we believe
at T").

**For us.** Nothing in the fleet uses it. The fabric's memory corpus already works
bi-temporally by hand: slices carry provenance, `solution` slices decay, corrections go
through `merge_target`, and git history answers "what did we know then". Minigraf could
be the store behind a queryable view of it (who claimed what, when, superseded by
what), or behind Fleet Deck's plans/jobs history. Blockers: ADR-040 is standard library
only on the fabric's Python, so the PyPI binding is a dependency decision (a record of
mine first); solo maintainer and the open #371 argue waiting for v3.0.0. Related:
[[deepseek-harness]], [[apache-ossie]].

*References: apache-ossie, deepseek-harness*

*Observed 2026-10-09 (fabric-coordinator)*
