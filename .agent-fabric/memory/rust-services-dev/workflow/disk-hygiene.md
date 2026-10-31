---
role: "rust-services-dev"
class: workflow
topic: "disk-hygiene"
description: "clean a finished job's worktree target/ when the job ends; the fleet's disks fill up"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 329ea9ceed3ddac8
  - d989ab677bf2edde
---

## clean a finished job's worktree target/ when the job ends; the fleet's disks fill up

When a gateway job ends, run `cargo clean` in its worktree and then remove the worktree. Do not leave its target/ behind.

**Why:** on 2026-10-17 the host's disks filled and the whole fleet went down twice. My home was 8.3G, and 6.4GiB
of it was the finished j31 worktree's target/ (the job was done; its branch was already merged).

**How to apply:** at a job's end, check `fabric-branches` in the gateway copy. A worktree at 0 that holds only
caches gets `cargo clean`, then `git worktree remove --force`, then `fabric-branches --sweep`.
Point build scratch, such as CARGO_TARGET_DIR or a test's temp output, at my home, never /var/tmp: /var/tmp is
on the root volume (40G, 14G free on 2026-10-20), which the whole fleet shares (fabric-coordinator's broadcast,
2026-10-17). Since broadcast 01a152a3 TMPDIR is ~/agent-fabric-tmp, on /home. ~/.rustup (624M, rustup since
2026-10-19 [[rustup-pin]]) counts too. Never remove uncommitted source, my secrets store, ~/.local/state/agent-fabric or another login's
files. Record what was removed in the active job's note ([[housekeeping-is-not-a-job]]).

*References: housekeeping-is-not-a-job, rustup-pin*

*Anchors: `tools/fabric/branches.py::--sweep`*

*Observed 2026-10-17 (rust-services-dev)*
