---
role: "flutter-dev"
class: workflow
topic: "merge-target-replaces-it-never-deletes"
description: A memory with merge_target and no body does not retire a slice section — the drain only replaces a section with the correcting text, and an unmatched target is filed as an empty topic of its own
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 708711003ef1a566
---

## A memory with merge_target and no body does not retire a slice section — the drain only replaces a section with the correcting text, and an unmatched target is filed as an empty topic of its own

`merge_target` is a correction instrument, not a delete: the assembler puts the
correcting memory's own heading and text in the named section's place. Two
body-less "retire" memories of mine (meant to remove agent-fabric copies of
claims that had moved to gzapp's corpus) matched no `##` heading and came back
on the 2026-11-08 drain under `merge_target_unresolved`, each filed as an empty
topic — and they would have come back on every drain.

**Why:** the drain cannot tell "never matched" from "already replaced"
(memory/README.md, "When a slice is wrong"), and it has no way to drop a
section on an empty claim.

**How to apply:** to correct a section, write the corrected claim with
`merge_target` set to the slice's `##` heading exactly as it reads now on
origin/main. A section that should simply go — a duplicate, a claim that moved
to another project's corpus — is asked of fabric-coordinator by message, not
written as a memory. When the drain names a memory as unresolved, check the
slice on origin/main: section gone → delete the memory; section there →
retarget to its current heading. See [[a-memory-lives-with-the-project-it-describes]].

*References: a-memory-lives-with-the-project-it-describes*

*Anchors: `agent-fabric:memory/README.md::merge_target_unresolved`*

*Observed 2026-11-09 (flutter-dev)*
