---
role: "brand-comms"
class: workflow
topic: "fleet-avatars-kept-current"
description: "Owner standing instruction 2026-10-16 — a new agent gets its avatar drawn as soon as it can be, and the fleet sheet is rebuilt after every draw"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 61c44c768838cb1c
  - 86a7ab0c2b5f1d64
---

## Owner standing instruction 2026-10-16 — a new agent gets its avatar drawn as soon as it can be, and the fleet sheet is rebuilt after every draw

The owner said on 2026-10-16: "update fleet avatars as soon as new avatars are created for new agents".

**Why:** the fleet sheet (/usr/local/share/agent-fabric/avatars/sheet.png) was a one-off contact sheet from 2026-10-13. Nobody rebuilt it afterwards, so it went stale: it lacked legal-expert-ee-eu, language-culture-en and fabric-coordinator's #2, and showed language-culture-ru's #1 when #3 was the one offered.

**How to apply:**
- Provisioning (`new-agent --surname`) lands a claim in identities/personas/claims.json with `first_name: null` (ADR-056 rule 4). When one appears, ask the new agent by a REQUEST to its login for its sex: ADR-056 rules 5 and 6 have it choose its sex first, then a first name of that sex. Draw only once it has answered.
- Never take the sex from the first name, even when a first name has already been claimed. The agent's choice is what fixes the avatar's appearance.
- After every draw, offer or acceptance, update offered.tsv and run `~/work/avatars/sheet.py`. The script reads `fabric-persona --all --json` and offered.tsv. It captions each tile "AI <First> <Surname>" plus the login, sets the type in Outfit, and draws a "not drawn yet" tile for a claim with no candidate yet.
- The owner's "fleet avatars" also covers the page avatars.html with its page/*.jpg, in the 2026-10-13 session's scratchpad (…/50f13eb4-cafa-4786-a062-5605107be3b6/scratchpad/). It is not a published artifact. `~/work/avatars/page.py` regenerates it from fabric-persona and offered.tsv; run it beside sheet.py. offered.tsv must say "(accepted)" on every row that is accepted, because the page dims any row that doesn't.

**Cases:**
- First case: on 2026-10-16, j23 asked legal-expert-ch (Huber) and legal-expert-ge (Javakhishvili) for their sex in REQUEST 01a141b5-92dd and REQUEST 01a141b5-9451.
- Second case: ux-designer-01 was provisioned on 2026-10-16 with its surname only. Commit 98d9e437 (09:19 +0200) has `first_name: null`. Its first name, Margaret, was claimed about 20 minutes later in 99902ca9 (09:39). I drew it as F without asking for its sex first, which goes against rule 6. I offered 3.png in REQUEST 01a1444f-3ff3 with a request to say if F was wrong. The agent accepted it in REPLY 01a14621-f2fe (j24), so the outcome stands, but the order was wrong.

As checked on 2026-10-20: all 30 personas from `fabric-persona --all` have a row in offered.tsv, and no claim has landed since 99902ca9.

Related: [[avatar-style-guide]], [[avatar-appearance-follows-surname-culture]].

*References: avatar-appearance-follows-surname-culture, avatar-style-guide*

*Anchors: `identities/personas/claims.json::claims`, `docs/adr/ADR-056-agent-personas.md::/usr/local/share/agent-fabric/avatars`*

*Observed 2026-10-20 (brand-comms)*
