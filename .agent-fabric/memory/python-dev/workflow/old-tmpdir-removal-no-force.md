---
role: "python-dev"
class: workflow
topic: "old-tmpdir-removal-no-force"
description: "removing the pre-#292 /var/tmp/agent-fabric-<login> — git worktree remove without --force per review head, then prune, then rm; the classifier refuses --force"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 85c0b1d908a106bf
---

## removing the pre-#292 /var/tmp/agent-fabric-<login> — git worktree remove without --force per review head, then prune, then rm; the classifier refuses --force

j65 (2026-10-19): the auto-mode entry from #309 allows `git worktree remove <path>` for the review heads under
`/var/tmp/agent-fabric-<login>/fabric-review/` and never `--force`; my first attempt with `--force` was refused
as irreversible destruction. Without it all 7 heads removed cleanly (rc=0), then `git worktree prune`, then
the directory (199M measured before). Move kept helpers (cienv.sh) to `~/.local/share/agent-fabric-python-dev/` first.

**Why:** the entry is keyed to use and to the non-force form; git itself refuses a head with changes.
**How to apply:** run the plain form per head from the clone it came from; if git refuses one, report it, never force. See [[ci-env-for-lint-and-mutations]].

*References: ci-env-for-lint-and-mutations*

*Observed 2026-10-19 (python-dev)*
