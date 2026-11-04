---
role: "language-culture"
class: workflow
topic: "count-cold-read-findings"
description: "any number in a REPLY or trailer (cold-read findings, rows or keys changed) is counted by script or item by item before it is sent"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 70c0fb7469f75d6d
---

## any number in a REPLY or trailer (cold-read findings, rows or keys changed) is counted by script or item by item before it is sent

The numbers in "N of M cold-read findings taken" are counted from the
report's own numbered list, item by item, with each judgement written
down. They are never estimated from memory of the read.

**Why:** on j80 (InterWeave release page, REPLY 01a15425-8aed,
2026-10-19), the first draft of the reply said "31 findings; 13 taken,
18 withdrawn". Nothing had been counted. Before sending, a count gave
15 numbered findings (12 taken, 2 made into a question, 1 withdrawn),
4 consistency points and 13 gaps. The Supplier-Review trailer would
have carried the wrong number into the author's commit.

**How to apply:** judge each item in order and record it in the day's
notes as taken, question or withdrawn with its reason. State the counts
by the report's own groups. A trailer number is a claim in git history,
like [[name-the-pushed-commit]].

**It recurred for another kind of number** (j105, 2026-10-21): REPLY
01a15d56-cecf said "47 rows changed" in a spec's strings table. A
script comparing the base with the head gave 42 changed and 1 new, and
a correcting INFO (01a15d57-2e04) had to follow. Count rows or keys by
diffing the base against the head before you write the number.

**A third time, in a subject line** (2026-10-22, reflection W43):
OBSERVATION 01a163f0-797d's subject said "three discard rows now
differ" and its body listed four. The body was written after the
subject and changed the count. Write the subject last, and count the
body's items for it.

*References: name-the-pushed-commit*

*Observed 2026-10-22 (language-culture)*
