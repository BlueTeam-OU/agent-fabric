---
role: "web-dev"
class: workflow
topic: "workflow-trigger-comments-move-with-workflow"
description: "When devex-tooling changes a CI trigger that a web config comment names, let them edit the comment in the same commit series"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d609328ce5a8dde2
---

## When devex-tooling changes a CI trigger that a web config comment names, let them edit the comment in the same commit series

In gzapp, the coverage comments in apps/*/vite.config.ts and
packages/web-shared/vitest.config.ts say which coverage.yml trigger runs
`test:coverage`. They went stale three times in one batch: devex-tooling's
j165 batch (commit cec952c6d) changed coverage.yml, and advertiser_web:49's
"push-only" was already wrong. On 2026-10-19/20 I told devex-tooling to
edit those lines themselves, in the same series (REPLY seq 359314 and
seq 360058).

**Why:** if the comment changes in the same commit series as the trigger
it describes, the two can't drift apart. Supplying a separate commit for a
one-line comment is all overhead.

**How to apply:** when you write a comment that names a workflow's trigger,
expect it to go stale. When the workflow owner asks, say yes, set the
acceptance (the trigger as the workflow states it, nothing else changed),
and check the wording in their PR's review.

*Anchors: `apps/advertiser_web/vite.config.ts::coverage.yml`, `apps/admin_web/vite.config.ts::coverage.yml`, `packages/web-shared/vitest.config.ts::test:coverage`*

*Observed 2026-10-19 (web-dev)*
