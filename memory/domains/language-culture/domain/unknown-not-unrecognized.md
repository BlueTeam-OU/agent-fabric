---
role: "language-culture"
class: domain
topic: "unknown-not-unrecognized"
description: "en word for a value the build does not know (status, role, enum, language, kind) — \"Unknown\", not \"Unrecognized\""
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c9feca3485c29e9f
---

## en word for a value the build does not know (status, role, enum, language, kind) — "Unknown", not "Unrecognized"

For a value that the build does not know (an enum value newer than the client: status, role, language, content kind), English uses "Unknown", not "Unrecognized". A cold read found that "Unrecognized" can read, to a reader of English as a second language, as something the system rejected or as an error that the reader caused. "Unknown" reads as a neutral value in a cell, in a badge and after a label ("Role: Unknown"). The same word is used in every portal (gzapp `operator.enum.unknown`, `common.enum.unknown`). The Russian holder reached the same answer on its own («Неизвестно», not «Не распознано»; domain slice unknown-enum-value-is-neizvestno).

**Why:** the reader of an unknown value has done nothing wrong. A word that suggests rejection makes them look for a fault that does not exist.

**How to apply:** when a draft says "Unrecognized", "Unsupported" or "Invalid" for a value that is only newer than the client, use "Unknown", and use it the same way in every surface.

*Observed 2026-10-15 (language-culture)*
