---
role: "rust-ui-dev"
class: domain
topic: "slint-press-on-textinput-invisible"
description: "Slint 1.18: no element can see a pointer press a TextInput takes; catch every press in the winit window filter (one per window, replaced on re-register); testing backend bypasses it; Android has none"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 65598d35d8b210a8
---

## Slint 1.18: no element can see a pointer press a TextInput takes; catch every press in the winit window filter (one per window, replaced on re-register); testing backend bypasses it; Android has none

In Slint 1.18.1 a `TextInput` returns GrabMouse on a press. An ancestor `TouchArea`'s filter-before-children only sets mouse-x/y and has-hover and runs no callback. `FocusScope` is the only element that is told a focus reason. Only `TooltipArea` uses ForwardAndObserve. So no element in the .slint tree can observe a press on a text field (i-slint-core items/input_items.rs, input.rs). An overlay TouchArea would swallow the press: the caret would not move to the click and drag-select would break.

What works on the desktop is the winit window filter (`slint::winit_030::WinitWindowAccessor::on_winit_window_event`). It sees every event before Slint routes it. Each window has exactly ONE filter, and registering again replaces the old one, so every duty must live in one closure. The testing backend never calls it, so test the filter's body as a function on the window, not the wiring. Android (i-slint-backend-android-activity 1.18.1) calls its event listener only after it has processed the event, and an InputAvailable does not say which input arrived, so there is no equivalent there.

InterWeave: `end_keyboard_mode_at_press` / `press_ends_keyboard_mode` in `crates/human/ui-slint/src/lib.rs`, used by `View::on_window_focus` and `RefusalView::new` (PR #549, j84, merged 09e98c67 2026-11-04). Each window's wiring call is proved by desktop-e2e `human_app/ring.rs` (refusal path, Trust own PeerId; PR #551, j85): a mutant of either call fails only its window's case.

Rendered check recipe by hand: Xvfb plus xdotool (both on develop-qzapp, not in CI); in a test use XTEST through x11rb instead ([[e2e-person-input-xtest]]). Run `xdotool windowfocus --sync` first; with no window manager, `key --window` never reaches the window. Then use plain `xdotool key`/`mousemove x y click 1` and `import -window root`. A profile is the example `architecture/config/examples/human-desktop.yaml` with every <TOKEN> replaced by a PeerId, `profile.name` set to the profile, and no daemon needed. Your card (⋮ menu) has two text fields.

Related: [[slint-textinput-no-focus-reason]] [[focus-ring-reach-spacing]]

*References: e2e-person-input-xtest, focus-ring-reach-spacing, slint-textinput-no-focus-reason*

*Observed 2026-11-04 (rust-ui-dev)*
