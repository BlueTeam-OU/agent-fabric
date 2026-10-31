---
role: "rust-ui-dev"
class: domain
topic: "slint-focus-request-needs-focus-wanted"
description: "A Slint focus request lands only on a control with focus-seq/focus-wanted, and a test must assert focus-id, not focus-target; set_vec recreates rows and drops a touch's grab"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - c11fca87c58be553
---

## A Slint focus request lands only on a control with focus-seq/focus-wanted, and a test must assert focus-id, not focus-target; set_vec recreates rows and drops a touch's grab

Three traps met in one batch (InterWeave j54 batch 4, 2026-10-25), each passing its tests until a test read the right thing.

- **A focus key that takes no request.** In the ui-slint pattern, Rust sets `focus-target` and bumps `focus-seq`; only a control with `focus-seq` bound and `focus-wanted: root.focus-target == <its key>` moves. Decline on a proposal, the Contacts list's `OpenRow` and a contact's Remove photo had a `focus-key` but no request, so focus "sent" there stayed where it was. One way to find them: list every `focus-key:` in app.slint whose element has no `focus-wanted`, then intersect with the keys Rust sends.
- **Assert `get_focus_id()`, never `get_focus_target()`.** The target is the request, so asserting it passes whether or not focus moved. The undo test for Delete contact and Remove photo asserted the target, and it passed for weeks while neither landed.
- **A control made by the same render misses its first `focus-seq` bump.** Use the after-draw form (two bumps, a turn apart) for any target in a list the render replaces whole.
- **`VecModel::set_vec` recreates every repeated instance.** A row under a finger loses its pointer grab: no release or cancel callback arrives, and the gesture state goes stale for the next touch. Update in place (by key, `set_row_data`/insert/remove) where a row can change during a touch.

**Why:** each defect sat behind a green test that fed what the author had in mind, which is the CLAUDE.md §4 rule about tests.
**How to apply:** when adding a focus target, add `focus-seq`/`focus-wanted` to the control and assert `get_focus_id` in its test. When a list can change under a drag, update it in place. Related: [[slint-layout-traps-seen-rendered]], [[slint-name-clash-traps]].

*References: slint-layout-traps-seen-rendered, slint-name-clash-traps*

*Observed 2026-10-25 (rust-ui-dev)*
