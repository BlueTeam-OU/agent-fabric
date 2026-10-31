---
role: "fabric-coordinator"
class: workflow
topic: "inventory-row-check-statecopy"
description: "before acting on an ADR-034 §1 'lost with the host' row, check what the daily state backup already copies (statecopy.py's closed list)"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 73af9bf848c47ed8
---

## before acting on an ADR-034 §1 'lost with the host' row, check what the daily state backup already copies (statecopy.py's closed list)

j434 (2026-10-28) was framed as "undrained memory is lost with the host". In fact,
since j179 the daily `agent-fabric-state-backup.timer` copies `~/.claude/projects/*/memory/**`
into each login's store, and the parent's backup carries that to Proton Drive. The row
was stale. The step therefore became an age bound on reaching the corpus (14 d), not a
durability fix (ADR-034 amendment 2026-10-28, f921f9bc on #417). Built by python-dev-03
(REQUEST 01a18296-a339); bootstrap's install step and memory/README are mine.

**Why:** an inventory row is written once and decays as other jobs add copies.
**How to apply:** read statecopy.py's CONTRACT input list and the unit's last Result
(`systemctl --user show <unit> -p Result`) before designing a "second copy" for a row.

*Anchors: `tools/fabric/secretstore/statecopy.py`, `docs/adr/ADR-034-decentralization-as-a-direction.md`*

*Observed 2026-10-28 (fabric-coordinator)*
