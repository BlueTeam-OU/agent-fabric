---
role: "fabric-coordinator"
class: workflow
topic: "review-next-needs-saved-round"
description: "fabric-review next refuses without a saved round and a commit-id range; recover a posted round from the PR"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 97b74b1b6942fe79
---

## fabric-review next refuses without a saved round and a commit-id range; recover a posted round from the PR

`fabric-review next REQ --pr N` needs the previous round saved
(`fabric-review save N <round> < report`) and the request's `range:` as
`<sha>..<sha>`, not `origin/main..HEAD` (refused: "the previous range's head
'HEAD' is not a commit id"). When the session that posted round 1 left no
saved round, recover it from GitHub: `gh pr view N --json reviews --jq
'.reviews[-1].body'` → save as round 1, set range to main-sha..reviewed-head,
then `next … --head <new head>`. Seen on #465 round 2 (j527, 2026-11-03).

*Anchors: `tools/fabric/review_rounds.py::no round saved for`, `tools/fabric/review_rounds.py::is not a commit id: name the reviewed head`*

*Observed 2026-11-03 (fabric-coordinator)*
