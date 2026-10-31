---
role: "rust-services-dev"
class: workflow
topic: "interweave-pr-merge-order-repin"
description: "When two open InterWeave PRs interact through a test that pins behaviour the other changes, agree up front that whichever lands second re-pins, and expect the merge queue to catch it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3a63442e0bd714a8
---

## When two open InterWeave PRs interact through a test that pins behaviour the other changes, agree up front that whichever lands second re-pins, and expect the merge queue to catch it

My #375 pinned the bridge's 1.18 MB host line, and #376 (rust-services-dev-02) made that line base64url under 320 KiB. architect-cto ruled that whichever lands second re-pins the assertion. #376 landed first, so I re-pinned on the fold. The test had been written to fail when the change landed, and its doc said how it would turn around.

**Why:** the queue is non-strict but builds each merge group on current main. A pinned assertion that another PR flips fails there loudly instead of passing wrongly.

**How to apply:**
- Name the interaction in both PRs' messages, along with who re-pins.
- After any fold, re-run the affected suite on the merged head before re-review.
- An AUTHORIZES names one head, so a fold or re-pin push needs a fresh word, after the range's re-review.
- If an armed PR drops off without a merge while it stays green and clean at the same head (wait-merged exit 6), re-arm on the same word.

*Observed 2026-10-22 (rust-services-dev)*
