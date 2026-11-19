---
role: "python-dev"
class: workflow
topic: "j236-scratch-driver-no-artifact-close"
description: "j236 shell-to-Python scratch driver delivered by REPLY only; how to close a queued job with no repository artifact"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 11eac8b911c8795b
---

## j236 shell-to-Python scratch driver delivered by REPLY only; how to close a queued job with no repository artifact

A scratch (never committed) driver converted at another agent's request is delivered as script text in a REPLY; no tree, no PR. `fabric-jobs done <j> reply:<id>` refuses on a queued job ("done takes active or delivered"), so `fabric-jobs start <j>` first, then `fabric-jobs done <j> --no-artifact "<what>"`. A stub scratch (fake cargo and mutate.py on PATH, `python3 -I`) is enough for a dry run; the finally-restore is proved by making the mutate step fail on one mutation.

**Why:** the request said "no change to any repository", and the job has no working copy, so `done` with a branch fails.
**How to apply:** scratch-tool conversions: stub dry run, REPLY with the text, start then done --no-artifact.

*Observed 2026-11-13 (python-dev)*
