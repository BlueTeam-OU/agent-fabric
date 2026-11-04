---
role: "language-culture"
class: workflow
topic: "name-a-reading-that-departs-from-source"
description: "A reading that departs from en-US or the requester's brief, or settles an ambiguity, is named in the REPLY — that is the only way the owner can catch a wrong one"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 57f3f96e2fefdecb
---

## A reading that departs from en-US or the requester's brief, or settles an ambiguity, is named in the REPLY — that is the only way the owner can catch a wrong one

When the ka-GE says something other than en-US in meaning (because I followed the brief), or settles an ambiguous source with one reading, the REPLY names it on its own line: what I chose, from what, and "tell me if not". Twice that is exactly what caught the error: (1) the wake title followed the brief's "next stop" rather than en-US "Get off soon"; the named choice showed flutter-dev the brief was wrong (ADR-077 §2.2 can wake more than one stop ahead); (2) I read "flagged copy" in delivery.carrier-reshow as the relay copy; python-dev-02 corrected it: the flag is on the InterWeave copy; (3) official_stop_selected, written ahead of en-US from the fact line alone, said in the REPLY that it names no "other" stop because the driver never sees the passenger's plan; backend-dev-02 answered that the passenger is told and en-US landed as "chosen over the planned one", so I aligned (e8fdcb1f5). The surface owner cannot read Georgian, so a reading taken silently is invisible to them and passes the validator. Before delivering, list every value whose rendering differs from en-US in meaning, or that settles an ambiguity. Where the brief and en-US disagree, read the ADR the key rests on first: en-US's author usually had its reason.

*Anchors: `gzapp:product/i18n/en-US.json::journey.wake.alighting.title`*

*Observed 2026-10-24 (language-culture)*
