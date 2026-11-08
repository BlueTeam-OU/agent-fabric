---
role: "language-culture"
class: workflow
topic: "caller-branch-moves-with-sibling-locale"
description: "a caller's branch takes the ru-RU holder's push in the same round; fetch and rebase before pushing"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric-j138-reflection-pass-2026-w44-run-fabric"
derived_from:
  - b22099dac453a133
---

## a caller's branch takes the ru-RU holder's push in the same round; fetch and rebase before pushing

When fabric-coordinator asks every locale together for a key on a caller's
branch, the ru-RU holder's commit often lands on that branch first. In j140
both pushes were refused by pre-push with "Invalid revision range <remote
oid>..", which reads like a secret-check failure but means the branch moved.
Fetch, rebase onto the caller's branch (different file, no conflict), push.

*Observed 2026-11-07 (language-culture)*
