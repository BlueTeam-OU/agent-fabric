---
role: "fabric-coordinator"
class: workflow
topic: "adr-no-inline-attribution"
description: "No \"(the owner, YYYY-MM-DD)\" in an ADR body or DIGEST, and no date at all in §2–§8 (§1 may date an incident) — ADR-001 §5 rules 10–11, adr.py check refuses both"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3eb3a533d1aced4c
---

## No "(the owner, YYYY-MM-DD)" in an ADR body or DIGEST, and no date at all in §2–§8 (§1 may date an incident) — ADR-001 §5 rules 10–11, adr.py check refuses both

The owner, 2026-09-27: "remove this kind of thing from any adr: (the
owner, 2026-09-13)". A record states the decision; who decided and when
are the header's (Date, Decision Makers, Ratified) and the history note's.
A date that belongs to the content stays in the sentence ("since
2026-09-25, …").

**Why:** the notes the records replaced carried an attribution after
nearly every rule; in a record it is noise, and the header already
carries provenance.

**How to apply:** agent-fabric ADR-001 §5 rule 10; `adr.py check`
refuses a parenthesis in a record body or DIGEST opening on "the owner"
or "the CEO". Brief any drafting agent with it. Other files (CLAUDE.md,
policies, skills) were not in scope of the request — ask before sweeping
them. See [[review-p3-may-defer]].

Then, the same day, on dates: "not sure also this is necessary" about
keeping content dates in the sentence; offered three options, the owner
chose "keep only in §1". ADR-001 §5 rule 11: §2–§8 carry no date; §1 may
date an incident (best by citing its live check or commit); paths, code
spans and the (A …)/(Amendment …) marks keep theirs. The team prompt and
the fabric's CLAUDE files were swept of attributions too, and the managed
projects' CLAUDE.md through REQUESTs to their owning roles.

*References: review-p3-may-defer*

*Observed 2026-09-27 (fabric-coordinator)*
