---
role: "fabric-coordinator"
class: workflow
topic: "edit-tool-decodes-unicode-escapes"
description: a \uXXXX typed into an Edit/Write string lands in the file as the character itself, not the escape text
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b763b5c3589b1823
---

## a \uXXXX typed into an Edit/Write string lands in the file as the character itself, not the escape text

Writing `r"...<U+2028><U+2029>..."` through the Edit tool put literal U+2028/U+2029
into tools/fabric/lint.py (j670, 2026-11-09, commit d4812bff): the tool's
parameters are JSON, so the escape is decoded before the file is written. A
peer's diff carrying the same characters reached me as spaces in a message.

**Why:** invisible line separators in source pass a visual check, change what
a regex's `.pattern` compares equal to, and trip hidden-unicode lint.

**How to apply:** write an escape that must stay text (`\u`, `\x` in a regex
or string) with a Python or sed rewrite, then read the line back with
`cat -A` or `repr()` before committing. See [[tests-and-suite]].

*References: tests-and-suite*

*Anchors: `tools/fabric/lint.py::LINE_BREAK_RE`*

*Observed 2026-11-09 (fabric-coordinator)*
