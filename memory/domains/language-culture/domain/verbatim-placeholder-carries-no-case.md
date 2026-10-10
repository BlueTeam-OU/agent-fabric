---
role: "language-culture"
class: domain
topic: "verbatim-placeholder-carries-no-case"
description: A verbatim placeholder (stop name, line code) never takes a Georgian case ending; the case sits on a generic carrier noun and the name stays quoted in the nominative.
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 4b4c57ffb5f6f58e
  - 6730976dbe15af5e
---

## A verbatim placeholder (stop name, line code) never takes a Georgian case ending; the case sits on a generic carrier noun and the name stays quoted in the nominative.

A verbatim placeholder ({place} = GTFS stop name, {line} = route code) never takes a Georgian case ending. The hyphen form ("Avtovokzal-მდე") is correct only for a foreign-script word; a Georgian-script name inflects inside the word (ავტოვაგზალი → ავტოვაგზლამდე), which substitution cannot do; a bare numeral ("wait for 4") reads as minutes. Pattern: the case on a generic carrier noun, the name quoted in the nominative — "გაჩერებამდე „{place}“" (to the stop "{place}"), "№ {line} ავტობუსს" (№ then U+00A0). Works in either script; it is the stop-announcement pattern. Origin: journey.now.* for flutter-dev, gzapp commit 7061bc83, 2026-09-18; the cold pass read the hyphen draft as a foreign body, and ru delivered the same shape. Apply: wherever a substituted value is data, find the carrier noun first, and name the carrier assumption (stop, bus) to the caller.

**Addendum (2026-09-26, #948, 8e30d479):** when the verbatim name already carries its own carrier noun (an OSM street, "… avenue"), no carrier can be added: the shape is "{turn}: {street}" with the name in the nominative, and the verb, not punctuation, tells a turn from carrying on (a cold reader took a colon/dash split as noise).

*Observed 2026-09-26 (language-culture)*
