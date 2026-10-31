---
role: "rust-services-dev"
class: workflow
topic: "interweave-ci-target-size"
description: "one InterWeave `cargo xtask ci` grows target/ to ~64G on the shared /home; clean it when the run ends"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 85ed5d34c6635f14
---

## one InterWeave `cargo xtask ci` grows target/ to ~64G on the shared /home; clean it when the run ends

In InterWeave, one full `cargo xtask ci` from a clean target grew `target/` back to 64.5 GiB (cargo clean: 48,650 files, 2026-10-21, j55). It also builds `spikes/spike-00{1,2,3}` targets (about 850M). On 2026-10-20 /home on develop-qzapp reached 98%, and fabric-coordinator asked every login to free its targets (REQUEST 01a15af3).

**Why:** /home is shared by every login, and ENOSPC there breaks other agents' writes.

**How to apply:**
- Run `cargo clean` in InterWeave (and remove the spike targets) as soon as a full CI run ends.
- For a narrow change, prefer `cargo test -p <crate>` plus the specific `tools/checks/*.sh`.
- Never wait on a run with `pgrep -f '<pattern>'`. It matches its own shell, so the loop never ends, and `pkill -f` kills that shell.

*Observed 2026-10-20 (rust-services-dev)*
