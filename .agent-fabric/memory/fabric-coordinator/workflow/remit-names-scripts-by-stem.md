---
role: "fabric-coordinator"
class: workflow
topic: "remit-names-scripts-by-stem"
description: "when writing a project's remit, name its scripts by stem and language once, not by file extension, so a port does not stale it"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 39c37f7feba1d906
---

## when writing a project's remit, name its scripts by stem and language once, not by file extension, so a port does not stale it

gzapp.decks #30 (merged 732b91c) ported scripts/*.mjs to Python; the brand-comms remit (.agent-fabric/roles/brand-comms.md:19) still named `deckmeta.mjs` and missed `doc` entirely until commit a4dca798 on PR #29 (job j302).

**Why:** a remit is read by the role every session; a wrong filename sends it looking for a file that is gone, and nobody but fabric-coordinator may fix it.
**How to apply:** in a remit, list scripts by stem with the language stated once ("Python: build, doc, bump…"); when a project's PR renames or ports files a remit cites, grep `.agent-fabric/roles/` in the same pass.

*Observed 2026-10-23 (fabric-coordinator)*
