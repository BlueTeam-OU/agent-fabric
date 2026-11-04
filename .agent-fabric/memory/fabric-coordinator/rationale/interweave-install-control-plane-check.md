---
role: "fabric-coordinator"
class: rationale
topic: "interweave-install-control-plane-check"
description: "Owner 2026-10-25 — any InterWeave install/update must restart its units and be checked over the control plane after; never leave an agent invisible"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - "156326052e162411"
---

## Owner 2026-10-25 — any InterWeave install/update must restart its units and be checked over the control plane after; never leave an agent invisible

The owner, 2026-10-25: an install or update of InterWeave takes the agent's
channel down; if it goes wrong the agent becomes "invisible", so a
control-plane check after the restart is required.

**Why:** the archive's install.sh enables nothing and running units keep
the old binaries; the restart is the moment the channel drops, and only the
control plane (on the relay, ADR-064 rule 12) still reaches the account.

**How to apply:** written as ADR-064 §5 rule 14 (commit edf84189, j401
branch). Every install path (fabric-ctl interweave-install, j168 by
python-dev-01) restarts what was running, checks units/version/carrier
status, restores the previous programs on failure. After any fleet
restart, read `fabric-ctl all interweave` before claiming the channel is up.
Related: [[settings-pin-vs-runtime-default]], [[launch-time-change-needs-relaunch]].

*References: launch-time-change-needs-relaunch, settings-pin-vs-runtime-default*

*Observed 2026-10-25 (fabric-coordinator)*
