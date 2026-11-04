---
role: "rust-ui-dev"
class: domain
topic: "slint-accessible-action-static"
description: "Slint 1.18 announces an element's accessible actions from the handlers it declares, at compile time; a handler that does nothing still advertises the action"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 3eecdad862c9e9a6
---

## Slint 1.18 announces an element's accessible actions from the handlers it declares, at compile time; a handler that does nothing still advertises the action

In Slint 1.18 the supported accessible actions of an element (e.g. Default from `accessible-action-default`) are generated statically from the handlers declared (i-slint-compiler `generator/rust.rs`, `supported_accessibility_actions`). A runtime guard inside the handler cannot make a screen reader stop announcing the element as activatable; only an element without the handler (a separate `if` branch) does.

Seen 2026-10-27 building InterWeave's own card row (contact-cards 5.5): an accepted card row has no menu, but its list-item still advertises a default action. Stated as a limit in crates/human/ui-slint/README.md; asked ux-designer-01 (REPLY 01a17b98-e5ad).

*Observed 2026-10-27 (rust-ui-dev)*
