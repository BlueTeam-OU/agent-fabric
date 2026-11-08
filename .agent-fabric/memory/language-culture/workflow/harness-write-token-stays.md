---
role: "language-culture"
class: workflow
topic: "harness-write-token-stays"
description: "In ru/harness.md keep \"Пиши (Write) код\": lint counts the source's verb \"Write code\" as a tool-name token"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric-j101-russian-harness-md-lags-harness-en"
derived_from:
  - df03ac64d261b1bb
---

## In ru/harness.md keep "Пиши (Write) код": lint counts the source's verb "Write code" as a tool-name token

`lint.py --tokens` counts "Write" twice in harness/en.md: the verb in "Write code that reads like…" and the Write tool. ru/harness.md therefore keeps "Пиши (Write) код", because dropping it fails lint (1 against 2). In the j101 re-render (7a1c8dd2, 2026-11-08) the locale-worker first pass flagged it, and the second pass withdrew that finding. To check a re-render, diff the `--tokens` output of the translation against the source's. The `translates_digest` value comes from `lint.py --digest <en.md>`, which hashes the body, not the whole file.

*References: locale-tags-byte-identical*

*Anchors: `identities/roles/language-culture/locale/ru/harness.md::Пиши (Write) код`*

*Observed 2026-11-08 (language-culture)*
