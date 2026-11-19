---
role: "python-dev"
class: workflow
topic: "arm-on-owner-word-done-needs-pr-arg-j131"
description: "arming a below-minimum PR on the owner's word, then closing the job: basis text, done needs the PR as artifact"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1ef60632a0e15e3e
---

## arming a below-minimum PR on the owner's word, then closing the job: basis text, done needs the PR as artifact

j131 (#563, 1 work, 0 fix): `fabric-pr arm 563 --basis "owner's word: ..."` armed at the review gate with pending platform-smoke checks; `fabric-pr wait-merged 563` in background returned MERGED.

After merge, `fabric-jobs deliver` refuses a merged PR/sha ("needs an artifact that is open"); use `fabric-jobs done j131 "#563"` instead. `switch` then refuses until every REPLY-EXPECTED message (including one queued while the job ran) is answered and the memory dir changed. The Stop hook wants "#N (W work, F fix)" from `fabric-pr gate` in every status line, merged included.

**Why:** cost several failed verbs. **How to apply:** done with the merged PR number, answer pending requests, write memory, then switch.

*Anchors: `bin/fabric-jobs::done needs evidence it landed`*

*Observed 2026-11-12 (python-dev)*
