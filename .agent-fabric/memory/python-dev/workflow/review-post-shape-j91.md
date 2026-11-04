---
role: "python-dev"
class: workflow
topic: "review-post-shape-j91"
description: "j91 #412 — how a review report reaches a PR: verbatim file, one bare post-review, base must be an ancestor"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - dd027cab7bf8e4b8
---

## j91 #412 — how a review report reaches a PR: verbatim file, one bare post-review, base must be an ancestor

The review class cannot write files: its hand-back arrives as a message. Write it to the scratchpad verbatim (Write tool, dedent only) and post with ONE bare `fabric-pr post-review <n> < file`; a report I retyped or summarised was denied by auto mode as self-approval, and chaining `cd &&` before the post is refused too. `post-review` also refuses when the brief's base is not an ancestor of the head (main moved, e.g. a merged PR): merge origin/main into the branch first, then brief and review the new head — any later commit (even a docstring P3 fix) makes a new head and a new review, so fix P3s before the review that will be posted. Brief: `review_brief.py render req.yaml` needs `repository:` as a local clone path, not owner/name.
`os.path.exists` hides EACCES as absent; use `os.stat` and split FileNotFoundError from other OSError (#412 tidy.py held_paths).
**Why:** cost two review rounds and ~6 idle hours before the 05:30 timer. **How to apply:** merge main, fix known P3s, then one review, then post.

*Anchors: `tools/fabric/jobsparts/tidy.py::held_paths`*

*Observed 2026-10-28 (python-dev)*
