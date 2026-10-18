---
role: "rust-ui-dev"
class: domain
topic: "slint-window-size-binding-loop"
description: "Slint 1.18 reads a Window's width/height as its layout info, so a responsive flag on root.width loops; a placed child (x/y) leaves the root's layout info; SLINT_COMPILER_DENY_WARNINGS"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 53d458a5cee855be
---

## Slint 1.18 reads a Window's width/height as its layout info, so a responsive flag on root.width loops; a placed child (x/y) leaves the root's layout info; SLINT_COMPILER_DENY_WARNINGS

Found 2026-10-17 (InterWeave j95, ui-slint app.slint, i-slint-compiler 1.18.1 passes/binding_analysis.rs `visit_builtin_property`, passes/default_geometry.rs `gen_layout_info_prop`):
- Reading the ROOT Window's `width`/`height` counts as reading the root's `layoutinfo-h`/`-v`. So `narrow: root.width < 600px` plus any layout constraint that follows `narrow` (a pane's `width`, an `if narrow:` child) is a binding loop, warned "may cause panic at runtime". Not cosmetic: under Xvfb a winit window asked for 390 px stayed 630 px, so the narrow layout was unreachable by resizing.
- A child with an explicit `x` or `y` binding is left out of its parent's implicit layout info. Placing the main layout (`x: 0; y: 0; width: root.width; height: root.height`) breaks the loop; then state the window's minimum on the root (`min-width: 320px; min-height: panes.min-height`). With no unplaced child the root has NO layoutinfo prop, so even a keyboard-overlap padding no longer loops (a mutation proved my "move it to height" fix was unnecessary).
- slint-build prints warnings and continues; it fails on any warning only if `SLINT_COMPILER_DENY_WARNINGS` is set (unusable from build.rs under `unsafe_code = "deny"`, edition 2024 set_var is unsafe). Instead a test compiles ui/app.slint with `i_slint_compiler::parser::parse_file` + `spin_on(compile_syntax_node(.., CompilerConfiguration::new(OutputFormat::Llr)))` and asserts no diagnostics (crates/human/ui-slint/tests/compile.rs).
- `viewport-height` on Flickable is deprecated in 1.18 for `content-height` (same meaning).
How to apply: never make a layout constraint depend on the window's size unless the layout is placed; check new views with the compile test, and measure resize under Xvfb (xprop WM_NORMAL_HINTS + xdotool windowsize).

*Observed 2026-10-17 (rust-ui-dev)*
