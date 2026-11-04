---
role: "python-dev"
class: workflow
topic: "arm-under-8-boundary-needs-owners-word-phrase"
description: "arming under 8 work commits on a security-boundary PR; the basis must carry \"the owner's word\"; the classifier refuses the agent's arm, the owner runs it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8e12b5fde12fed25
---

## arming under 8 work commits on a security-boundary PR; the basis must carry "the owner's word"; the classifier refuses the agent's arm, the owner runs it

Under the minimum work count, a PR touching a security-boundary file (here tools/fabric/control/tools.py arrived via a main merge) arms only with "the owner's word" in `--basis` (or an architect-cto AUTHORIZES id). The auto-mode classifier refused my own `fabric-pr arm` three ways (Merge Without Review, CI Bypass) even after the owner said "merge"; the owner ran `fabric-pr arm N --basis "the owner's word"` as a `!` command and it merged (#303, 2026-10-19).

**Why:** a subagent review plus a relayed word is not enough for the classifier; the owner's own shell is.
**How to apply:** post the review first, read `fabric-pr gate`, then hand the owner the one-line `! fabric-pr arm N --basis "the owner's word"` instead of retrying. A request for review of a range whose base is not on origin/main needs `card_base: <origin/main sha>` in the request file. Old /var/tmp/agent-fabric-<login> removal with `git worktree remove --force` was classifier-denied too; remove without --force.

*Observed 2026-10-19 (python-dev)*
