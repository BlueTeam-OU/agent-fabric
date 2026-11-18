---
role: "python-dev"
class: solution
topic: "j154-rustup-role-list-closed"
description: "j154 rustup on develop-qzapp/user — role list in projects/registry.json suffices; non-operators cannot run fabric-ctl all; hygiene round traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 545b9ff8c4c40162
---

## j154 rustup on develop-qzapp/user — role list in projects/registry.json suffices; non-operators cannot run fabric-ctl all; hygiene round traps

j154 (2026-11-16) closed with no branch. `fabric-ctl all tools` refuses a non-operator login ("not a host operator"), and the classifier denies reading other accounts' homes, so a measurement comes from the operator's report. `tools_install.install()` places a pin only for an account with a working copy of a declaring project AND a bound role in that entry's `roles`; fabric-coordinator was in no rustup `roles` list, which is why user ran Fedora cargo 1.99.1. The coordinator edits `projects/registry.json` itself; no bootstrap hunk was needed.

**Why:** a role-list gap looks like a provisioning gap; read `install()` before building a step.
**How to apply:** for "tool X missing on account Y", check the registry `roles` first.

Hygiene round (2026-11-16): `fabric-branches --sweep` kept ~25 clean merged worktrees ("ignored paths"); `git worktree remove` without `--force` removed them. A dirty one whose diff is already on main is discarded with `git checkout -- <file>` then removed; a dirty one whose lines are not on main is kept and named. Pin the PR counts ("#N (W work, F fix)") whenever a status of a PR is stated, or the stop hook refuses. See [[old-tmpdir-removal-no-force]].

*References: old-tmpdir-removal-no-force*

*Anchors: `tools/fabric/tools_install.py::wanted`, `projects/registry.json::rustup`*

*Observed 2026-11-16 (python-dev)*
