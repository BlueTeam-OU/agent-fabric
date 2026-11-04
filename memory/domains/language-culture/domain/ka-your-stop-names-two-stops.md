---
role: "language-culture"
class: domain
topic: "ka-your-stop-names-two-stops"
description: "In rider copy \"თქვენი გაჩერება\" (your stop) reads as the stop to get off; name the boarding stop \"ჩასაჯდომი გაჩერება\""
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 587baa2bdf2728e6
---

## In rider copy "თქვენი გაჩერება" (your stop) reads as the stop to get off; name the boarding stop "ჩასაჯდომი გაჩერება"

gzapp j106 (2026-10-19, ADR-077 wake keys, e18bea229): within one set, "თქვენი გაჩერება" (your stop) meant the stop to get off in one string and the boarding stop in another. A cold read caught it, since a reader takes "your stop" as the destination. Two more findings from the same job. Standing alone in the singular (a channel name), "გაჩერება" reads as the act of stopping. "შეხსენება" is a reminder the user set, not an event alert. For one rider, "ჩასაჯდომად"; "ჩასხდომა" is collective, as in the admin copy. In rider copy, name the boarding and alighting stops explicitly, and keep "your stop" for the alighting one if it is used at all.

*Observed 2026-10-19 (language-culture)*
