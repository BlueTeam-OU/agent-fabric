---
role: "devex-tooling"
class: domain
topic: "gh-pr-merge-strategy-flag-on-a-queued-repo"
description: "`gh pr merge --auto --merge` on gzapp prints what looks like a refusal, leaves autoMergeRequest null, yet DOES enqueue the PR."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 3592cf3161d13a86
  - 796c6629674f5430
  - ca6c411630d574f5
---

## correction — on a queue-managed repo read the queue with `fabric-pr gate` (queue=<pos>); `fabric-pr arm` already reports "queued at N"

On a repository whose main has a merge queue (gzapi-org/gzapp, InterWeave), `gh pr merge --auto --merge` prints what looks like a refusal and leaves `autoMergeRequest` null, yet it enqueues the PR when its checks are already green. Never read "not armed" from `autoMergeRequest` alone. Read the queue entry: `fabric-pr gate <n>` prints `queue=<pos>`, or query `mergeQueueEntry{position state}` directly.

`fabric-pr arm` reads the queue entry too, and reports an instantly queued PR as "queued at N". The `runtime/github/*.sh` and `tools/gh/*.sh` paths are forwarders to `fabric-pr`; call `fabric-pr` itself.

*Observed 2026-10-10 (devex-tooling)*
