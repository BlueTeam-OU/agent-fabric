---
role: "python-dev"
class: workflow
topic: "open-chain-after-whole-head-review-needs-defer"
description: "arm refuses on an earlier review's open findings once a later whole-head review is the PR's checkpoint; post-review refuses the chain re-review, so --defer is the route"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e83018b3dcd6396e
---

## arm refuses on an earlier review's open findings once a later whole-head review is the PR's checkpoint; post-review refuses the chain re-review, so --defer is the route

j103/j104 (#526, 2026-11-09): round 2 (main merged into the fix range) was posted but its
coverage was void, so I ran a fresh review of origin/main..HEAD (round 3). It found F1/F2;
I fixed them and ran another whole-range review (round 4, no findings), which became the
PR's last checkpoint. `fabric-pr arm` then refused: F1/F2 of round 3 were still open
(gate 4c). A re-review judging them (base = round 3's head) was refused by `post-review`:
"neither the merge-base nor the head of the PR's last checkpoint review".

**Why:** a narrower range is not the review of the PR, and the checkpoint had already moved.

**How to apply:** after a fix, do not run a whole-range review next if the previous round
has open findings: render the chain re-review first (base = that round's head, post it), then
the whole-head one. If already past that, arm with `--defer "<head8>:F<n>" "<why>"` per
finding (reason without the words "post-review" in a Bash call: the hook reads them as a
posting). A merge of origin/main into the branch belongs before the last fixes, see
[[rereview-after-main-merge-reads-nothing-covers-no-head]]. The arm minimum was 1 work
commit here; read the dry-run.

*References: rereview-after-main-merge-reads-nothing-covers-no-head*

*Anchors: `tools/fabric/github/post_review.py::REVIEW_MARKER`*

*Observed 2026-11-09 (python-dev)*
