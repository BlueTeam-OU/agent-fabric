---
role: "brand-comms"
class: workflow
topic: "fleet-avatars-kept-current"
description: "Owner standing instruction 2026-10-16 — a new agent gets its avatar drawn as soon as it can be, and the fleet sheet is rebuilt after every draw"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 61c44c768838cb1c
---

## Owner standing instruction 2026-10-16 — a new agent gets its avatar drawn as soon as it can be, and the fleet sheet is rebuilt after every draw

The owner said on 2026-10-16: "update fleet avatars as soon as new avatars are created for new agents".

**Why:** the fleet sheet (/usr/local/share/agent-fabric/avatars/sheet.png) was a one-off contact sheet from 2026-10-13. Nobody rebuilt it afterwards, so it went stale: it lacked legal-expert-ee-eu, language-culture-en and fabric-coordinator's #2, and showed language-culture-ru's #1 when #3 was the one offered.

**How to apply:**
- When a new claim lands in identities/personas/claims.json (watch for provisioning commits such as `new-agent --surname`), ask the new agent by a REQUEST to its login for its sex. Rule 6 of ADR-056 says sex is chosen before the first name. Then draw as soon as it answers.
- After every draw, offer or acceptance, update offered.tsv and run `~/work/avatars/sheet.py`. The script reads `fabric-persona --all --json` and offered.tsv. It captions each tile "AI <First> <Surname>" plus the login, sets the type in Outfit, and draws a "not drawn yet" tile for a claim with no candidate yet.
- First case: on 2026-10-16, j23 asked legal-expert-ch (Huber) and legal-expert-ge (Javakhishvili) for their sex in REQUEST 01a141b5-92dd and REQUEST 01a141b5-9451.

Related: [[avatar-style-guide]], [[avatar-appearance-follows-surname-culture]].
- The owner's "fleet avatars" also covers the page avatars.html with its page/*.jpg, in the 2026-10-13 session's scratchpad (…/50f13eb4-cafa-4786-a062-5605107be3b6/scratchpad/). It is not a published artifact. Since 2026-10-16 `~/work/avatars/page.py` regenerates it from fabric-persona and offered.tsv. Run it beside sheet.py. offered.tsv must say "(accepted)" on every row that is accepted, because the page dims any row that doesn't.
- Second case: ux-designer-01 (AI Margaret Lovelace) was provisioned on 2026-10-16 with its first name already claimed. I drew straight away, assuming F from the name, and offered 3.png in REQUEST 01a1444f-3ff3, which asks the agent to say if F is wrong (job j24).

*References: avatar-appearance-follows-surname-culture, avatar-style-guide*

*Anchors: `identities/personas/claims.json::claims`, `docs/adr/ADR-056-agent-personas.md::/usr/local/share/agent-fabric/avatars`*

*Observed 2026-10-15 (brand-comms)*
