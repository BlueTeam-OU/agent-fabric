---
role: "rust-ui-dev"
class: domain
topic: "slint-android-handle-disable"
description: Slint 1.18.1 Android leaves the TextInput cursor handle drawn after focus loss (Disable arm); InterWeave carries it as a toolkit limit, not a vendored patch
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 62dc317a076bad0c
  - 81b779e211ea34b9
---

## Slint 1.18.1 Android leaves the TextInput cursor handle drawn after focus loss (Disable arm); InterWeave carries it as a toolkit limit, not a vendored patch

In i-slint-backend-android-activity 1.18.1, `androidwindowadapter.rs` `input_method_request` does not hide the cursor or selection handles in the Disable arm; only Enable and Update call set_imm_data with the handle flag. Clearing focus (`clear-focus()`, or Back closing the keyboard) therefore leaves the handle's PopupWindow drawn until the next touch. App code cannot remove it. Upstream master has the same Disable arm (checked 2026-10-20).

On 2026-10-20, architect-cto-01 decided (DECISION 01a15914) to carry it as "F3 residual" in the Stage 17 closing record under (j). There is no vendored Slint backend: a vendored tree needs its own ADR (ADR-0051's rule) and a licence question under ADR-0057 decision 3. Upstream issue drafted at a scratch path; filing it waits for the owner's word.

**How to apply:** don't re-try app-side fixes for a lingering Android text handle. Check whether a Slint bump carries a Disable-arm fix.
Worse than the residual: the app-side attempt (b010afb9, clear focus whenever the keyboard overlap fell to zero) never removed the handle and made one conversation's composer refuse focus altogether (F16, found by ux-designer-01's bisect between two device builds; host tests could not reproduce it). Removed in ff981b5e and seen fixed on the Pixel: closing the keyboard keeps the field focused, as a platform field does. Rule: never clear a text field's focus to hide a toolkit artefact; once a limit is ruled unfixable, take the workaround out. (reflection; MESSAGE-IDs 01a159e7-6f45, 01a159f6-f587, 01a15abb-8b8b)

*Observed 2026-10-24 (rust-ui-dev)*
