---
role: "rust-ui-dev"
class: domain
topic: "slint-scale-factor-env-not-applied"
description: "SLINT_SCALE_FACTOR / WINIT_X11_SCALE_FACTOR do not apply in a probe; dispatch WindowEvent::ScaleFactorChanged; release builds have no element tree"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 8ac49358db798df5
---

## SLINT_SCALE_FACTOR / WINIT_X11_SCALE_FACTOR do not apply in a probe; dispatch WindowEvent::ScaleFactorChanged; release builds have no element tree

Found 2026-11-05 (j92, PR #563). Desktop release probes ran under `tools/ci/with_display.sh` with
`SLINT_SCALE_FACTOR=2` in the environment. `take_snapshot` returned 1000 × 600 frames for a 1000 × 600 logical
window, so the factor was not applied, and every figure I reported "at scale 2" was a scale-1 figure. I had to
correct it on #561 (issuecomment-6647727188) and in #563's body.

**How to apply:** before reporting a measurement at a scale, check the frame's physical size against the logical
size, or read `window.scale_factor()` in the probe. A height measured for the i16 ceiling (32,767 *physical* px)
is wrong by the factor otherwise. How to really get scale 2 on this host's desktop backend is still unknown; find
out before #561 A4.

Related: [[slint-software-renderer-i16-height]]

**Solved 2026-11-05 (j95):** dispatch `slint::platform::WindowEvent::ScaleFactorChanged { scale_factor }` on the
window after `show()`. take_snapshot then returns frames of logical × factor (720 × 1,600 for 360 × 800 at 2), and
`scale_factor()` reads the factor. WINIT_X11_SCALE_FACTOR does not take effect either: the probe runs no event loop,
so winit's change is never delivered. Two caveats:
- A RELEASE build of ui-slint has no element tree (build.rs `with_debug_info(!release)`), so ElementQuery finds
  nothing and every height reads 0. Measure layout in a debug build; geometry does not depend on the profile.
- At scale 3 with 200 % text, a 40-heading body at the bound (11,143 logical px at 360 wide) panics the software
  renderer (euclid size.rs:335).

The probe is crates/human/ui-slint/tests/long_probe.rs on the j95 branch (uncommitted). Its env is WIDTH, FONT,
SCALE, SOURCE.

*References: slint-software-renderer-i16-height*

*Observed 2026-11-05 (rust-ui-dev)*
