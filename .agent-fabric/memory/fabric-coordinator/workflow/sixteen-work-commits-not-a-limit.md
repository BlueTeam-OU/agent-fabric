---
role: "fabric-coordinator"
class: workflow
topic: "sixteen-work-commits-not-a-limit"
description: "the charter's \"at most sixteen work commits\" does not stop the next piece of work riding the open PR; the owner said add it there"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 412116b29ebc92d7
---

## the charter's "at most sixteen work commits" does not stop the next piece of work riding the open PR; the owner said add it there

2026-11-12 (j766 PR, then at 16 work commits): I proposed putting j801's auto-mode entry on a later PR because the charter says "at most sixteen work commits". The owner: "16 is not a limit, add there". It landed as 61c39a35, the 17th.

**Why:** the owner reads the open PR as the place for the next piece of work; splitting by a count makes a second PR, which is what the one-PR rule exists to prevent.

**How to apply:** when the open PR reaches 16 work commits, still put the next piece of work on it and say the count in the report; do not move work to a later PR or squash commits to fit 16 without asking. The charter text is fabric-coordinator's to propose changing ([[next-work-rides-the-open-pr]]).

*References: next-work-rides-the-open-pr*

*Anchors: `identities/roles/fabric-coordinator/charter.md::at most sixteen work commits`*

*Observed 2026-11-12 (fabric-coordinator)*
