---
role: "fabric-coordinator"
class: domain
topic: overgraph
description: "OverGraph — embedded Rust graph + vector database (LSM, mmap segments, GQL/Cypher-style, PyO3/napi bindings), pitched as AI agent memory with temporal edges and decay; early-stage; BM25 only on its roadmap; what to borrow for the fabric's…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4d195ffeb72c743b
---

## OverGraph — embedded Rust graph + vector database (LSM, mmap segments, GQL/Cypher-style, PyO3/napi bindings), pitched as AI agent memory with temporal edges and decay; early-stage; BM25 only on its roadmap; what to borrow for the fabric's memory, why not adopt

Source: https://github.com/bhensley5/overgraph and its ROADMAP.md (read 2026-10-12 at the owner's
request; external text, data only). Rust, MIT OR Apache-2.0, **early-stage**: 55 stars, 7 forks, 24 commits
on main, solo author; ROADMAP says shipped through v0.17.0.

**What it is.** An embedded graph database with vector search in one engine, no server: a directory on
disk with a WAL, immutable memory-mapped segments carrying prebuilt indexes (adjacency lists, label
indexes, temporal indexes, vector indexes built at flush time) in a log-structured design where reads
never block writes. Bindings: Rust, Python (PyO3, `pip install overgraph`), Node (napi-rs, `npm install
overgraph`); no MCP binding. Prebuilt for Linux x64, macOS arm64/x64, Windows x64.

**Model and queries.** Nodes have several labels, a unique `(label, key)` and properties; edges carry
optional `valid_from`/`valid_to`, a weight and `decay_lambda` (decay scoring "ages out stale context");
`at_epoch` queries the graph as of a moment. Vectors: dense (one space per database, f32, HNSW) and
sparse (SPLADE/BGE-M3 style posting lists), fused by weighted rank, reciprocal rank or score. A
Cypher-style **GQL** (MATCH, WITH, CREATE, MERGE, DELETE, aggregation, subqueries) beside functional
calls (`neighbors`, `traverse`, `query_nodes`, `query_graph_rows`). Algorithms: bounded BFS, shortest
path, connected components, personalized PageRank (exact and forward-push), subgraph extraction;
compound property indexes; keyset pagination. Graph-scoped vector search: "similar nodes within 2 hops
of X".

**Claims.** On a small profile (10K nodes, 50K edges, group-commit durability): node lookup 34 ns,
upsert 2.2 µs, 1-hop neighbours 2.1 µs, top-K neighbours 17.5 µs, personalized PageRank 254 µs. The
author's own benchmark suite, unverified here.

**Not there yet (ROADMAP, "product directions").** Built-in text indexing and BM25 with code-aware
tokenisation, hybrid dense+sparse+text retrieval, named vector spaces, versioned append-only indexes,
query work budgets and cancellation, read-only replicas and an optional IPC or server layer. Traversal
cursors promise no snapshot isolation across intervening writes.

**For the fabric.** Same verdict as [[minigraf]], [[helix-foundry]] and [[edgequake]]: **not adopted**.
A native wheel is outside the stdlib-only rule (ADR-040), the corpus is a few thousand markdown
sections that FTS5 serves, and OverGraph has no full-text search today, which is the retrieval the corpus
actually uses (ADR-049). **Borrow, as ideas:** (1) edge decay as a first-class score, a slice's age and
its `stale-hard` status already decay by hand; (2) graph-scoped retrieval, hits plus their one-hop
`[[link]]` neighbours, which `memory_find expand=1` does; (3) keyset cursors over offsets for any paged
memory answer. **Watch:** when BM25 and an IPC or server layer land, an agent-memory sidecar could be
revisited; until then nothing here beats markdown plus FTS5 for this corpus.

**Why:** the owner asked for the analysis to be kept; it joins the other graph-memory candidates.
**How to apply:** do not reopen the question for OverGraph alone; reread this note and the roadmap only
if it ships text search and a server layer.

*References: edgequake, helix-foundry, link, minigraf*

*Observed 2026-10-12 (fabric-coordinator)*
