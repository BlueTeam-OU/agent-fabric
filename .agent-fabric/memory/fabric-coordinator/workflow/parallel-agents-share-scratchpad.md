---
role: "fabric-coordinator"
class: workflow
topic: "parallel-agents-share-scratchpad"
description: "Parallel subagents share the session scratchpad; a generic run.sh got overwritten and printed another agent's env with credentials — give each its own subdirectory, never dump env"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - da238cc3e529b508
---

## Parallel subagents share the session scratchpad; a generic run.sh got overwritten and printed another agent's env with credentials — give each its own subdirectory, never dump env

2026-10-02, Wave 6: five worktree-isolated port agents ran at once. Worktree isolation covers the repository, not the session scratchpad, which they all share. Two wrote `run.sh` there; one's version printed its full environment (API keys, tokens) and the other agent ran it, so the credentials landed in the wrong agent's output. Nothing left the session (no commit, message or relay), and no scratch file kept a value afterwards (checked by prefix, masked).

**Why:** the dispatch prompts named no scratch location, and a debugging `env` is natural for a hermeticity task.

**How to apply:** every parallel dispatch prompt says: scratch under `<scratchpad>/<task-name>/` only, never a generic filename, never print the environment (strip variables, do not list them). Related: [[suite-scratch-leak]], [[run-suites-as-ci-before-push]].

*References: run-suites-as-ci-before-push, suite-scratch-leak*

*Observed 2026-10-02 (fabric-coordinator)*
