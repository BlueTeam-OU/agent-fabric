---
role: "python-dev"
class: solution
topic: "herdr-fork-strategy"
description: "before any work on herdr or its remotes — upstream is closed to non-contributors; we work in our fork and take upstream's work in without overturning ours"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 664d2fdef2befb3b
---

## before any work on herdr or its remotes — upstream is closed to non-contributors; we work in our fork and take upstream's work in without overturning ours

The owner's word, 2026-10-07: herdr's upstream is closed to
non-contributors. We keep our own fork. When upstream has new work, we
take it in, but we never overturn our own branch's work to do so: no
reset onto upstream, and no rebase that rewrites our commits. Upstream
comes in as a merge on top of ours. herdr's default branch is master,
which j42 (fabric-branches resolving the remote's default branch) was
written for.

**Why:** we cannot land anything upstream, so our fork is where our work
lives. A rewrite toward upstream would lose it or rewrite its history.
**How to apply:** in herdr, origin is our fork. Upstream is a second
remote, fetched and merged, never pushed to, and our branches are never
reset to it. A tool that counts or sweeps against the "default branch"
must read origin's (our fork's), never upstream's. See
[[contributor-merge-direction]].

*References: contributor-merge-direction*

*Observed 2026-10-07 (python-dev)*
