---
role: "python-dev"
class: workflow
topic: "arming-on-relayed-owner-word"
description: "PRs under eight work commits are armed by python-dev-03 on the owner's word as fabric-coordinator relays it; the basis text and the counts format the Stop hook demands"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d4837eea74fd454a
---

## PRs under eight work commits are armed by python-dev-03 on the owner's word as fabric-coordinator relays it; the basis text and the counts format the Stop hook demands

Under eight work commits I do not arm on my own: I tell fabric-coordinator the PR is green with its head reviewed and no threads, and they relay the owner's word ("arm 149"); I then run `fabric-pr arm <N> --basis "the owner's word, relayed by develop-qzapp/user (fabric-coordinator) in seq <n>, <date>: \"arm <N>\"; <counts and gate>"`. The arm tool wants the phrase "owner's word" in the basis. A PR that is clean merges at once on arming. Every reply that states a PR's status must give "#N (W work, F fix)" read from `fabric-pr gate <N>` (the Stop hook blocks otherwise); for a merged PR the gate says MERGED and has no counts, so say the last counts read before the merge.
**Why:** the hook cost several turns on #139 and #140.
**How to apply:** each PR of mine; send the readiness INFO with `--force` when the coordinator has no session.

*Observed 2026-10-09 (python-dev)*
