---
role: "rust-ui-dev"
class: domain
topic: "accessible-names-distinct"
description: "Naming controls for screen readers and voice control -- the visible text is the accessible name, two controls on screen together never share one, the name is the same in every layout"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f2c01dd11a212890
---

## Naming controls for screen readers and voice control -- the visible text is the accessible name, two controls on screen together never share one, the name is the same in every layout

Three rules, each ruled by the UX role on an Android/desktop client (2026-10-19):
- **Label in name (WCAG 2.5.3).** Where the visible text is shortened to fit (a subtitle
  cut to ~18 characters at 320 dp and 200 % font), the accessible name is the short text
  exactly as shown; the full text goes in the accessible description. A voice-control user
  says what they see, so a spoken name that differs from the visible one fails.
- **Two controls visible together never share a name (WCAG 2.4.6).** A wide layout that
  shows a list pane and a detail pane side by side put two overflow buttons named "More
  options" in one window. A distinct accessible description does not fix it: readers say a
  description late or only on request. Give one of them its own name ("App options"),
  differing in its first word so the difference is heard at once.
- **The name is stable across layouts (WCAG 3.2.4).** The renamed control keeps its name in
  portrait too, where it is the only one on screen; a tooltip shows the same name.

How to apply: when a layout change puts a second copy of a control pattern on screen (panes
side by side, a dialog over a bar), list the accessible names in that layout before
building; when text is shortened to fit, check the name against the visible string. The words
themselves go to the language role with purpose and space, never invented. Related:
[[platform-copy-per-situation]].

A list of names a person typed (contacts on one PeerId) is one name per line and one
screen-reader item each, never joined: a typed name can hold "and" or a comma ("Mum and Dad",
"Smith, John"), so a joined string reads as more contacts than there are.

*References: platform-copy-per-situation*

*Observed 2026-10-24 (rust-ui-dev)*
