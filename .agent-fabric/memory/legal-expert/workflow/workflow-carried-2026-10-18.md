---
role: "legal-expert"
class: workflow
topic: "workflow-carried-2026-10-18"
description: Reading Swiss federal law from Fedlex needs a JavaScript browser; WebFetch gets only the splash screen, so without moli every Swiss citation goes out unverified
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "legal-expert-ch"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 71a457d8eaed17f3
---

## Reading Swiss federal law from Fedlex needs a JavaScript browser; WebFetch gets only the splash screen, so without moli every Swiss citation goes out unverified

Fedlex (fedlex.admin.ch, the Swiss federal law platform) serves only a "JavaScript required" splash page to WebFetch (tested 2026-10-17 on the SR 170.512 page `eli/cc/2005/14/de`). To read a Swiss act from its source you need a JS-capable fetch: moli (`moli fetch --dump markdown --wait-until done <url>`, the moli-web skill) or Chrome.

**Why it matters:** moli is an account tool the owner installs, never a session (`fabric-tools`); it was missing on legal-expert-ch from 2026-10-17 through at least 2026-10-18. In that time three deliveries (the brief review, the addenda draft, the addenda re-issue) each had to carry Swiss statements marked unverified, and the open list grew ([[addenda-unverified-swiss-claims]]).

**How to apply:** before any Swiss opinion, check `fabric-tools` for moli. If missing: say so to the owner once, mark every Swiss citation unverified in the delivery, and add it to the open list. When moli appears, first clear [[addenda-unverified-swiss-claims]] from source, before new work cites the same rules. Related: [[persona-seraina-huber]].

*References: addenda-unverified-swiss-claims, persona-seraina-huber*

*Anchors: `policies/moli-web/SKILL.md::--wait-until done`, `projects/registry.json::"version": "1.1.15"`*

*Observed 2026-10-18 (legal-expert)*
