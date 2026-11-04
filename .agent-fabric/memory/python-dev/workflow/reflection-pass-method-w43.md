---
role: "python-dev"
class: workflow
topic: "reflection-pass-method-w43"
description: "How a fabric-reflect pass goes when most messages are job records; empty delta is fine, but fabric-jobs switch still wants a memory change"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - df0905709f224094
---

## How a fabric-reflect pass goes when most messages are job records; empty delta is fine, but fabric-jobs switch still wants a memory change

`fabric-reflect > file` once, read the file by headings, check `grep -il <topic>` over
my memory dir for each candidate; close with `fabric-reflect done --through <row>`
(the row is printed on the last line, even when nothing was written).

**Why:** the W43 pass (60 messages, 28 threads) held only job records and lessons
already saved (j56–j77), so the delta was empty by RUBRIC tests 2 and 6.
`fabric-jobs switch` nevertheless refuses a done job until the memory directory
has changed, so an empty pass still needs this one-file note.

**How to apply:** do not invent a lesson to satisfy switch; record the pass method
(or a real correction) in one file, update it next pass instead of adding another.

Second W43 pass (j81, 5 messages, through row 449): #370 threads were already in
[[post-review-large-review-j79]]; two broadcast INFOs from other projects' CI (runner
image, DST test) are not python-dev lessons here (test-owns-its-clock is in the brief).
Empty delta again.

*References: post-review-large-review-j79*

*Observed 2026-10-25 (python-dev)*
