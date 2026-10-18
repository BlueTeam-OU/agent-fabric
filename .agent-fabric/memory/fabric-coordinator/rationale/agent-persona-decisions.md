---
role: "fabric-coordinator"
class: rationale
topic: "agent-persona-decisions"
description: "Owner 2026-10-13 — agent personas: 'AI <Name> <Surname>' / 'AI <Name> - <Role>', worldwide scientist surnames (no weapons-related), each agent picks surname+name+sex; anime avatars the agent may reject; sex is for appearance only, no…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c054cff92e9b8f49
---

## Owner 2026-10-13 — agent personas: 'AI <Name> <Surname>' / 'AI <Name> - <Role>', worldwide scientist surnames (no weapons-related), each agent picks surname+name+sex; anime avatars the agent may reject; sex is for appearance only, no gender, 'it' on request

The owner, 2026-10-13, in the coordinator's session (designing agent personas; ADR-033 says no transport
gives an agent a human-style identity, so this needs a record amending it):

- **Display**: "AI Ada", "AI Ada Maxwell", or by role "AI Ada - Python Dev". The "AI" prefix is the
  clear marker that it is an AI agent.
- **Names from all over the world**; the language-culture agents choose from their own culture.
- **Surnames** from a set — scientists are good — but none directly related to weapons ("like nobel or
  oppenheimer"). Each agent picks its surname from the list, and chooses its first name and its sex
  (M/F).
- **Sex is for the image only** (a consistent appearance). "Gender don't make sense for a synthetic
  agent": no gender or pronoun field. An agent that does not want he/she may ask to be called "it",
  "appropriate both as neutral and as synthetic".
- **Avatar**: anime-like, matching name/surname/sex; the owner said "ghibli studio like" — I proposed
  our own style guide ("warm, hand-painted anime style") rather than naming the studio (style-imitation
  and Miyazaki's stance), not yet answered. Each agent may **reject** an image of itself it doesn't
  like, until it accepts one.

My proposals still open with the owner: one agent per surname; the weapons test written as "best-known
work or a role held was weapons development"; profile in `settings/profile.json` of `fabric-agent-<id>`;
brand-comms-01 owns the style and generates the avatars; a decision record first.
Related: [[agent-repo-per-agent]].

*References: agent-repo-per-agent*

*Observed 2026-10-13 (fabric-coordinator)*
