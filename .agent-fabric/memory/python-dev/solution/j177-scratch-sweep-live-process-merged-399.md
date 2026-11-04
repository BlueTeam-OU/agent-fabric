---
role: "python-dev"
class: solution
topic: "j177-scratch-sweep-live-process-merged-399"
description: "branches.py sweep keeps a session scratch dir a live process uses (cwd, fd, cmdline id); merged #399; carried P3s; subagent brief/post-review mechanics"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 149a9b55db728f39
---

## branches.py sweep keeps a session scratch dir a live process uses (cwd, fd, cmdline id); merged #399; carried P3s; subagent brief/post-review mechanics

#399 (2026-10-27): `sweep_sessions` calls `process_touches()` (one /proc scan: cwd, fd links, cmdline, own pid excluded) and `scratch_holder()`; /proc unreadable keeps all. `fabric-jobs switch` shares it through `leave_sweep.py` (`--sweep --worktrees`).
**Why:** after /clear the harness process changes session id but its task children keep writing under the old id's dir.
**How to apply:** carried P3s: no sweep-level test of the unreadable-/proc keep; ADR-022 §5 rule 11 still registry-only (coordinator's). Unproven: a real /clear run with a task child holding an fd.
Mechanics: `fabric-review brief` is broken (usage error) - run `python3 tools/fabric/review_brief.py render req.yaml`; post-review reads the report on stdin; with 1 work commit the owner's "merge" is the arming basis once the review gate is met. Mutation on committed state, sed + cp restore.

*Observed 2026-10-27 (python-dev)*
