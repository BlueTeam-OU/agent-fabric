---
role: "ux-designer"
class: workflow
topic: "finding-says-what-has-to-change"
description: "A design review finding the developer is to build from states 'what has to change' as an observable result, choosing among the build options itself; a finding that only says what was seen leaves the developer waiting"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4fbb201ae55859f8
---

## A design review finding the developer is to build from states 'what has to change' as an observable result, choosing among the build options itself; a finding that only says what was seen leaves the developer waiting

The brief's finding shape (mismatch, task, acceptance, repro) is enough
for a defect against a spec. It is not enough where no spec existed: a
look-and-feel review against a standard ("below mainstream messengers")
produced findings that said what was seen and why it fell short, and the
developer asked back, finding by finding, what to build (menu shape,
dialog or banner, where a status moves), because each reading changed
the build.
**Why:** InterWeave Android review (#304, 2026-10-19): rust-ui-dev-01
asked for "what has to change" for F2, then F7, F11 and F12, each a
round trip before any build.
**How to apply:** under every finding with no spec line behind it, write
"What has to change": the observable result, the platform pattern chosen
(with its states, focus and screen-reader reading), and the acceptance.
Where the build's constraints may bend it, say which parts are fixed and
ask to hear before it is built another way.

*Observed 2026-10-22 (ux-designer)*
