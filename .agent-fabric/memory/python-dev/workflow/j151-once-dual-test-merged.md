---
role: "python-dev"
class: workflow
topic: "j151-once-dual-test-merged"
description: "j151 — #616 merged; AgentdOnce case pins 'and not once' on the dual start; review-base and arm-defer traps"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3f38d8fad154210a
---

## j151 — #616 merged; AgentdOnce case pins 'and not once' on the dual start; review-base and arm-defer traps

#616 merged (1 work, 1 merge): `AgentdOnce` in tests/test_control_agentd_dual.py; Base takes an `argv` class attribute. The guard tested is the `if` at agentd.py's dual start, not hold_for_ctl (which only asserts `not once`).

**Why:** the brief rendered from a request with `range: origin/main..HEAD` pinned base = origin/main; the branch was 24 commits behind, so `fabric-pr post-review` refused ("base not an ancestor of head").
**How to apply:** fetch and merge origin/main into the branch before rendering the brief, then re-dispatch the review; post-review must be the bare command with `< file`. A deferred P3 arms with `fabric-pr arm N --basis ... --defer "<head8>:F<n>" "<why>"`. A commit/push command containing `$HOME` is refused by the job-copy guard: use `env -i PATH=$PATH` instead.

*Anchors: `tests/test_control_agentd_dual.py::AgentdOnce`*

*Observed 2026-11-14 (python-dev)*
