---
role: "fabric-coordinator"
class: domain
topic: "slice-correction-attribution-writer-name"
description: "Correction for memory/shared/domain-claude-code-attribution-reminder.md: the writer bootstrap.sh runs is runtime/claude-code/user-settings.py (attribution-off.py until 2026-09-20), and it also sets showThinkingSummaries and verbose"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - 57b5e74789811d10
---

## Correction for memory/shared/domain-claude-code-attribution-reminder.md: the writer bootstrap.sh runs is runtime/claude-code/user-settings.py (attribution-off.py until 2026-09-20), and it also sets showThinkingSummaries and verbose

The slice `memory/shared/domain-claude-code-attribution-reminder.md`
(line ~47) says the attribution key is written into every account's
user settings by `runtime/claude-code/bootstrap.sh` through
`attribution-off.py`. Since agent-fabric PR #25 (2026-09-20) that
writer is `runtime/claude-code/user-settings.py`: the same attribution
keys, plus `showThinkingSummaries: true` and `verbose: true`, the
owner's decision so the operator reads a session's thinking summaries
and full tool output from its terminal. The tree is the fact; the
slice's mechanism description is otherwise current.

*Observed 2026-09-20 (fabric-coordinator)*
