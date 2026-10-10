---
role: "rust-ui-dev"
class: domain
topic: "slint-rendered-window-lessons"
description: "Slint 1.18 layout/font traps the testing backend does not show -- monospace by name, wrap min-width, a component's height from its only child layout; look at the winit window under Xvfb"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 649e6da7d4b6af9b
  - d5bc3023023be7a9
---

## Slint 1.18 layout/font traps the testing backend does not show -- monospace by name, wrap min-width, a component's height from its only child layout; look at the winit window under Xvfb

Found 2026-10-04 by screenshotting the ui-slint window (winit + software renderer) under `xvfb-run` + ImageMagick `import`; the testing backend passed every case:
- `font-family: "monospace"` is passed to parley as a NAMED family (i-slint-core textlayout/sharedparley/shaping.rs), matches nothing, falls back to sans. Resolve the generic via `i_slint_common::sharedfontique::fontique::Collection::generic_families(GenericFamily::Monospace)` (ui-slint `code_font`).
- A `wrap: word-wrap` Text's minimum width is its longest word: a long URL widens the whole list. `min-width: 0` fixes it (cannot be combined with `width:` -- wrap the Text in a layout instead).
- In a HorizontalLayout, a marker Text and a content Rectangle both stretch: give the marker `horizontal-stretch: 0`.
- A FocusScope component takes its child layout's height only when that layout is its ONLY child; a TouchArea sibling left it one line tall in the winit window, while the testing backend sized it correctly (mutation survived there). Put the TouchArea inside.
- `cargo test -p interweave-human-ui-slint` builds the crate's examples WITHOUT the desktop feature and overwrites the scratch example binary ("No default Slint platform"): rebuild it with `--example <n> --features desktop` right before using it. An AT-SPI read of a scratch window can reuse desktop-e2e's a11y driver from a scratch test file (Bus::window_of(child pid)), removed after (2026-10-06, route indicator).
- The rendered trust page (2026-10-06) showed an unlabelled own PeerId reading as a trusted peer and an unlabelled field at the page foot -- the testing backend passed; give visible captions (accessible-role: none when the field carries the same label).
How to apply: before calling a Slint view done, render it with realistic long content under Xvfb and look; a testing-backend geometry test is no evidence for these. Scratch example in crates/human/ui-slint/examples/, never committed.

*Observed 2026-10-06 (rust-ui-dev)*
