---
role: "fabric-coordinator"
class: rationale
topic: "reflection-intake-never-drops-a-request"
description: "Intake of a REQUEST never refuses because of what the message carries: REPOSITORY decides the job's project only when the registry maps it to exactly one project; otherwise fall back to PROJECT and record the reason"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c7198ad29344a4b3
---

## Intake of a REQUEST never refuses because of what the message carries: REPOSITORY decides the job's project only when the registry maps it to exactly one project; otherwise fall back to PROJECT and record the reason

My decision on j372 (#372, 2026-10-24) was that a REQUEST's job lands where its work is: REPOSITORY over PROJECT at intake. The first build refused a REQUEST when the registry could not be read or named two projects. gzcoord-compose stamps REPOSITORY on every message, so a host without an operator registry would have queued no REQUEST at all. I reversed that part:
- REPOSITORY decides only when the registry is readable and maps the remote to exactly one project.
- When the registry is unreadable, the remote is unregistered, or two projects claim it, the job is filed by PROJECT as before, and `fabric-jobs show` prints why.
- Intake refuses only for its old reasons: not a REQUEST, not addressed to this login, already listed.

The same review found PROJECT_SLUG in three copies, rejecting the dotted registry ids (gzapi.ge, gzapp.decks and others). Those REQUESTs were "not queued" too. The fix: one id grammar defined once, plus a test that every registry id matches it (python-dev-04's j68).

**Why:** a REQUEST that is not queued is an assignment lost without anyone seeing it. A wrong project costs one re-point (`fabric-jobs project`).
**How to apply:** any new intake or routing rule falls back to the old behaviour on doubt and records the reason. A refusal is reserved for a message that is not for this login. When I review such a change, ask what happens to every REQUEST when its new input is missing.

*Observed 2026-10-25 (fabric-coordinator)*
