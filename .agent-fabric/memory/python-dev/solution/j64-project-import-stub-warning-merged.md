---
role: "python-dev"
class: solution
topic: "j64-project-import-stub-warning-merged"
description: "fabric-project import #308 merged — stub remits named on stderr, plan names its tree, empty path flags refused; review traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fbeac28d2b9a0d7b
---

## fabric-project import #308 merged — stub remits named on stderr, plan names its tree, empty path flags refused; review traps

#308 (1 work, 2 fix) merged 2026-10-19 on top of [[j63-fabric-project-import-merged]]: the plan's first line names ROOT; each stub remit is marked `[stub remit]` and has its own stderr reason (sibling working copy not found / `<file> does not exist`); a `--like-working-copy` that is not a directory, and an empty `--working-copy`/`--like-working-copy`, are refused (exit 2).

**Why / traps:**
- A path flag tested by truthiness reads an unset shell variable (`""`) as "absent": refuse empty before any truthiness use (found by re-review, round 2).
- Record the reason where the fallback is decided (per-file `stub` string), never recompute it afterwards from the flags (round-1 P2).
- `git checkout <file>` to undo a mutation also drops uncommitted fixes: commit first, mutate after.
- `fabric-review brief` wants `repository:` as a local path, `card_base`/range as full shas, `previous_findings` as a file path; the review subagent does not post: post with `fabric-pr post-review` yourself.
- A commit can fail on the OpenTimestamps step (transient): retry once.

*References: j63-fabric-project-import-merged*

*Anchors: `tools/fabric/project.py::plan`, `tests/test_project_import.py`*

*Observed 2026-10-19 (python-dev)*
