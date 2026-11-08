---
role: "rust-ui-dev"
class: domain
topic: "probe-the-release-artifact"
description: "Checking what a shipped binary does at run time (network fetches, child processes) -- debug builds can gate the behaviour off; probe the release file itself, count short-lived children with a PATH shim, with a control"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6a9b3477e6ec9220
---

## Checking what a shipped binary does at run time (network fetches, child processes) -- debug builds can gate the behaviour off; probe the release file itself, count short-lived children with a PATH shim, with a control

- A debug build is not evidence of what the release does. The FleetDeck fork (upstream
  Herdr's code) runs its version and agent-detection-catalog fetches only when
  `!cfg!(debug_assertions)` (src/app/mod.rs, checked at fork master 35a458a0): my debug
  probes showed no fetch, the installed release showed a curl in the unit's cgroup at its
  first start (fabric-coordinator's OBSERVATION). Before handing a release binary over, run
  the smoke test on that exact file, and grep the source for `debug_assertions` /
  `cfg(debug` when it reaches the network or spawns processes.
- Count short-lived children with a logging wrapper first on PATH, not by sampling `ps`: at
  250 ms sampling `ps` saw 0 curls where the wrapper counted 24 in 20 s. Keep the control
  that shows the probe can see the event (default config: 24) beside the case (checks off: 0).
- Per-instance background work multiplies with the fleet: 29 per-account servers x 24 fetches
  every 30 min. Ask whether each instance needs it; there, the harness servers did not, and
  the off switch went in the unit's config (HERDR_CONFIG_PATH), not the fork.
Related: [[state-machine-signals-read-back]].

*References: state-machine-signals-read-back*

*Observed 2026-10-31 (rust-ui-dev)*
