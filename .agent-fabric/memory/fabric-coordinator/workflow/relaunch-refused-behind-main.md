---
role: "fabric-coordinator"
class: workflow
topic: "relaunch-refused-behind-main"
description: "An agent's pane says 'RESTART NOT COMPLETED … N commit(s) behind origin/main and cannot fast-forward': fabric-ctl <login> upgrade fabric, then fabric-resume at its shell and fabric-fresh --job inside the session"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a28cb99eb3692698
---

## An agent's pane says 'RESTART NOT COMPLETED … N commit(s) behind origin/main and cannot fast-forward': fabric-ctl <login> upgrade fabric, then fabric-resume at its shell and fabric-fresh --job inside the session

2026-11-09, python-dev-03 finishing j672 for j120: the launcher refused the fresh relaunch, "agent-fabric … is 9
commit(s) behind origin/main and cannot fast-forward (local commits or changes)". Its control agent reported the
checkout clean at 426ab783, a commit on origin/main. `fabric-ctl python-dev-03 upgrade fabric` moved it to the
current main at once. Most of the fleet sat at the same 426ab783, so the refusal may hit any of them (j695).

Reading another account's checkout directly (`git -C /home/<login>/…`) is refused by auto mode; ask its control
agent (`fabric-ctl <login> status` fabric column, `branches`) instead.

`fabric-fresh --job <j>` typed at the bare shell is refused ("not started by the launcher … use /clear"), although
the pane's own text says to run it there (j696). The route that works is `fabric-resume` at the shell, then
`fabric-fresh --job <j>` inside that session.

**Why:** the pane's instruction leads the owner into a second refusal; the control-plane upgrade is the fix I can run.
**How to apply:** upgrade the one account first, then give the owner the two steps. Related: [[stuck-agent-read-its-pane]],
[[holder-checkout-back-to-main]].

*References: holder-checkout-back-to-main, stuck-agent-read-its-pane*

*Anchors: `tools/fabric/launch.py::RESTART NOT COMPLETED`, `tools/fabric/fresh.py::--job`*

*Observed 2026-11-09 (fabric-coordinator)*
