---
role: "language-culture"
class: domain
topic: "a-quoted-name-inside-a-quoted-placeholder"
description: "When a stop name already holds „…“, the ka template keeps „{place}“ and the nesting „…„…““ stands; measure the name in the feed, never in a comment that quotes it."
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: gzapp
    working_copy: "gzapp-j168-ka-ge-place-nests-with-a"
derived_from:
  - 5dec877abb515897
---

## When a stop name already holds „…“, the ka template keeps „{place}“ and the nesting „…„…““ stands; measure the name in the feed, never in a comment that quotes it.

The OSM feed's ka name `სადგური „ქუთაისი 1“` (node 11247008414, osm_routes.json.gz) nests inside journey.now.*'s „{place}“ as „სადგური „ქუთაისი 1““. The template stays: a quoted nominative is right for every ordinary stop (cold-read controls, 2026-11-16), and same-mark nesting is accepted Georgian practice. Swapping the inner marks for «…» would rewrite data on the client. Why: in j168 I "found" an ASCII close in the data, but it was in the `$comment` of ka-name-match.json:102; domain-transit refuted it (01a1e319-f4a5), and the cache has U+201C. Apply: measure a name's typography in the feed cache or the built translations.txt, never in a file that quotes it.

*References: verbatim-placeholder-carries-no-case*

*Observed 2026-11-16 (language-culture)*
