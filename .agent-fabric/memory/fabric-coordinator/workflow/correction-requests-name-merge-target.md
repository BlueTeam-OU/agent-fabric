---
role: "fabric-coordinator"
class: workflow
topic: "correction-requests-name-merge-target"
description: "When asking an agent for a correction memory, say merge_target or \"fix the source memory\" — a bare correction lands as a separate slice beside the stale one"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0135cb821a7db6ca
---

## When asking an agent for a correction memory, say merge_target or "fix the source memory" — a bare correction lands as a separate slice beside the stale one

A correction memory replaces a stale slice section only when its
`metadata:` carries `merge_target: "<the section's heading>"`
(memory/README.md "The drain cycle", ADR-014 rule 7). On 2026-09-28 I
asked five authors for correction memories without saying so; the
gzapp drain filed each as its own slice beside the stale one, and two
stale citations stayed. I discarded the run and re-asked.

**Why:** memory/README.md's "the next drain merges it" reads as automatic;
it is not without merge_target.

**How to apply:** a correction request names the choice: correct the
source memory the slice was drained from and delete nothing else, or
write a correction carrying merge_target with the stale section's
heading. Check a drain's untracked files for new `correction-*` slices
before committing it.

*Observed 2026-09-28 (fabric-coordinator)*
