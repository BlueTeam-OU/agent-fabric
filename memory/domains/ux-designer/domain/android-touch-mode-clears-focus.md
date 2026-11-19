---
role: "ux-designer"
class: domain
topic: "android-touch-mode-clears-focus"
description: Android touch mode clears focus from a button on a touch and hides the focus highlight — never cite it as keeping focus
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - f0b3d0a55294cfe9
---

## Android touch mode clears focus from a button on a touch and hides the focus highlight — never cite it as keeping focus

In the Android View system, entering touch mode (a touch) clears focus from a focused view that is not
focusableInTouchMode (a button), or hands it to an ancestor, and the default focus highlight is not drawn in touch
mode. A design rule that keeps keyboard focus where it was after a tap is therefore the app's own choice (an app
that draws its own focus, such as a Slint one, can make it), not platform behaviour. Citing touch mode as keeping
focus was a confirmed review finding on InterWeave PR #645 (round 1 F3, 2026-11-12).
Related: [[j119-tap-focus]].

*References: j119-tap-focus*

*Observed 2026-11-12 (ux-designer)*
