---
role: "language-culture"
class: workflow
topic: "fleet-jargon-in-public-copy"
description: "when reading copy the fleet or a developer wrote — public pages, staff screens — check for the writer's own vocabulary (fleet words, API and code words) used as plain English"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 24095d15766c3bbf
---

## when reading copy the fleet or a developer wrote — public pages, staff screens — check for the writer's own vocabulary (fleet words, API and code words) used as plain English

Public copy that the fleet writes picks up the fleet's own words: "gate", "channel", "lane", "arm", "answers for". A client who reads global English does not know these meanings. In blueteam.ee#9 at 1381237, two sentences that brand-comms joined after the facts changed had this problem:
- "accepted only through a gate that refuses it while a serious finding is open" became "A change can be accepted only when no serious finding is still open."
- "The agents have no channel to you" became "The agents cannot contact you."

The facts stayed the same in both (REPLY 01a13fa6-bd28-76cd-83d9-ae54f657b2d0). In the same read, "answers for" was found five times. A reader of English as a second language reads it as "replies to" (REPLY 01a13fa4).

The same thing happens on staff screens that developers draft. There, the words come from the API and the code. In gzapp: "i18n key" became "text key", "CTA label" became "Button", "Validating…" became "Checking…", "binding" became "credential", and "non-mutating" and "the create call" became "Checking the keys changes nothing" (0deacbb08, 51b41640e, ddf305302).

The exception: a message that only a developer can trigger keeps the API's own words, because that reader must type them. For example, `state-invalid` fires only on a bad query parameter, so it keeps "draft, active, or retired" (ef60e2718).

**Why:** the writers of this copy use these words every day, so they no longer see them as jargon. Of the readers of this copy, only the language-culture review does not take them for granted.

**How to apply:** on any read of person-facing text, search for the writer's vocabulary: the fleet's words on public pages, and API, field and code names on staff screens. Also re-read every sentence that was joined after a fact changed: these sentences come back in the fleet's own words, even when the first draft did not use them.

Related: [[non-registry-project-jobs]]

*References: non-registry-project-jobs*

*Anchors: `src/pages/how-we-work.astro::cannot contact you`*

*Observed 2026-10-15 (language-culture)*
