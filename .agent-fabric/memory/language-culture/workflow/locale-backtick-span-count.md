---
role: "language-culture"
class: workflow
topic: "locale-backtick-span-count"
description: a backticked span in a prompt translation must appear exactly as often as in its source; lint counts it
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8ee9c5a949601c08
---

## a backticked span in a prompt translation must appear exactly as often as in its source; lint counts it

The corpus lint (`tools/fabric/lint.py`) counts every backticked span in a prompt translation against its source: if `memory_find` appears once in the source and twice in the translation, lint fails ("an identifier … stays byte-identical"), and test_roots_readers in tests/run.sh fails with it. To clear up an ambiguous pronoun, do not repeat the identifier; describe it in words. Found on j54, 2026-10-14, locale/ge/memory.md, e6a32459. Re-run the lint after applying cold-read fixes, before delivering.

*Observed 2026-10-13 (language-culture)*
