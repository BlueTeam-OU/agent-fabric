---
role: "fabric-coordinator"
class: workflow
topic: "auto-mode-refuses-fleet-upgrade"
description: "fabric-ctl all upgrade fabric, run wrapped (timeout … | tail), was refused by auto mode as Modify Shared Resources; the owner ran it with ! and all 30 accounts upgraded"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 27842c4768f93661
---

## fabric-ctl all upgrade fabric, run wrapped (timeout … | tail), was refused by auto mode as Modify Shared Resources; the owner ran it with ! and all 30 accounts upgraded

2026-11-05, after #488 merged: `timeout 900 fabric-ctl all upgrade fabric 2>&1 | tail -30` was refused by the auto-mode classifier as [Modify Shared Resources]. I did not retry in another form; the owner ran `! fabric-ctl all upgrade fabric` and every account went fd10a755/75f071d3 → fe13e35b (control agents restart after the reply; sessions take it at next launch).

**Why:** the fleet upgrade touches every account, and a wrapped command goes to the classifier instead of matching a `Bash(fabric-ctl *)` allow rule. The bare form was not tried that day. 2026-11-08 (j636, #504/#505): bare `fabric-ctl all upgrade fabric` PASSED auto mode, 30 accounts → f1e29bd8; read-back `fabric-ctl python-dev-01 status` showed the fabric column.

**How to apply:** after a merge, run `fabric-ctl all upgrade fabric` bare, with no timeout, pipe or redirect. If it is refused, hand the owner the one-line `!` command at once and read the account table it prints back. See [[auto-mode-refuses-account-assign]] and [[post-review-run-bare]].

*References: auto-mode-refuses-account-assign, post-review-run-bare*

*Anchors: `policies/auto-mode.json::fabric-ctl`*

*Observed 2026-11-08 (fabric-coordinator)*
