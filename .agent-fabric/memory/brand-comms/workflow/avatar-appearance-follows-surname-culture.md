---
role: "brand-comms"
class: workflow
topic: "avatar-appearance-follows-surname-culture"
description: "ADR-056 avatars — the face is drawn from the surname's culture (the surnames.json `from`), not cast freely; the owner's ruling"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9d6bf726701a1e11
---

## ADR-056 avatars — the face is drawn from the surname's culture (the surnames.json `from`), not cast freely; the owner's ruling

An ADR-056 avatar's appearance follows the culture of the agent's surname (the `from` of its entry in identities/personas/surnames.json), the same culture rule 5 takes the first name from. Plausible for someone living in that country today; never a stereotype, a costume or the scientist's likeness.

**Why:** the owner, 2026-10-13, overruled a draft of the avatar style guide that cast faces freely "so the fleet is varied": a name from one culture on a face from another is cultural appropriation.

**How to apply:** before writing `{appearance}` for an avatar, read the agent's surname entry and choose features plausible for that culture; vary within it. Related: [[avatar-style-guide]].

*References: avatar-style-guide*

*Observed 2026-10-13 (brand-comms)*
