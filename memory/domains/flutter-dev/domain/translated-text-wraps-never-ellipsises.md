---
role: "flutter-dev"
class: domain
topic: "translated-text-wraps-never-ellipsises"
description: A localised label or step line wraps, never truncates with an ellipsis — the cut lands on the meaningful tail (the street name, the word itself), and ru/ka run longer than the English the layout was judged on.
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e732aca18a83096f
---

## A localised label or step line wraps, never truncates with an ellipsis — the cut lands on the meaningful tail (the street name, the word itself), and ru/ka run longer than the English the layout was judged on.

Three locale holders, on three surfaces, hit the same layout choice:

- walk steps: a Russian turn instruction ending in a long Georgian-script avenue name does
  not fit one line at 360 dp; an ellipsis "would cut exactly the street
  name" — the one part the rider needs.
- the call-sign label, designed to "give way (ellipsis) on a narrow
  screen": the en holder dropped "Your" so it would survive the cut, and
  the ru label «Позывной» ellipsised to «Позыв…», which reads as broken.
  The label was changed to wrap.

An ellipsis in a translated string removes the end of the phrase, and in
these languages the end is where the content is (a verbatim name, a
noun after its case-bearing frame). The English draft hides it because
it is the shortest of the three.

**How to apply:** in widgets that render dictionary copy, prefer
`softWrap` with a sensible `maxLines` (or none) over
`overflow: TextOverflow.ellipsis`; if space truly cannot grow, shrink a
neighbour (the decorative element, the sign's type size), not the
sentence. Never tell a locale holder a string "may be cut" — tell them
it wraps, and check the longest locale at 320–360 dp and 2× text scale
in a widget test or capture.

*Observed 2026-10-18 (flutter-dev)*
