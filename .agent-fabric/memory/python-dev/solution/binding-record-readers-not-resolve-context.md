---
role: "python-dev"
class: solution
topic: "binding-record-readers-not-resolve-context"
description: "readers of only the agent's binding use identity.binding_record, not resolve_context (which resolves cwd's working copy and can fail on an unrelated checkout)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b226bfbbc8f7fc03
---

## readers of only the agent's binding use identity.binding_record, not resolve_context (which resolves cwd's working copy and can fail on an unrelated checkout)

j214 (#511 r4): memory_mcp, gateway_plan, query, sessions._bound read `identity.binding_record(agent)`; `resolve_context` also resolves cwd's marker/registry, so an unregistered marker cost them the binding. Keep the old catch (OSError, ValueError, SystemExit). `BindingRecord.session` is recorded, unchecked; the reader validates its shape. identity.py is outside python-dev's entry: its part goes as a patch, and the worktree must be clean (git restore after saving the diff) for `fabric-jobs switch`.

**Why:** a binding-only reader should not depend on cwd. **How to apply:** new binding readers call binding_record.

*Observed 2026-11-08 (python-dev)*
