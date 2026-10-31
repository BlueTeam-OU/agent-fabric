---
role: "devex-tooling"
class: workflow
topic: "job-landed-check-by-commit"
description: "Closing jobs as \"landed\": check each named commit on origin/main (ancestor, else same subject), not the PR state the coordinator matched"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ef627689ed21ce07
---

## Closing jobs as "landed": check each named commit on origin/main (ancestor, else same subject), not the PR state the coordinator matched

When asked to close jobs because "a PR it names is MERGED" (fabric-coordinator's
job-list sweep, 2026-10-18, REQUEST 01a15091), check the commits instead:
`git merge-base --is-ancestor <c> origin/main`, and when that fails,
`git log origin/main --fixed-strings --grep="<subject>"`. InterWeave and gzapp
rebase or squash folds, so commits land under new hashes.

**Why:** the sweep matched `#N` without the repository. It paired j111 with
gzapi-org/gzapp#233 when the job meant agent-fabric#233. It also listed
j38 as merged, but its commit ae88eed9e never landed: the work was
superseded by the fabric port, so the job was a drop, not a done.

**How to apply:** check every listed job this way, then use `done` for
landed work and `drop "<why>"` for superseded work. Name any mismatched
PR in the reply.

*Anchors: `tools/fabric/github/wait_merged_input.py::incident`*

*Observed 2026-10-18 (devex-tooling)*
