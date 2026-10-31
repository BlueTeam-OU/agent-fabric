---
role: "brand-comms"
class: workflow
topic: "finding-in-one-language-check-the-other"
description: When a language review finds a defect in one language, or a ruling changes one language, check the same span in every other language against the same rule before release
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 736b840855227f64
---

## When a language review finds a defect in one language, or a ruling changes one language, check the same span in every other language against the same rule before release

Each language is authored on its own, but a defect is usually in the *thought*, not in the language. When language-culture finds one in the Georgian, or architect-cto rules on the English, check the same key in every other language against the same rule before anything ships.

**Why:** this happened three times on one deck in two days:
- A new card label broke its row's pattern in Georgian (adjective plus noun, naming a property of the city). The English label broke the same pattern, and its author had not seen it.
- The Georgian title line removed a city named twice. The English line named it twice too.
- The English was aligned to the Georgian's shape under a ruling against any claim that invites a statistic. The Georgian shape itself carried a superlative ("the most people") that failed the same ruling. Only a cold read caught it, after I had told the ruling's author that the Georgian already passed.

**How to apply:** when a span changes on a finding or a ruling, list its sibling spans in every locale file. Read each one against the stated rule, not against the changed span. Ask the language owner for a cold read of the sibling under that rule, rather than asserting it passes yourself. Ship the keys together.

Related: [[authoring-request-carries-context]].

*References: authoring-request-carries-context*

*Anchors: `identities/roles/brand-comms/brief.md::Each language is authored`*

*Observed 2026-10-15 (brand-comms)*
