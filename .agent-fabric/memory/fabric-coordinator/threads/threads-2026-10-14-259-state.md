---
role: "fabric-coordinator"
class: threads
topic: "threads-2026-10-14-259-state"
description: "A re-review brief rendered by the fabric-review on PATH uses main's code (no dispatch header, no card): render a PR's brief with the PR worktree's own bin/; and the order before arming a security-boundary PR"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bd1ce619d8ccfbf9
---

## A re-review brief rendered by the fabric-review on PATH uses main's code (no dispatch header, no card): render a PR's brief with the PR worktree's own bin/; and the order before arming a security-boundary PR

At the owner's request (2026-10-14) the coordinator session left the API key (claude-pzhuy, credit probe in [[api-key-credit-coordinator-only]]) and returns to the setup-token account.

#259 (16 work, 10 fix, 4 merge by `fabric-pr gate` before the last push): branch develop-qzapp/user/feat/review-economics-p1, head 9a739f49 (devex's aca0b084 folded and an ADR-020 rule 10 sentence added after 271c5f63; main merged in; folds python-dev-01's for/user/p1-ledger-review-fix and devex-tooling's for/user/post-review-fence unrebased onto my five round-1 fixes). Local suite on the fold: python red only on test_fabric_fresh_git (branch behind main, fixed by the merge) and test_control_agentd (timing flake under load); both pass alone on 271c5f63; bash suite passed. CI on 9a739f49 not yet read; the full python suite not rerun after the last two folds.

**Remains, in order:** CI green on the head; one re-review of 88270bcb..271c5f63 posted with `fabric-pr post-review 259 --model fable` (the arm refuses a security-boundary PR without a review of the current head); then the owner's arm (already said "arm 259", 2026-10-14 — it stays refused until the review exists). The round-2 brief at ~/.cache/claude-tmp/rr259.md is for the OLDER head 271c5f63 and must be re-rendered for 9a739f49 (git worktree ~/.cache/claude-tmp/fold259, run its)  the FOLD TREE's own `./bin/fabric-review next` (the one on PATH renders main's code: no dispatch header, no card; do not use it). Dispatch it verbatim as Agent(subagent_type: code-review, model: fable, no isolation); `fabric-review save 259 2` keeps the report. The request chain is under .../scratchpad/rev259/ (request-rr3.json); if that is gone, rebuild from round 1.

**Why:** a dispatch from a session on main's code produces a brief the reviewer cannot judge (round 1 said so). **How to apply:** render with the worktree's bin/, check the first line is the ```agent-fabric-dispatch v1 block.

*References: api-key-credit-coordinator-only*

*Observed 2026-10-14 (fabric-coordinator)*
