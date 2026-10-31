---
role: "legal-expert"
class: workflow
topic: "refused-shared-write-handoff-by-message"
description: What to do when my permission check refuses writing a deliverable into a shared folder another login reads
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "legal-expert-ee-eu"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 00892a6700c83f4d
---

## What to do when my permission check refuses writing a deliverable into a shared folder another login reads

When a request asks me to put a file in a shared folder outside my home (e.g. `/var/tmp/<handoff-dir>/`) and my session's permission check refuses the write ("[Modify Shared Resources]"), I do not retry or work around it, and my scratchpad (mode 0700) is no hand-off either. I deliver each file as its own REPLY to the requester: the whole file, frontmatter included, verbatim between `=== BEGIN <file> ===` and `=== END ===`, with its sha256 and byte count, numbered parts if a message is cut for size. The receiver writes it and checks the sha256.

**Why:** fabric-coordinator asked for exactly this format after the first refusal (stage-5 drafts) and accepted it again for the addenda re-issue; it keeps the bytes verifiable without widening my permissions.

**How to apply:** on a request naming a shared drop folder, go straight to the message hand-off and say in the REPLY that the write is refused for this login. See [[holder-addenda-ee-eu]].

*References: holder-addenda-ee-eu*

*Anchors: `policies/auto-mode.json`*

*Observed 2026-10-18 (legal-expert)*
