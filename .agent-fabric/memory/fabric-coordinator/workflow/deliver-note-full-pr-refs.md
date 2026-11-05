---
role: "fabric-coordinator"
class: workflow
topic: "deliver-note-full-pr-refs"
description: "fabric-jobs sweep leaves a delivered job open when its artifact text names any bare #N"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cacfd656f1169847
---

## fabric-jobs sweep leaves a delivered job open when its artifact text names any bare #N

`fabric-jobs sweep` resolves every `#N` in a delivered job's artifact text, and one bare `#444` (no owner/repo) leaves the job undone: "unresolved: #444 names no repository". This happened on j532 (2026-11-01), whose note said "codex absent on #444/#451".

**Why:** the sweep cannot tell which repository a bare number belongs to, so it refuses rather than guess.

**How to apply:** write every PR in a deliver artifact as `BlueTeam-OU/agent-fabric#N`, the prose too. If the landing is already verified by hand, `fabric-jobs done <id>` closes the job directly.

*Observed 2026-11-01 (fabric-coordinator)*
