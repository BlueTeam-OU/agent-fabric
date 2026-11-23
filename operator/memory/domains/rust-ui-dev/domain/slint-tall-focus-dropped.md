---
role: "rust-ui-dev"
class: domain
topic: "slint-tall-focus-dropped"
description: Slint 1.18 drops keyboard focus from an item taller than its Flickable that took focus off screen; TAB then restarts at the top
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 2244debb94c32c28
---

## Slint 1.18 drops keyboard focus from an item taller than its Flickable that took focus off screen; TAB then restarts at the top

Found 2026-11-08 (j95, A40 run of the long-message case). In Slint 1.18.1 `Flickable::choose_min_move` asks for an
item's top and bottom in view at once; for an item taller than the Flickable no scroll satisfies both and it returns
0 (its comment says "only with NaNs"). So a focused item that is taller than the list and wholly off screen is never
scrolled into view, and `WindowInner::process_key_input` drops the focus of an item it finds not visible on the NEXT
key event, the TAB's own KeyReleased included ("Reset the focus... not great"). Symptom: TAB from a tall message
jumps to the window's first stop, Shift+TAB to its last; a testing-backend probe that sends press and release shows
it (`focus-lost(reason)` with tab-navigation right after `focus-gained`).

**Why:** focus traversal admits items clipped only by a Flickable, so the item is reached, then lost.

**How to apply:** any focusable that can be taller than its scrolling list must be revealed by the view itself in its
`focus-gained` (synchronous, before the toolkit's reveal): InterWeave's `Reveal.tall` + `messages-flick.reveal-tall`
in crates/human/ui-slint/ui/app.slint. To diagnose a lost focus, read `WindowInner::from_pub(..).focus_item` and
upgrade it in a probe; a dead weak with valid element handles means focus was dropped, not the item destroyed.

Related: [[slint-focus-request-needs-focus-wanted]] [[slint-testing-tree-omits-clipped]]

*References: slint-focus-request-needs-focus-wanted, slint-testing-tree-omits-clipped*

*Observed 2026-11-08 (rust-ui-dev)*
