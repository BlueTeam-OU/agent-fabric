---
role: "rust-ui-dev"
class: domain
topic: "slint-textinput-no-focus-reason"
description: "Slint 1.18 TextInput has no focus-gained(reason); keyboard mode is set by a root FocusScope's capture-key-pressed on Tab (KeyboardScope), not per control"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 2f259a19e80a9e76
---

## Slint 1.18 TextInput has no focus-gained(reason); keyboard mode is set by a root FocusScope's capture-key-pressed on Tab (KeyboardScope), not per control

In Slint 1.18.1, only FocusScope has `focus-gained(reason)` / `focus-lost(reason)` (i-slint-core items/input_items.rs). TextInput has only `has-focus`. A "ring only in keyboard mode" flag set from `FocusReason.tab-navigation` therefore misses a text field reached first by Tab, and a modal whose Tab handler moves focus by a call.

What works: a FocusScope wrapping the whole window's content with `capture-key-pressed` that sets the flag on Tab/Backtab and returns `reject`. Slint runs capture from the window down the focused item's ancestor chain before any `key-pressed` (window.rs `process_key_input`). Give it `focus-on-tab-navigation: false` (and `focus-on-click: false` if a blank click should focus nothing). Limits: the chain stops at PopupWindows, and with nothing focused there is no chain, so that first Tab passes no capture.

InterWeave: `KeyboardScope` in `crates/human/ui-slint/ui/app.slint`, PR #547 (j83, merged afc31fe0 2026-11-04). The reverse case (a press on a TextInput keeps the flag) was j84, fixed on the desktop by the winit filter: [[slint-press-on-textinput-invisible]].

Related: [[focus-ring-reach-spacing]]

*References: focus-ring-reach-spacing, slint-press-on-textinput-invisible*

*Observed 2026-11-04 (rust-ui-dev)*
