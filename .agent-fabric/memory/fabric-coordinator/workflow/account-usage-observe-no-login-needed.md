---
role: "fabric-coordinator"
class: workflow
topic: "account-usage-observe-no-login-needed"
description: "an account no login runs on still has a readable weekly window: fabric-accounts observe (dry), not fabric-usage or the switch state"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ae8219f0bed7be5f
---

## an account no login runs on still has a readable weekly window: fabric-accounts observe (dry), not fabric-usage or the switch state

2026-11-09: asked how much weekly allowance was left on the CEO's account, an account no login ran on. I answered
"cannot be read without a login on it" from `fabric-usage` (rows per login) and the switch controller's kept probe (taken through a
login), and the owner corrected me: `fabric-accounts observe` reads every template's account directly (seven_day utilization,
resets_at, weekly_reset weekday/time, overage). Without `--write` it is dry and changes nothing; with `--write` it stores the
reading under "observed" in settings/accounts/<slug>.json in the coordinator's store.

**Why:** fabric-usage and fabric-ctl status read per login, so an unused account is invisible to them.
**How to apply:** for any account's weekly allowance, run `fabric-accounts observe` first; `fabric-accounts read` only covers
the coordinator's own sign-in. Related: [[auto-mode-refuses-account-assign]].

*References: auto-mode-refuses-account-assign*

*Anchors: `bin/fabric-accounts`, `tools/fabric/control/accounts.py`*

*Observed 2026-11-09 (fabric-coordinator)*
