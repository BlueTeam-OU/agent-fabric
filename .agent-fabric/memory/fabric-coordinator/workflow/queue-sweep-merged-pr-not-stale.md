---
role: "fabric-coordinator"
class: workflow
topic: "queue-sweep-merged-pr-not-stale"
description: "sweeping my job queue for stale entries: a merged PR named in a title rarely means the job is done; read main for each 'fold/supply/distribute onto #N' job"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 53ba83ae14eb14ae
---

## sweeping my job queue for stale entries: a merged PR named in a title rarely means the job is done; read main for each 'fold/supply/distribute onto #N' job

On 2026-11-14, 25 of my ~100 open jobs named a merged agent-fabric PR. Only 2 of them were really done: j850 by #599, and j862 by the distribution. Most were follow-ups that the merge had created. The "onto #N" jobs were the dangerous ones. When #N merged without the fold, the work was not dropped but orphaned:
- j829: python-dev-03's supply for/user/w14-relay-catchup-removed (1d128b22) sat on origin a day after j814's PR merged without it.
- j797: my supply for python-dev-02's #570 never landed.

**How to apply:** when a PR merges, look for any job of mine that targets it (`fabric-jobs list | grep '#N'`) and turn it into a commit on my next PR the same day. A fold job is open until `git merge-base --is-ancestor <tip> origin/main` says yes. Related: [[supply-target-merged-first]], [[next-work-rides-the-open-pr]].

*References: next-work-rides-the-open-pr, supply-target-merged-first*

*Anchors: `tools/fabric/lint.py::relay_catchup`*

*Observed 2026-11-14 (fabric-coordinator)*
