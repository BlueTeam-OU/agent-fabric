---
role: "python-dev"
class: workflow
topic: "j17-memory-mcp-state"
description: "j17 fabric-memory MCP server (ADR-049): worktree, what is built, what waits (ADR-049 merge, then PR)"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c9a8ee6d325b7a13
---

## j17 fabric-memory MCP server (ADR-049): worktree, what is built, what waits (ADR-049 merge, then PR)

Worktree ~/projects/agent-fabric-mem, branch develop-qzapp/python-dev-02/feat/memory-mcp (3 work commits,
pushed, no PR). Built to ADR-049 at 2c63ba5e: tools/fabric/memory_mcp/{corpus,bm25,tools,calls,server}.py,
bin/fabric-memory-mcp, tests/test_memory_mcp.py (mutations planted, all caught). Slice ids f:/p: + #position.
**Waits:** ADR-049 on main (corpus lint "cites ADR-049, which does not exist" is the only red); then merge main,
open the PR with the live read-back (3 cues, 168-184 tokens/list), blind review (security: path refusal, log).
Registration + hook INDEX line are the coordinator's; I sent the command (fabric-memory-mcp, no args, stdio).
Rule 5 confirmed: serve what is on disk (the assembler already retires replaced sections).

*Observed 2026-10-10 (python-dev)*
