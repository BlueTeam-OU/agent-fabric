---
role: "fabric-coordinator"
class: solution
topic: "locale-lint-reads-sentence-verb-as-tool"
description: "A charter sentence that begins with a tool's name as a verb (\"Write the file...\") fails every locale rendering in lint: it counts the word as the tool name, which a translation rightly renders"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9890350d4beac198
---

## A charter sentence that begins with a tool's name as a verb ("Write the file...") fails every locale rendering in lint: it counts the word as the tool name, which a translation rightly renders

The locale lint counts each harness tool name (Write, Edit, Read, ...) in an English role file and requires the same count, byte-identical, in every rendering under `locale/<l>/`. It cannot tell a capitalised verb from the tool: "Write the file as a file edit" in the language-culture charter (d7adeb2f) made both the ge and ru renderings fail ("tool name 'Write' appears 0 time(s), 1 in the source"), in `tests/test_roots_readers.py`, `tests/test_project_import.py` (two `--like` cases) and the corpus lint. That is three suites from one word (j732, #551).

**Why:** the translators were right to translate the verb; the defect was the English.
**How to apply:** in a role file that has renderings, never start a sentence with a tool name used as a verb. When the tool is meant, name it ("with the Write tool") so the renderings carry it literally (fixed in 9ece67dd). Before folding renderings, run `lint.py --no-siblings` on the folded head. Related: [[locale-codes-say-the-language]].

*References: locale-codes-say-the-language*

*Anchors: `identities/roles/language-culture/charter.md::with the Write tool`*

*Observed 2026-11-10 (fabric-coordinator)*
