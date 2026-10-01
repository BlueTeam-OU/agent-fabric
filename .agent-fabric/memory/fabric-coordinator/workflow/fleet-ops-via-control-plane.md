---
role: "fabric-coordinator"
class: workflow
topic: "fleet-ops-via-control-plane"
description: "An operation on accounts (move Claude account, sync, verify, restart) goes through signed control-plane messages, never hostexec/sudo per login — build the action if it is missing"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - 41a1a42f00b22ded
---

## An operation on accounts (move Claude account, sync, verify, restart) goes through signed control-plane messages, never hostexec/sudo per login — build the action if it is missing

On 2026-09-25 I moved eleven logins to another Claude account and, because
the `secrets-sync` action was still unmerged, ran `fabric-secrets sync` and
a fingerprint check per login through `runtime/hostexec`. The owner: "this
process must be fully done by control plane via message."

**Why:** the control plane is the fabric's way to act on accounts: signed,
replayable-safe, answered per account with its own verdict. A hostexec loop
is the coordinator reaching into every login with sudo, and its checks are
the coordinator's, not the account's.

**How to apply:** when a fleet operation has no action yet, the missing
action is the work — add it (signed op, verification in the reply, exit 1
on any row not ok) rather than looping hostexec. hostexec stays the
fallback for a host whose daemons are down, and for distribution
([[distribute-after-merge]]). For account moves: `fabric-accounts assign`
sends `secrets-sync --expect <template sha12> --restart` (branch
develop-qzapp/user/account-assign, commit df4b53c).

*References: distribute-after-merge*

*Observed 2026-09-25 (fabric-coordinator)*
