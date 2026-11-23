---
role: "rust-ui-dev"
class: domain
topic: "slint-look-lessons"
description: "Slint layout and theming traps met building the Android look (j98): rem in a global, a stretchable row under a wrapped bubble, rendering dark/RTL in a scratch example"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 0750cc1841de8665
---

## Slint layout and theming traps met building the Android look (j98): rem in a global, a stretchable row under a wrapped bubble, rendering dark/RTL in a scratch example

Met in j98 (#295, #296, Slint 1.18):
- In a `global`, a `rem` value needs a property of the relative-font-size type; a length property refuses it.
- A row with stretch under a wrapped Text takes that Text's height: a chips or day row under a wrapped bubble grew with it. Give such rows `vertical-stretch: 0` (crates/human/ui-slint/tests/look.rs, the wrapped-bubble test).
- To see dark mode or RTL in a scratch example: set RTL through set_touch_settings, and set the Palette colour scheme from a Timer after the window shows, because the backend overwrites the scheme on show.
- A position test of a mirrored layout must compare against the other side, not an absolute x: an absolute x passed with the mirroring removed. Mutate first, then trust the test.

Related: [[slint-rendered-window-lessons]] [[ci-fonts-dejavu-only]].

*References: ci-fonts-dejavu-only, slint-rendered-window-lessons*

*Observed 2026-11-04 (rust-ui-dev)*
