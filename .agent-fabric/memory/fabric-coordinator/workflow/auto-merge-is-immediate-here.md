---
role: "fabric-coordinator"
class: workflow
topic: "auto-merge-is-immediate-here"
description: "SUPERSEDED 2026-10-04: agent-fabric main now has a ruleset with required checks and auto-merge on, so `gh pr merge --auto` waits for green; still read the gate before arming"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2c3a7b120035055d
  - 479fda2843f05028
---

## SUPERSEDED 2026-10-04: agent-fabric main now has a ruleset with required checks and auto-merge on, so `gh pr merge --auto` waits for green; still read the gate before arming

On 2026-09-29, #64 was armed with `gh pr merge 64 --auto --merge` while the four `guards-and-suites` jobs were still pending. It merged at once (046c3a4, 14:57:35Z), because agent-fabric's branch protection requires no status check, so auto-merge has nothing to wait for. CI later finished green, but only by luck.

**Why:** the fabric's rule is to arm on MERGEABLE, and `pr-gate.sh` read "BLOCKED: 6 check(s) pending". On this repository, "armed" and "merged" are the same act.

**How to apply:**
- On agent-fabric, wait for every check to be green (`gh run watch <id> --exit-status`, or the gate reading MERGEABLE) BEFORE `gh pr merge`.
- Never arm on "only checks pending".
- Or propose to the owner making `guards-and-suites` a required check, so that `--auto` waits as its name suggests.

See [[check-exit-status-not-pipe]] and [[arm-in-band-on-my-own]].


**Superseded 2026-10-04.** The owner approved a ruleset on agent-fabric's main (tools/fabric/github-ruleset-main.json, applied by tools/fabric/github-repo-settings.sh; ADR-019 rule 6): a PR, 11 required CI checks and signed commits; auto-merge on. `gh pr merge --auto --merge` now waits for green. The gate is still read first (no open P1/P2, review on head).

*References: arm-in-band-on-my-own, check-exit-status-not-pipe*

*Observed 2026-09-29 (fabric-coordinator)*
