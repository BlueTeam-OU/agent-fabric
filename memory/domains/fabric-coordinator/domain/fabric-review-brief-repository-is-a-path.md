---
role: "fabric-coordinator"
class: domain
topic: "fabric-review-brief-repository-is-a-path"
description: "fabric-review brief takes repository: as a working-copy path, not owner/name"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "radicle-spike"
    working_copy: "radicle-spike"
derived_from:
  - ee7b2264283da0bd
---

## fabric-review brief takes repository: as a working-copy path, not owner/name

`fabric-review brief` takes `repository:` as the working copy's PATH, not `owner/name`: given `owner/name` it
refuses with "is not a git working copy", because it tests for `.git` under the given path
(`tools/fabric/review_brief.py`). Split out of [[drain-project-half-index-only-check]] after review finding F2 on
radicle-spike #7 (review 5821174729): a fact about agent-fabric's own CLI belongs in its corpus, not a project's.

*References: drain-project-half-index-only-check*

*Observed 2026-11-14 (fabric-coordinator)*
