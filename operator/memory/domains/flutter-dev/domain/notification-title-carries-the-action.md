---
role: "flutter-dev"
class: domain
topic: "notification-title-carries-the-action"
description: A notification whose variant asks the reader to act needs its own title, not only its own body — a lock screen or collapsed shade may show the title alone
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "flutter-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1eee4470135dd235
---

## A notification whose variant asks the reader to act needs its own title, not only its own body — a lock screen or collapsed shade may show the title alone

An Android/iOS notification is often read as its title alone: on a lock
screen with content hidden, in a collapsed group, on a watch. So when
one notification has a variant that asks the reader to DO something
(the base says "your stop is close", the variant must also say "ask the
driver to stop"), the variant is a title-and-body pair, never a body
under the shared title — a reader who sees only the shared title does
not act.

Learned twice on gzapp's journey wake (2026-10-19/20): a language-culture
cold read found the shared alighting title gave no hint of the ask, and
the boarding variant needed the same; ADR-077 §2.4 was amended to say
"a variant title and body … the title too, since a lock screen may show
it alone", and the keys are `journey.wake.{boarding,alighting}.title-on-request`
beside the `body-on-request` ones.

**How to apply:** when a notification (or any surface that can be
truncated to its first line) gets a variant, decide per field — title,
body, any action label — whether it must differ; if the variant carries
an action, the title carries it. Take the pair whole at render time, so
a words file lacking the variant falls back to the base pair, never to
a mixed or empty one. Brief the copy holders with "may be read alone"
for the title. Related: [[settle-meaning-before-copy-request-strengthened]].

*References: settle-meaning-before-copy-request-strengthened*

*Observed 2026-10-24 (flutter-dev)*
