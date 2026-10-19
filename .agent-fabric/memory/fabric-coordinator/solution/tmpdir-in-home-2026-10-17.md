---
role: "fabric-coordinator"
class: solution
topic: "tmpdir-in-home-2026-10-17"
description: "Launcher TMPDIR is ~/agent-fabric-tmp (on /rw), pruned weekly; /var/tmp on the Qubes root volume filled and crashed the fleet"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1c0ae3bb10e4529f
---

## Launcher TMPDIR is ~/agent-fabric-tmp (on /rw), pruned weekly; /var/tmp on the Qubes root volume filled and crashed the fleet

Since #292 (merged 2026-10-18, main 5b6923aa) the launcher's default TMPDIR is
`~/agent-fabric-tmp`, mode 700, pruned at each launch of top-level entries
untouched for 7 days (max of mtime and ctime; symlinks removed as themselves,
never walked). An account-set TMPDIR wins and is never pruned. It is not under
`~/.cache`, because review_codex.scratch_root and review-bash-guard HOME_PATH
both refuse a home's hidden directories.

**Why:** on a Qubes AppVM the root volume (40G, holds /var/tmp) is small and
reset at reboot; the old /var/tmp/agent-fabric-<login> filled it on
2026-10-17 and crashed every session. /rw (541G) holds /home.

**How to apply:** a running session keeps its old TMPDIR until relaunch.
python-dev's memory `ci-env-for-lint-and-mutations` still names the
/var/tmp path, so it needs correcting by its owner. Related:
[[trusted-base-orphaned-by-reset]].

*References: trusted-base-orphaned-by-reset*

*Anchors: `tools/fabric/launcher/session.py::settle_tmpdir`*

*Observed 2026-10-17 (fabric-coordinator)*
