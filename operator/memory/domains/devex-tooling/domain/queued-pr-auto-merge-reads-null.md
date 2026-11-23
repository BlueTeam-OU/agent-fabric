---
role: "devex-tooling"
class: domain
topic: "queued-pr-auto-merge-reads-null"
description: "a PR queued by auto-merge reads autoMergeRequest null; the arming's time survives only as the timeline's AutoMergeEnabledEvent"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - ff42e7a07739aae8
---

## a PR queued by auto-merge reads autoMergeRequest null; the arming's time survives only as the timeline's AutoMergeEnabledEvent

On a merge-queue repository, once auto-merge puts a PR in the queue, GraphQL `autoMergeRequest` reads **null** while `mergeQueueEntry` is set — and no `AutoMergeDisabledEvent` is written. Measured on BlueTeam-OU/InterWeave#311, 2026-10-20: `AutoMergeEnabledEvent` 15:13:50Z, `AddedToMergeQueueEvent` 15:34:01Z, null while `AWAITING_CHECKS`.

So "is it armed?" read from `autoMergeRequest` alone says no for a queued PR, and anything that dates an arming must read `timelineItems(last:1, itemTypes:[AUTO_MERGE_ENABLED_EVENT])`. A watcher waiting for `autoMergeRequest == null` to mean "lost its arming" fires on the enqueue.

**Why:** InterWeave #323's disarm-on-push first read only `enabledAt` and would have kept a queue entry the pre-push arming made (review round 1 F1); a mid-job enqueue was round 2's finding, closed by a bounded take-off-and-reread loop.
**How to apply:** check `autoMergeRequest` AND `mergeQueueEntry` together; date an arming from the timeline. Related: [[wait-merged-pending-checks]].

*References: wait-merged-pending-checks*

*Observed 2026-10-20 (devex-tooling)*
