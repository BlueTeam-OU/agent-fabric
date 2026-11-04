---
role: "devex-tooling"
class: workflow
topic: "review-class-leaves-run-user-scratch"
description: "a code-review dispatch leaves scratch it cannot delete — /run/user/<uid>/rv.* trees, or an empty tmp.* in the scratchpad; the session removes them"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 174a05d855fa945e
  - 4855ba55c2df4378
---

## a code-review dispatch leaves scratch it cannot delete — /run/user/<uid>/rv.* trees, or an empty tmp.* in the scratchpad; the session removes them

The review class's Bash fence refuses `rm`, so a reviewer that `git archive`s base and head for mutation
runs leaves them under `/run/user/<uid>/rv.XXXX` (32 MB on the j95 review, 2026-10-12) and asks the
session to delete them. After every review report, check `/run/user/$(id -u)/rv.*` and remove what that
review made (a tmpfs: it costs RAM until removed).

It can also leave an empty `tmp.XXXX` under this session's scratchpad: the guard lets it create the directory
and then refuses writes (gzapp #1135 round 3, 2026-10-19). Check the scratchpad for `tmp.*` too.
A reviewer that cannot write reproduces with an in-memory stub (`bash -c` with a `gh` function), which is
enough for a workflow's run: script.

*Observed 2026-10-11 (devex-tooling)*
