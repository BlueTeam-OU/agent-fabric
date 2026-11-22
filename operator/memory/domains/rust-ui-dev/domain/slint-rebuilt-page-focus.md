---
role: "rust-ui-dev"
class: domain
topic: "slint-rebuilt-page-focus"
description: "Slint page rebuilt from Rust on every input loses a repeated stop's focus -- re-ask it in changed page by the (segment, index) the stop reported"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 8d5336d8cb94e0b7
---

## Slint page rebuilt from Rust on every input loses a repeated stop's focus -- re-ask it in changed page by the (segment, index) the stop reported

Measured on the InterWeave identity page (j199, 2026-11-03). Rust sets a fresh struct with new ModelRcs after every input. Slint 1.18.1, headless testing backend.
- For a modal page with a variable number of stops (26 keys, chips, 24 slots), have each stop report its segment and index when it takes focus. Do the TAB arithmetic over segment sizes taken from the page's model. Slint functions have no loops and no substring, so a focus-id string cannot be parsed back.
- `changed page` is the single place for "where does focus go after this input". It re-asks the same stop on every rebuild, clipped to the segment's new size, or focuses the page itself when the segment is gone. Without it focus is lost on the rebuild: the mutation that removed the re-ask failed two tests.
- A new element misses the first focus-seq bump ([[slint-focus-new-element]]). A one-shot 1 ms Timer that bumps again is the in-Slint fix. In tests, walk the tree, then run mock_elapsed_time(Duration) plus update_timers twice.
- mock_elapsed_time takes std::time::Duration, not ms.
- A FocusScope whose Return presses the control swallows a page-level Enter shortcut. Route Enter to the page while a "typing" mode is on.

*References: slint-focus-new-element*

*Observed 2026-11-03 (rust-ui-dev)*
