---
role: "language-culture"
class: domain
topic: "instruction-doable-in-reader-situation"
description: "an instruction in UI text (driver band, heads-up, rider hint) must be something its reader can do where they are — at the wheel, at a glance, without opening the app"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9ff2e69c45504a8f
---

## an instruction in UI text (driver band, heads-up, rider hint) must be something its reader can do where they are — at the wheel, at a glance, without opening the app

Text that tells a reader to act is read in a situation, and the action must fit it. A driver reads the band at a glance, with both hands on the wheel. Two driver texts failed this in one day (gzapp#1119):
- "Look for them on the bus" at the dropoff asked the driver to search the bus from the wheel. The ru-RU holder's cold read found it, and the ruling changed to "ask out loud who is getting off".
- A heads-up body "The stop is shown in the app" was read by a cold reader as an instruction to open the app while driving.

**Why:** a writer checks whether the words are clear and true. Whether the reader can do the thing, where they are, is a different test. Neither the validator nor a reading of the words alone makes it.

**How to apply:** for each instruction, name the reader's situation (driving, walking, a screen reader, a glance), then ask: can they do this there, now, without another device or screen? If not, say so to the caller as a meaning question, because the action is the owner's. Give the cold reader the situation, not only the text.

Related: [[key-value-true-in-every-state]]

*References: key-value-true-in-every-state*

*Observed 2026-10-18 (language-culture)*
