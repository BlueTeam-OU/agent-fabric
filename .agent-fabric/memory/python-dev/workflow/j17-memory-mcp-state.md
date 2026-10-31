---
role: "python-dev"
class: workflow
topic: "j17-memory-mcp-state"
description: "j17/j18 fabric-memory MCP server + harvest of marks/counts: MERGED as #183 (2026-10-11); what is carried and the lessons"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8760e94b99737a1c
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

## j17/j18 fabric-memory MCP server + harvest of marks/counts: MERGED as #183 (2026-10-11); what is carried and the lessons

#183 merged 2026-10-11 as 491e4319 (8 work, 5 fix, 0 merge), armed by me at the review gate on the user's word ("arm it when green") and the coordinator's message.
Built: tools/fabric/memory_mcp/ + bin/fabric-memory-mcp (stdio JSON-RPC; memory_find/read/index/mark), memory_index.py (library, bands), committed_tree.py
(reads git HEAD, ADR-049 rule 6), memory_use.py + harvest_memory.py + assembler report (marks.jsonl, memory_use, memory_marks). Next on this feature (not mine yet):
coordinator's runtime/mcp/fabric-memory/install.py and the hook's INDEX line; python-dev-03 builds ADR-050 s8 on my shapes (answer its questions first).
Carried named P3s (fix first in the next change to these files): the MIN_TOKENS comment/test bound the slice-id length (~165 chars); the unserved-root test's `or`
precedence; a parent dir of a root that is a link; two ms-wide watermark edges; --project vs binding project mismatch.

**Lessons (workflow):**
- A log that belongs to the login, read by a per-project drain, needs a project on every row (a P1 the first review found).
- Read the CURRENT ADR text before building to it: the first reading of ADR-049 was an earlier draft (rules 3 and 6 had grown).
- Run lint.py AND the CI guards (git archive origin/main tools policies; agent_fabric_dir_authority, charter_authority, adr range-check) before a push.
- Cherry-pick onto a fresh branch from main instead of merging main into an old branch: a merge's own conflict resolutions outside my entry are judged by the guard.
- Don't pkill by pattern across users (-u $(id -u)); a full suite takes ~45 min; the local one is redundant with CI except for host-specific traps.
- The real agent-fabric-gateway is on this host now (~/.local/bin): tests must not lean on PATH state.
Old remote branch feat/memory-mcp (carries a merge of mine) is superseded; left for the owner to delete. Local fix/carried-114 has 2 commits off main (not mine to judge).

*Observed 2026-10-10 (python-dev)*
