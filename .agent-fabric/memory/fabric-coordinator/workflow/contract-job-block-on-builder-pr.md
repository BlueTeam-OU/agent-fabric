---
role: "fabric-coordinator"
class: workflow
topic: "contract-job-block-on-builder-pr"
description: "A \"contract for a python-dev\" job on my list is blocked on the builder's PR the moment their REPLY names it; left on --on-request, switch takes it active with a stale blocked-on text (j375, 2026-10-24)"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 63bf32a1b232d2b6
---

## A "contract for a python-dev" job on my list is blocked on the builder's PR the moment their REPLY names it; left on --on-request, switch takes it active with a stale blocked-on text (j375, 2026-10-24)

j375 (post-review large-review contract) stayed `blocked --on-request` after
python-dev-03 opened #370 for it. A later `fabric-jobs switch` took j375
active with its old "blocked on: python-dev-03 builds it" text, in the
j381 worktree, and the next switch refused to leave it until a memory
changed. The job had nothing of mine left to do.

**Why:** a request block clears when the request's job on the other list
ends; the artifact that matters to me is the PR, and `pr:` is what the
blocker checker reads to settle.

**How to apply:** when a builder's REPLY names a PR for a contract job of
mine, run `fabric-jobs block <id> --on pr:<owner/repo>#<n>` at once (or
`deliver` it with the PR when nothing of mine remains), so switch never
picks it as work. See [[park-a-job-block-not-pause]].

*References: park-a-job-block-not-pause*

*Observed 2026-10-24 (fabric-coordinator)*
