---
role: "fabric-coordinator"
class: workflow
topic: "agents-clean-stale-things"
description: "Owner 2026-10-19: every agent clears out its own stale worktrees, branches and scratch, not only me; broadcast 01a15576 is the interim, a fabric-branches/switch change the durable form"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cf8c60035b30f818
---

## Owner 2026-10-19: every agent clears out its own stale worktrees, branches and scratch, not only me; broadcast 01a15576 is the interim, a fabric-branches/switch change the durable form

2026-10-19, after I removed 39 leftover worktrees of my own login (review heads in /var/tmp and
~/agent-fabric-tmp, drain and job checkouts across nine repositories, 530 MB), the owner said:
"you should tell also agents to do clean out of old stale things". I broadcast the procedure
(INFO 01a15576: `fabric-branches --sweep` per working copy, then by hand the clean worktrees whose
HEAD is pushed, review heads once saved, own scratch measured and said) and queued the durable
change for myself.

**Why:** `fabric-branches --sweep` (ADR-022) removes only worktrees whose commit is on the default
branch, so pushed-but-unmerged drains, job checkouts and review heads pile up on every account.

**How to apply:** clean my own after each job ends, not in a batch weeks later; check each
worktree for changes and unpushed commits before removing it, and never touch another login's.
A cleanup that lives only in a broadcast is lost — the sweep/switch change is the rule's real form.
Related: [[tmpdir-in-home-2026-10-17]], [[own-checkout-is-fleet-tooling]].

*References: own-checkout-is-fleet-tooling, tmpdir-in-home-2026-10-17*

*Anchors: `bin/fabric-branches::--sweep`*

*Observed 2026-10-19 (fabric-coordinator)*
