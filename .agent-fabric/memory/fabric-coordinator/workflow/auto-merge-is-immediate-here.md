---
role: "fabric-coordinator"
class: workflow
topic: "auto-merge-is-immediate-here"
description: "agent-fabric main requires a PR, signed commits, ci-ok and fabric/armed; a hand merge posts fabric/armed first; a push disarms unless the head carries it"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2c3a7b120035055d
  - 479fda2843f05028
  - 65808d24fdb6a959
  - 9d370610e7c72ea0
---

## agent-fabric main requires a PR, signed commits, ci-ok and fabric/armed; a hand merge posts fabric/armed first; a push disarms unless the head carries it

Since #454 (2026-11-01, audit F02, ADR-019 A 2026-11-01), main's ruleset (tools/fabric/github-ruleset-main.json,
applied by `bin/fabric-repo-settings` and `fabric-repo-policy apply`) requires a PR, signed commits and TWO status
checks: `ci-ok`, the aggregate of the CI legs, and `fabric/armed`. `fabric-pr arm` posts `fabric/armed` (state
success) on exactly the sha its gates read, before `gh pr merge --auto --merge --match-head-commit`. That ties the
arming to that head on GitHub's side. Every mode-auto repository's ruleset carries it, through the arming policy's
`armed_status` (fabric/armed or null), never through `required_checks`.

A push after the arming takes auto-merge off unless the PR's current head carries fabric/armed
(`.github/workflows/disarm-on-push.yml` comments on the PR). Re-arm through the gate after a push.

A merge made outside `fabric-pr arm` waits on the status. That covers a Dependabot pin bump merged by hand, and the
owner's merge in the UI. Post the status on the head being merged first:
`gh api repos/<o>/<r>/statuses/<sha> -f context=fabric/armed -f state=success -f description=...`.
A PR armed before its repository's ruleset carried the check waits too: arm it again.

The older lesson still stands: "armed" must mean "merged when green". Read the gate first with
`fabric-pr gate <n>` (no open P1/P2, review on the head) and arm only on MERGEABLE, in a separate step.
Related: [[arm-auto-merge-false-failure]].

*References: arm-auto-merge-false-failure*

*Anchors: `tools/fabric/github-ruleset-main.json::fabric/armed`, `tools/fabric/github/arm_policy.py::ARMED_STATUS`*

*Observed 2026-11-01 (fabric-coordinator)*
