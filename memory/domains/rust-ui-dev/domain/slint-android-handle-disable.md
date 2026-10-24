---
role: "rust-ui-dev"
class: domain
topic: "slint-android-handle-disable"
description: Slint 1.18.1 Android leaves the TextInput cursor handle drawn after focus loss (Disable arm); InterWeave carries it as a toolkit limit, not a vendored patch
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 81b779e211ea34b9
---

## Slint 1.18.1 Android leaves the TextInput cursor handle drawn after focus loss (Disable arm); InterWeave carries it as a toolkit limit, not a vendored patch

In i-slint-backend-android-activity 1.18.1, `androidwindowadapter.rs` `input_method_request` does not hide the cursor or selection handles in the Disable arm; only Enable and Update call set_imm_data with the handle flag. Clearing focus (`clear-focus()`, or Back closing the keyboard) therefore leaves the handle's PopupWindow drawn until the next touch. App code cannot remove it. Upstream master has the same Disable arm (checked 2026-10-20).

On 2026-10-20, architect-cto-01 decided (DECISION 01a15914) to carry it as "F3 residual" in the Stage 17 closing record under (j). There is no vendored Slint backend: a vendored tree needs its own ADR (ADR-0051's rule) and a licence question under ADR-0057 decision 3. Upstream issue drafted at a scratch path; filing it waits for the owner's word.

**How to apply:** don't re-try app-side fixes for a lingering Android text handle. Check whether a Slint bump carries a Disable-arm fix.

*Observed 2026-10-20 (rust-ui-dev)*
