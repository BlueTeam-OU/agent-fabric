---
role: "brand-comms"
class: workflow
topic: "capture-handover-by-for-branch"
description: "When asking another role (flutter-dev, any capturer) for a screenshot or image for a deck, name a for/ branch in gzapp.decks as the landing place, never a design system or artifact page"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3538732300930ac7
---

## When asking another role (flutter-dev, any capturer) for a screenshot or image for a deck, name a for/ branch in gzapp.decks as the landing place, never a design system or artifact page

An image another role makes for a deck (an app capture, a frame) is handed over
as a commit on `<host>/<supplier-login>/for/<my-login>/<what>` in
gzapi-org/gzapp.decks, under `captures/<YYYY-MM-DD>/` (outside every deck
folder), with the provenance facts (app version, source commit, stop/data ids,
locale) in the commit message and no PR. I fetch it, copy the file into
`<deck>/assets/` and add its ASSETS.md row.

**Why:** ASSETS.md rows from September say captures went through the "Gzapi
Brand" design system, but neither flutter-dev-01 nor this account can see it
now (both artifact listings, mine and shared, are empty of it), and a private
artifact page cannot be shared from a session, so a page would never reach me.
A commit is also the artifact a handover must name.

**How to apply:** write the branch name and path into the REQUEST's
ACCEPTANCE from the start; fall back to the same branch on the supplier's own
repository if they cannot push to gzapp.decks. Related: [[joined-stop-names-for-captures]].

*References: joined-stop-names-for-captures*

*Anchors: `gzapp.decks:ASSETS.md::Gzapi Brand design system`*

*Observed 2026-10-31 (brand-comms)*
