---
role: "fabric-coordinator"
class: workflow
topic: "auto-merge-is-immediate-here"
description: "agent-fabric main requires a PR, signed commits and the single check ci-ok; auto-merge waits for it; a push disarms it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2c3a7b120035055d
  - 479fda2843f05028
  - 65808d24fdb6a959
---

## agent-fabric main requires a PR, signed commits and the single check ci-ok; auto-merge waits for it; a push disarms it

Main has a ruleset (tools/fabric/github-ruleset-main.json, applied by `bin/fabric-repo-settings`; ADR-019): a PR, signed commits and ONE required status check, `ci-ok`, the aggregate of the legs. `gh pr merge --auto --merge` waits for it. A push after the arming takes auto-merge off (`.github/workflows/disarm-on-push.yml` comments on the PR), so re-arm after a push.

Before the ruleset (2026-09-29) an armed PR merged at once with checks pending, green only by luck. The lesson that stays: "armed" must mean "merged when green", so read the gate first with `fabric-pr gate <n>` (no open P1/P2, review on the head) and arm only on MERGEABLE, in a separate step after reading it. See [[check-exit-status-not-pipe]].

*References: check-exit-status-not-pipe*

*Observed 2026-10-10 (fabric-coordinator)*
