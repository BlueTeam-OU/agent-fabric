---
role: "rust-ui-dev"
class: domain
topic: "platform-copy-per-situation"
description: "One shared UI text table across desktop and mobile when the remedy differs by platform -- one key per situation, per-platform values chosen at the composition root"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6be4a4c7a49ea172
---

## One shared UI text table across desktop and mobile when the remedy differs by platform -- one key per situation, per-platform values chosen at the composition root

When a shared core's texts name something one platform has and another lacks (a separate
"transport daemon" on desktop, an in-app service on Android), do not reach for one neutral
word: the texts carry the recovery step, and the step differs. Keep one key per situation,
give it a value per platform, and select the platform table once at each app's composition
root, so no view branches on platform and an exhaustive match makes a missing platform text
a compile error. Before asking the copy owner for a platform's text, confirm the state is
reachable on that platform (a version-skew error cannot occur when app and runtime ship as
one build), so nobody writes text for a state that cannot happen.

The same goes for one word used in two situations on the same platform. A state's label is not
the text that announces an event: a snackbar names what just happened, so "Canceled" (a row's
state) reads wrong after a Cancel, and the copy owner gave it its own key ("Sending canceled").
An event text must also be true on every path that shows it: "Restored" was false after an Undo
of Keep, which restores nothing, so it became "Action undone". When a text is reused across
paths, list the paths for the copy owner rather than the key.

*Observed 2026-10-18 (rust-ui-dev)*
