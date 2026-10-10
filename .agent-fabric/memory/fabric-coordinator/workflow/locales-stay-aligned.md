---
role: "fabric-coordinator"
class: workflow
topic: "locales-stay-aligned"
description: "The owner's rule (2026-10-07) that every language-culture locale carries every translation another locale has; ge must match ru"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 877b9f7b4198c69f
---

## The owner's rule (2026-10-07) that every language-culture locale carries every translation another locale has; ge must match ru

The owner, 2026-10-07: "georgian agent should align with all translations that ru already do, this have to stay aligned." A translation added to one locale under identities/roles/language-culture/locale/ is requested of every other locale in the same round. Each holder keeps its files current with the English source.

**Why:** ge had no ka-GE.json (the GZCoord tool strings) while ru had ru-RU.json, and nobody had noticed. A Georgian session saw the tools in English.

**How to apply:** when I ask one locale holder for a translation, send the same request to the others. The lint rule added in the carried-105 PR enforces equal file sets per locale and equal keys against en-US.json. Remember [[locale-suffixes]]: ge is Georgian, ka-GE its tag.

*References: locale-suffixes*

*Observed 2026-10-07 (fabric-coordinator)*
