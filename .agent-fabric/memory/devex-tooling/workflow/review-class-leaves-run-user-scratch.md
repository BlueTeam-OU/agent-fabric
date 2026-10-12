---
role: "devex-tooling"
class: workflow
topic: "review-class-leaves-run-user-scratch"
description: "a code-review dispatch that exports trees for mutation runs cannot delete them; the session removes /run/user/<uid>/rv.*"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-12"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 174a05d855fa945e
---

## a code-review dispatch that exports trees for mutation runs cannot delete them; the session removes /run/user/<uid>/rv.*

The review class's Bash fence refuses `rm`, so a reviewer that `git archive`s base and head for mutation
runs leaves them under `/run/user/<uid>/rv.XXXX` (32 MB on the j95 review, 2026-10-12) and asks the
session to delete them. After every review report, check `/run/user/$(id -u)/rv.*` and remove what that
review made (a tmpfs: it costs RAM until removed).

*Observed 2026-10-11 (devex-tooling)*
