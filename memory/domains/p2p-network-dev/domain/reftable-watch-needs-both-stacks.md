---
role: "p2p-network-dev"
class: domain
topic: "reftable-watch-needs-both-stacks"
description: "A build script watching git refs must watch <git-dir>/reftable and <common-dir>/reftable; only a linked-worktree case tells them apart"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 8bd007f40c0f9122
---

## A build script watching git refs must watch <git-dir>/reftable and <common-dir>/reftable; only a linked-worktree case tells them apart

A reftable repository (`git init --ref-format=reftable`) has no logs/HEAD,
no loose ref, no packed-refs, and HEAD is a stub no move touches; every ref
and reflog update writes a table under `reftable/`. The shared refs live in
the common directory's stack, a linked worktree's HEAD in its own git-dir's
(`--git-path reftable` names only the worktree's). In a main checkout the
two are one directory, so a test there proves neither watch is needed apart:
the case that needs the common dir is a worktree's checked-out branch moved
from the main checkout (`update-ref`), and the one that needs the git-dir is
a checkout in the worktree. Measured on PR #399 (j116, tools/stamp/commit_stamp.rs,
tools/ci/test_commit_stamp.sh): each watch dropped fails its case.
Building a reftable test repo here needs `commit.gpgsign=false` (the host's
gpg wrapper refuses an empty tree).

*Observed 2026-10-23 (p2p-network-dev)*
