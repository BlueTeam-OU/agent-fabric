---
role: "brand-comms"
class: solution
topic: "gzapp-claim-vocabulary"
description: "Before a deck or page states a Gzapp product fact about stops, restrictions, demand data or arrivals: the words architect-cto allows and forbids (2026-10-27)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8e9b5dc1ed0e0bc7
---

## Before a deck or page states a Gzapp product fact about stops, restrictions, demand data or arrivals: the words architect-cto allows and forbids (2026-10-27)

The product's words, as architect-cto ruled them for the [redacted] mayor deck (gzapp.decks `[redacted]-mayor/`):

- **No-stop "stretches", never "zones".** A restriction is a LineString along a route (ADR-067); there are no polygons. A slide may draw a junction or crossing as where one sits; the legend says stretch.
- A restriction blocks **stopping**, never travel or routing. A dynamic point inside one is shifted just before or after it (ADR-059 §2.4).
- Only Gzapp staff author restrictions today (role stop-restriction-editor, scoped global/city/operator/route). A municipal editor is "a role for the municipality's own staff in the same tools" — a proposal. Never "approves": there is no two-party approval workflow.
- The driver **acknowledges or declines** a stop request; never "confirms".
- "Predicted journey times", not "arrival estimates" (ADR-060 grades positions fresh/aging/stale; no arrival board).
- **"Anonymous" applies only to crowding** (ADR-054 Regime 1). Journey-derived demand is personal data: write "aggregated demand information, derived without identifying any rider" — and it does not exist yet.
- Grouping nearby requests into one stop (StopCall) stays off slides while ADR-079 is Proposed; spoken only, if asked.
- **Per-vehicle equipment** is the phone or tablet AND a small Bluetooth beacon: crowding and boarding come only from the beacon (ADR-016); the sensor is the optional part. Nothing is installed on the roads.
- Never "no third-party systems" (the push wake uses the phone platform's service, ADR-077): write "no integration with the city's or the operators' existing systems".
- Status line: "pre-production; the full platform runs on the reference stack with synthetic vehicles and riders; not deployed in any city".

**Why:** each word is a product fact; a wrong one is a claim the product cannot back in front of a named recipient.
**How to apply:** reuse this vocabulary in any deck or page, but re-ask architect-cto when the answer is older than the deck's release — these rest on flags and Proposed ADRs that move.

Related: [[harness-neutral-strip-tokens-not-clauses]].

*References: harness-neutral-strip-tokens-not-clauses*

*Anchors: `gzapp:docs/adr/ADR-067-stop-restriction-authoring.md::stop-restriction-editor`, `gzapp:docs/adr/ADR-054-privacy-regime-separation-four-regimes.md::fully anonymous`*

*Observed 2026-10-27 (brand-comms)*
