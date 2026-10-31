---
role: "python-dev"
class: solution
topic: "drain-due-j94"
description: "j94 #419 — fabric-drain-due (ADR-034 §7 step 3): what the review found, how the report treats unknown, the review-brief and shell traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4b4df43a03e47b75
---

## j94 #419 — fabric-drain-due (ADR-034 §7 step 3): what the review found, how the report treats unknown, the review-brief and shell traps

#419 (merged, 3 work + 2 fix, on the owner's word: boundary paths, under the minimum) built tools/fabric/drain_due.py, bin/fabric-drain-due, runtime/control/agent-fabric-drain.{service,timer}, `oldest_drainable_ms` in the harvest report/manifest/ops `_report`, and the status line.

**Why (the findings that mattered):**
- "No store answered" is decided on stores that gave no *count* (`drainable is None`), not on status "unknown": an older control agent's store has a count and no age, and is an answer (F5).
- A failing run must prune nothing and leave no directory without a report.json, or it pushes good runs out of the 4 kept; decide failure before `prune_runs`.
- fabric-jobs has no retitle verb: the open drain job (topic `drain-due`) is retitled with `identity.update_jobs`; priority only moves between normal and high.
- A flock on `drain/.lock` (closed in `finally`) stops two runs adding two jobs.

**How to apply:**
- Re-review brief: `fabric-review save <pr> <round>` after each posted report, then `fabric-review next <previous rr json>` (the first round's REQUEST yaml only for round 2), then `brief` the printed json; paste the brief verbatim into the dispatch. The post-review needs the report as a file written with the Write tool.
- Never `cat > file` without a heredoc in a Bash chain (it reads the tty and hangs); a hook blocks `cd` to another directory for commands that publish (post-review) — write files first, post from the job worktree.
- The bootstrap install step and commands.json line are the coordinator's; the PR merged without them.

*Anchors: `tools/fabric/drain_due.py::collect`, `tools/fabric/harvest_memory.py::DRAIN_BOUND_DAYS`*

*Observed 2026-10-28 (python-dev)*
