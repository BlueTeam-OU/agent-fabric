---
role: "fabric-coordinator"
class: workflow
topic: "owner-arm-word-runs-next"
description: "an owner's 'arm N' becomes the NEXT session's job (blocking priority, switch now), never a queued line among a hundred; 11-12 and 11-13 words for the drain PRs sat unexecuted"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a9e5e5d088b28102
---

## an owner's 'arm N' becomes the NEXT session's job (blocking priority, switch now), never a queued line among a hundred; 11-12 and 11-13 words for the drain PRs sat unexecuted

The owner told me to arm the drain PRs three times:
- 2026-11-12: "arm both" (gzapi.brand#14 and gzapp.decks#29).
- 2026-11-13, earlier: "arm your four drain PRs now" (j821–j824). The same day, "arm both" for blueteam.brand#4 (j825).
- 2026-11-13 ~22:40Z: "arm both now".

The first two were queued as jobs, and none of those jobs ran. When the third word came, the job-copy guard refused `fabric-pr arm`. This session had already closed jobs in place, and ADR-037 rule 3 says a session that has worked a job publishes nothing more: the next job needs a fresh session.

**Why:** an arm on the owner's word is the owner's decision waiting on me. Queued at normal priority among 80+ jobs, it is lost.
**How to apply:**
- On an owner's "arm N", add the job at `--priority blocking`, settle the current job, and run `fabric-jobs switch` now.
- Before closing jobs in place to tidy the list, run any arm or publish the owner asked for. After closing them, the session can only read.
- Before adding a new arm job, check for an earlier one on the same PR (`fabric-jobs list | grep '#N'`).

Related: [[never-wait-on-owner-to-arm]], [[owner-arm-word-drain-prs-2026-11-12]].

*References: never-wait-on-owner-to-arm, owner-arm-word-drain-prs-2026-11-12*

*Observed 2026-11-13 (fabric-coordinator)*
