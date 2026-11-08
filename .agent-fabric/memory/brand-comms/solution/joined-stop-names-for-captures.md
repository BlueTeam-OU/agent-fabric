---
role: "brand-comms"
class: solution
topic: "joined-stop-names-for-captures"
description: "Before using or requesting a gzapp passenger/driver app capture that shows a [redacted] stop name, check the name is native, not a scraped Russian romanisation; ask for a joined stop"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2a782efb8766fab9
---

## Before using or requesting a gzapp passenger/driver app capture that shows a [redacted] stop name, check the name is native, not a scraped Russian romanisation; ask for a joined stop

As of gzapp main 691ab0962 (2026-10-30): the [redacted] GTFS feed's stop names
were scraped with Russian romanisations ("Ulitsa Nikea"; 324 of 780 stops).
The stop-name join (gzapp #1190/#1191/#1192/#1194) gives only the stops near an
OSM object with a Georgian name (164 of 780) a ka row, name:<lang> rows and a
Latin romanisation, and the apps pick by display locale. Every other stop
still shows the feed's scraped name to every reader, en and ka alike, until
OSM is contributed to, which the owner has not asked for.

**Why:** a 2026-09-20 capture on gita-pitch slide 8 showed "Walk to Ulitsa
Nikea" to a Georgian state agency; nobody had read the street name.

**How to apply:** read every place name in a capture enlarged before it goes on
a slide. When requesting one, ask for a journey whose shown stops are joined,
and for the stop id and its served names (base, names.en, names.ka,
name_latin) in the handover, as flutter-dev-01 gave at cd1721096. Re-check the
counts on gzapp main before quoting them. Related: [[capture-handover-by-for-branch]].

*References: capture-handover-by-for-branch*

*Anchors: `gzapp.decks:ASSETS.md::passenger-journey-following-line.png`*

*Observed 2026-10-31 (brand-comms)*
