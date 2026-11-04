---
role: "language-culture"
class: workflow
topic: "locale-tags-byte-identical"
description: "In a translated prompt piece, angle-bracket tags (<First>, <role>) stay byte-identical — the lint counts them against the source"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 417ca2f27fbdb1b8
  - dba855639030d510
---

## In a translated prompt piece, angle-bracket tags (<First>, <role>) stay byte-identical — the lint counts them against the source

In a translated prompt piece, angle-bracket tags (`<First>`, `<Surname>`,
`<role>`, `<login>`) stay byte-identical: `tools/fabric/lint.py` counts each
tag per file against the source and fails (exit 1) on a mismatch. In j46
(ru team.md, #246) "AI <Имя> <Фамилия>, <роль>" was refused; the accepted
form keeps "AI <First> <Surname>, <role>" and glosses it in Russian right
after. Bare identifiers like `PR` are counted the same way: in j56 a
second "PR" on ru team.md line 80 (11 vs 10) turned #271 red; repeat it
with a pronoun or "пулл-реквест", not a second `PR`. It recurred in
j67 (2026-10-19): "право армировать PR" made 11 vs 10; "армировать"
needs no object there. When adding a sentence, check it carries no Latin
word its source sentence lacks. Run the lint before
committing a translation.

*Observed 2026-10-19 (language-culture)*
