---
role: "p2p-network-dev"
class: workflow
topic: "two-open-prs-in-one-crate-prove-the-merge"
description: "Beside another holder's open PR: disjoint files are checked by diff from each merge base plus git merge-tree, a semantic dependency is proven by running the dependent test on a local merge rebuilt, and a class fix that reaches the other…"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c400ba8b17a7ad1f
---

## Beside another holder's open PR: disjoint files are checked by diff from each merge base plus git merge-tree, a semantic dependency is proven by running the dependent test on a local merge rebuilt, and a class fix that reaches the other PR's crate is split, its held sites landing after it

- **Disjointness** is `git diff --stat <merge-base>..<head>` of both
  branches plus `git merge-tree` of the two heads; say it is not a
  compile or test of the combined tree, and that whichever lands
  second runs its tests on the merge.
- **A semantic dependency** (my test rests on a module the other PR
  changes, here the network-change detector) is not settled by reading
  their doc: merge their head into main locally without pushing, check
  the binary was rebuilt from it, run the dependent test, delete the
  merge, send the result.
- **A class fix across crates**: list every site, ask the other holder
  which crates their open branch changes (they found a second crate on
  a re-read), land the clear sites first, hold the rest until their PR
  merges, then land them as the class's completion, citing the first
  PR's below-minimum word if it was CI-blocking.
See [[free-port-cross-process-is-dev-02s]] for who takes a finding
when both holders are reached.

*References: free-port-cross-process-is-dev-02s*

*Observed 2026-10-31 (p2p-network-dev)*
