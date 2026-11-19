---
role: "fabric-coordinator"
class: workflow
topic: "owner-word-blocker-blocks-arm"
description: "fabric-pr arm refuses while a job on the PR's branch is blocked on \"owner: word to arm\" — deliver that job once the word is given"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: gzapi.brand
    working_copy: gzapi.brand
derived_from:
  - b68dae88447c2484
---

## fabric-pr arm refuses while a job on the PR's branch is blocked on "owner: word to arm" — deliver that job once the word is given

`fabric-pr arm` (gate: blocked job on the PR's branch) refuses a PR when one of your own jobs on its
branch is still `blocked` on a non-checkable "owner: word to arm …" blocker, even after the owner
has given that word. fabric-jobs has no unblock verb: `fabric-jobs deliver <job> pr:<repo>#<n>`
clears it honestly (the job's work is the PR), then arm passes; `done` it after the merge.
Seen arming gzapi-org/gzapi.brand#14 on 2026-11-13 (job j499).

**Why:** `--defer-job` is for a wait that is *not* this PR's; this one was the PR's own arming word.
**How to apply:** before arming on the owner's word, check `fabric-jobs list` for a job blocked on
that same word and deliver it first. Related: [[drain-hold-is-per-bundle]].

*References: drain-hold-is-per-bundle*

*Anchors: `agent-fabric:tools/fabric/github/arm.py::defer-job`*

*Observed 2026-11-13 (fabric-coordinator)*
