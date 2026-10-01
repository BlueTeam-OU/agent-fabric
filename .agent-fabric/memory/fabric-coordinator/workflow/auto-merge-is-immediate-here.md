---
role: "fabric-coordinator"
class: workflow
topic: "auto-merge-is-immediate-here"
description: "on agent-fabric, `gh pr merge --auto` merges at once while CI is still pending, because no check is required by branch protection; arm only after CI is green"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 479fda2843f05028
---

## on agent-fabric, `gh pr merge --auto` merges at once while CI is still pending, because no check is required by branch protection; arm only after CI is green

On 2026-09-29, #64 was armed with `gh pr merge 64 --auto --merge` while the four `guards-and-suites` jobs were still pending. It merged at once (046c3a4, 14:57:35Z), because agent-fabric's branch protection requires no status check, so auto-merge has nothing to wait for. CI later finished green, but only by luck.

**Why:** the fabric's rule is to arm on MERGEABLE, and `pr-gate.sh` read "BLOCKED: 6 check(s) pending". On this repository, "armed" and "merged" are the same act.

**How to apply:**
- On agent-fabric, wait for every check to be green (`gh run watch <id> --exit-status`, or the gate reading MERGEABLE) BEFORE `gh pr merge`.
- Never arm on "only checks pending".
- Or propose to the owner making `guards-and-suites` a required check, so that `--auto` waits as its name suggests.

See [[check-exit-status-not-pipe]] and [[arm-in-band-on-my-own]].

*References: arm-in-band-on-my-own, check-exit-status-not-pipe*

*Observed 2026-09-29 (fabric-coordinator)*
