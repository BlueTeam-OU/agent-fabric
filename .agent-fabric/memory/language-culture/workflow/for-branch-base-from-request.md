---
role: "language-culture"
class: workflow
topic: "for-branch-base-from-request"
description: "fabric-jobs switch cuts a for/ branch from origin/main; when DELIVER-TO says \"based on the branch below\", reset it to the caller's branch first"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 00c52404ff4f543e
---

## fabric-jobs switch cuts a for/ branch from origin/main; when DELIVER-TO says "based on the branch below", reset it to the caller's branch first

The for/ branch `fabric-jobs switch` creates is cut from origin/main. When a request's DELIVER-TO says "based on the branch below", reset it onto the caller's branch while it has no commits of its own; otherwise the source commit is not in its history and translates_digest is computed against the wrong English. Seen in j114 (2026-11-11): base df5803f8, source d7adeb2f, head 1ce7b065. Check first with `git merge-base --is-ancestor <source commit> HEAD`.

*Anchors: `tools/fabric/jobs.py::fabric-jobs switch`*

*Observed 2026-11-10 (language-culture)*
