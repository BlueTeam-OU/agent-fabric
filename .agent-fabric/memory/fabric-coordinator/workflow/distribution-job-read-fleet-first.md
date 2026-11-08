---
role: "fabric-coordinator"
class: workflow
topic: "distribution-job-read-fleet-first"
description: "a queued [distribution] job may already be met by a later merge's upgrade: read fabric-ctl all status's fabric column against origin/main before running fabric-ctl all upgrade fabric"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e5135d3c80729ee1
---

## a queued [distribution] job may already be met by a later merge's upgrade: read fabric-ctl all status's fabric column against origin/main before running fabric-ctl all upgrade fabric

j561 (2026-11-07): queued since #461 merged 11-03, taken four days later. `fabric-ctl all status` already showed 30/30 accounts on 2a374df4 = origin/main head, which contains #461's 8178f358 (`git merge-base --is-ancestor`). A later upgrade had carried it, so no upgrade was run.

The nightly half: `gh run list --workflow stripped-nightly.yml`. A `success` conclusion is enough evidence for "green apart from its listed reds". The run fails on an unlisted red and also on a listed file that now passes (header of .github/workflows/stripped-nightly.yml). The `red, listed — jNN` lines in `gh run view <id> --log` name what is still listed.

**How to apply:** for a distribution job, compare the fabric column with `git log -1 origin/main` first. Upgrade only when an account is behind, and run it bare ([[auto-mode-refuses-fleet-upgrade]]). The "managed DRIFTED" column is the root-installed settings snapshot (the [[adr-043-managed-settings-option-1]] / j509 track). It is not a distribution failure.

*References: adr-043-managed-settings-option-1, auto-mode-refuses-fleet-upgrade*

*Observed 2026-11-07 (fabric-coordinator)*
