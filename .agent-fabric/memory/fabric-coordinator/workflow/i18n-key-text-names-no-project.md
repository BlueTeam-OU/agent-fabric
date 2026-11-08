---
role: "fabric-coordinator"
class: workflow
topic: "i18n-key-text-names-no-project"
description: "en-US key text I hand a requester or the locale holders must name no managed project (InterWeave etc.) — lint refuses it in generic files, in every locale"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b22dcd09dcd26530
---

## en-US key text I hand a requester or the locale holders must name no managed project (InterWeave etc.) — lint refuses it in generic files, in every locale

A message string in `communication/gzcoord/i18n/en-US.json` or a locale's
`<tag>.json` is a generic file: `tools/fabric/lint.py` refuses a managed
project's name there ("InterWeave"), and `tests/test_roots_readers.py` and
`tests/test_project_import.py` go red. j116's `send.carrier-took-it` said
"the InterWeave carrier"; the translators kept the brand byte for byte as
asked, so one wording cost three commits and two locale round trips (j635,
en-US fix 72ae95e6, ru/ka asked of language-culture-ru and -ge).

**Why:** the translators copy a name as given; the lint catches it only after
all three locales landed.
**How to apply:** before sending en-US key text to python-dev or the locale
holders, say "the carrier", "the relay", never a project's name; the en-US
line is mine to change, ru-RU/ka-GE only by their holders' commits.

*Anchors: `communication/gzcoord/i18n/en-US.json::send.carrier-took-it`*

*Observed 2026-11-07 (fabric-coordinator)*
