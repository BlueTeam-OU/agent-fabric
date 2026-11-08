---
role: "rust-ui-dev"
class: domain
topic: "slint-testing-tree-omits-clipped"
description: "Slint 1.18 testing backend's ElementQuery/find_by_accessible_label does not return items the list (Flickable) clips out of view; make the window tall enough first"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 7a0de5ce454a5512
---

## Slint 1.18 testing backend's ElementQuery/find_by_accessible_label does not return items the list (Flickable) clips out of view; make the window tall enough first

Seen 2026-11-05 in `crates/human/ui-slint/tests/views.rs`
(`a_long_line_is_drawn_in_pieces_that_meet_with_no_gap`, j92). In a default-sized test window, a
message whose body ran past the window had only its first items in the tree: `find_by_accessible_label`
returned 0 for a text drawn lower down. After `set_size(1000, 8000)` and
`update_timers_and_animations()`, every piece was there. A test that looks for something far down a
long message must size the window to hold it, or scroll it into view. Otherwise "label not found"
reads as a rendering bug.

Related: [[slint-layout-traps-seen-rendered]]

*References: slint-layout-traps-seen-rendered*

*Observed 2026-11-04 (rust-ui-dev)*
