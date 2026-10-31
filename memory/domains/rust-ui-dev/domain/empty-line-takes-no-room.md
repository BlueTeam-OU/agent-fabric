---
role: "rust-ui-dev"
class: domain
topic: "empty-line-takes-no-room"
description: An empty status/error line in a Slint layout keeps its height and the spacing after it; with the keyboard up it eats the message strip
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - b0ff859ab04aece0
---

## An empty status/error line in a Slint layout keeps its height and the spacing after it; with the keyboard up it eats the message strip

A Slint `Text` whose text is empty still takes its font's line height in
a layout, and the layout's `spacing` is added after it even at height 0.
An always-present live-region line (a refused-send line kept so a screen
reader hears it) cost 17 + 8 px in the conversation pane; in landscape
with the keyboard up that was most of the strip left to the messages,
and the newest bubble ended 43 dp above the composer (InterWeave #304
F9 step 5, fixed in #313 d9b98c92).

Rule: a line that is usually empty gets `height: text == "" ? 0px :
self.preferred-height` and shares a row (an inner layout whose spacing
is 0 while it is empty) with its neighbour, so neither its height nor
the spacing remains; keep the element itself so the live region keeps
its node. Any space budget computed by hand (InterWeave's
`pane-chrome`) is updated with it. Probe geometry on the host with the
device's dp figures before guessing: the host look test reproduced the
phone's gap exactly. Related: [[device-tests-host-first]].

*References: device-tests-host-first*

*Observed 2026-10-21 (rust-ui-dev)*
