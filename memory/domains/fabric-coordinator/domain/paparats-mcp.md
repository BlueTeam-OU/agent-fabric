---
role: "fabric-coordinator"
class: domain
topic: "paparats-mcp"
description: "paparats-mcp: self-hosted MIT MCP server for semantic code search across many repos (tree-sitter chunks, call graph, change_impact, git history per chunk, agent architectural memory) on Docker+Qdrant+llama.cpp; not adopted now (host load…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5f8951eae6b83636
---

## paparats-mcp: self-hosted MIT MCP server for semantic code search across many repos (tree-sitter chunks, call graph, change_impact, git history per chunk, agent architectural memory) on Docker+Qdrant+llama.cpp; not adopted now (host load, ADR-049 no embeddings for memory); borrow change_impact and per-chunk history; maybe a gzapp/InterWeave spike

The paparats-mcp repository on GitHub (its author's personal account; read 2026-10-28 through moli). MIT, 21 stars, 578 commits, npm `@paparats/cli`, Node 24 and Docker Compose. It is a self-hosted MCP server that gives Claude Code, Cursor, Codex and other clients semantic code search across many repositories. Code is chunked by tree-sitter AST for 11 languages (Rust, TypeScript, Python, Go and others), embedded locally (bge-code-v1 for code and Qwen3-Embedding-0.6B for prose, both through llama.cpp) and stored in Qdrant. Cloud embeddings (Voyage, OpenAI) are opt-in, and by default nothing leaves the machine.

**Tools:**
- `search_code`: by meaning, across a group of repositories.
- `find_usages` and `change_impact`: a call graph by method; callers up to three steps out, uncertain links marked, and the tests that reach them listed apart.
- `module_map`: a dependency map of the modules, with a web page.
- Git history per chunk: who changed it, when, and the tickets in the commit messages.
- Agent-maintained architectural memory: components, decisions, lessons.
- Docs search and a glossary.

The tools sit on three endpoints by audience: coding, support (read-only) and knowledge (docs only, behind a token). Repositories are re-checked every 10 minutes and indexed incrementally; there is no file watcher, and `POST /trigger` forces an update. Calls are not linked across repositories yet. Its own claim: on one question, 25% faster and 23% fewer new input tokens for Claude Code, averaged over three runs. Local models take about 2.3 GB of disk, and the embed container 2–6 GB of RAM.

**For the fabric:** not adopted now.
1. **Host load:** develop-qzapp is already CPU-bound (load around 110 on 10 vCPUs on 2026-10-26) and was nearly out of disk (97%); an always-on indexer, an embedding container and Qdrant add to both.
2. **The stack:** Node, Docker and Qdrant are outside the fabric's stdlib-Python stance for control-plane tools (ADR-040).
3. **Memory:** ADR-049 deliberately keeps fleet memory retrieval to BM25 with no embeddings; paparats' "architectural memory" would be a second memory beside the curated corpus, the same objection as for [[graphicle]].

**Where it could help:** code search for the big project repositories (gzapp, InterWeave, about 17 projects), where agents spend context on grep-and-read loops, and one shared index would serve 30 agents. That is a per-project spike: one host service, a read-only endpoint, and measured tokens and time before and after on real jobs, only after the host-load lease (j412) and only if the measurement shows the loops cost much.

**Borrow without adopting:**
- `change_impact`'s shape (callers to depth 3 plus the reaching tests, uncertain links marked) as a review-brief aid;
- git history per chunk for the review card;
- endpoints split by audience: coding, read-only support, and docs behind a token.

Related: [[helix-foundry]], [[graphicle]], [[edgequake]].

*References: edgequake, graphicle, helix-foundry*

*Observed 2026-10-28 (fabric-coordinator)*
