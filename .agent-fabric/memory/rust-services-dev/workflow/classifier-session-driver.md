---
role: "rust-services-dev"
class: workflow
topic: "classifier-session-driver"
description: "Auto mode refuses a script that launches claude sessions with dev-channel flags, even after the owner says yes in chat; it needs allow rules"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 95a11924fa2ff50d
---

## Auto mode refuses a script that launches claude sessions with dev-channel flags, even after the owner says yes in chat; it needs allow rules

On 2026-10-20 (InterWeave j36, SPIKE-001 S19) the auto-mode classifier refused twice to let me write
spikes/spike-001/s19_channels.py. That driver launches `claude` sessions with
`--dangerously-load-development-channels` / `--channels`, pre-seeds a scratch CLAUDE_CONFIG_DIR and
answers the development warning. The refusals were "Safety Bypass Flag" and then, after the owner
answered "1" (allow) in chat, "Create Unsafe Agents".

**Why:** an owner's yes in the conversation does not change the classifier's verdict. Only a permission
allow rule does (/permissions, or policies/auto-mode.json through fabric-coordinator), or the owner
running the sessions by hand.

**How to apply:** when a measurement needs nested claude sessions with a dangerous flag, do not draft the
driver first. Ask the owner for the exact allow rules, or for a hand run, before writing anything. Never
work around a refusal.

**The ask for an allow entry** goes to fabric-coordinator (policies/auto-mode.json is its file). The entry is
classifier prose, so the ask names:
- each refused call: the tool, the exact path or command, and the refusal text;
- what the driver does, step by step, and nothing more. The entry covers the file only while it does exactly
  that;
- its one credential and where it comes from (a child environment carrying no other);
- its end condition, which names the job.
Ask in this shape once and the scope is usually taken whole (the s19 entry, #353; the j41 ask, 0774b0af).
- **When it reaches me:** only after the PR merges, then `fabric-ctl all upgrade fabric`, then a relaunch.
  Until then, write nothing the entry covers.
- **When the job ends,** or its run is dropped, tell fabric-coordinator to remove the entry or withdraw the ask.
- **Keep the job id stable.** A job added without a working copy is refused by `fabric-jobs switch`, and
  re-adding it under a new id breaks an entry that names the old one (j36 became j39). Give every job its
  working copy when it is added.

*Observed 2026-10-22 (rust-services-dev)*
