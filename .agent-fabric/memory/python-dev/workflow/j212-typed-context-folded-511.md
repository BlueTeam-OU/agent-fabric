---
role: "python-dev"
class: workflow
topic: "j212-typed-context-folded-511"
description: "j212 typed AgentContext folded by the coordinator into #511 (no own PR); out-of-entry files go as a patch in the REPLY; dataclass-by-path trap"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 06a168b27434221e
---

## j212 typed AgentContext folded by the coordinator into #511 (no own PR); out-of-entry files go as a patch in the REPLY; dataclass-by-path trap

j212 (W1-C): the hook refuses python-dev commits of identity.py, policies/, lint.py, lint_rules/ even on a for/ branch, so the supply was a `git diff HEAD` patch pasted as a PATCH: section in the REPLY (299 lines went through gzcoord-send). The coordinator folded my feat branch unrebased into #511 and applied the patch; I opened no PR.

**Why:** the branch alone cannot pass CI without the out-of-entry half. **How to apply:** next time put the patch in the REPLY at once and say "open no PR yet".

Traps: a dataclass in a module loaded with spec_from_file_location (never in sys.modules) fails on 3.14 under `from __future__ import annotations` (dataclasses reads sys.modules[cls.__module__]); identity's `_frozen` registers a stand-in for the call. A path-loaded identity makes resolve_context need workingcopy.py+roots.py under a fixture AGENT_FABRIC_ROOT. Never type `git stash` as a probe: it stashed my work (restored via apply of the entry sha, then drop). Follow-up job j213: read_binding raw-dict callers; SyntaxWarning suppression in context_reads.

*Observed 2026-11-08 (python-dev)*
