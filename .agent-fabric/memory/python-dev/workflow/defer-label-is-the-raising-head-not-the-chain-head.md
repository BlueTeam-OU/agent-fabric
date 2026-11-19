---
role: "python-dev"
class: workflow
topic: "defer-label-is-the-raising-head-not-the-chain-head"
description: "fabric-pr arm --defer wants <head8>:F<n> of the head that RAISED the finding; an earlier-round finding keeps its old head"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d384a62496fff06a
---

## fabric-pr arm --defer wants <head8>:F<n> of the head that RAISED the finding; an earlier-round finding keeps its old head

j102 / PR 524: arm refused with three open P3s listed as `6ab3e2f0:F3`, `dd3c4188:F5`, `dd3c4188:F6`. My first `--defer dd3c4188:F3` was
refused ("names no open finding"): F3 was raised in round 1 on 6ab3e2f0 and only its chain moved to the new head. Read the labels from the
refusal's own list, not from the head being armed. The owner's "arm N" word does not lift open findings; it lifts the count, so the P3s
are deferred by name with a reason in the same command.

Also: a fedora platform-smoke failure in an unrelated case (test_jobs_switch "held: next is switch", memory-directory check) passed on
`gh run rerun <run> --failed`; main's same job was green, so it is a flake until it repeats.

**Why:** two refused arms cost a round trip each.
**How to apply:** `fabric-pr arm N --dry-run --basis x` first, copy each `<head8>:F<n>` from its refusal into `--defer`.

*Observed 2026-11-09 (python-dev)*
