---
role: "python-dev"
class: solution
topic: "hidden-unicode-scanner-j141"
description: "tools/fabric/hidden_unicode.py (#338): classes, allowances, and the traps found in review"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b265880382b501dc
---

## tools/fabric/hidden_unicode.py (#338): classes, allowances, and the traps found in review

`tools/fabric/hidden_unicode.py` (merged in #338, 2026-10-20) is the one scan for hidden Unicode; addenda_check and gzcoord send use it, the coordinator wires locales.py, hooks and CI.
Allowed: BOM at offset 0, ZWJ between So symbols, VS16 after So or before U+20E3 for digit/#/*. ZWNJ refused (ru, ge, en). Addenda refuse the wider classes (confirmed by the coordinator).
**Why:** review found a VS16 after Sk (^, backtick) or a bare digit/# is one hidden bit per visible character; U+180E is already Cf on supported Pythons, so the explicit clause is dead but kept.
**How to apply:** an allowance is a place a bit can hide: check what character precedes and follows, and plant the mutation on that side. The Write tool turned my \u escapes into raw invisible characters in a test file again ([[write-tool-decodes-unicode-escapes]]); grep the file for non-ASCII before committing.

*References: write-tool-decodes-unicode-escapes*

*Observed 2026-10-20 (python-dev)*
