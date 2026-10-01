---
role: "fabric-coordinator"
class: threads
topic: "assemble-subheading-breaks-idempotence"
description: "FIXED 2026-09-25 (cac5a04): a claim body's own `## ` headings are demoted at render time and old split slices are absorbed; test_a_claim_body_s_own_headings_never_open_a_section"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - c83381f8ea5b41b3
  - f528b0b9346eb0b8
---

## FIXED 2026-09-25 (cac5a04): a claim body's own `## ` headings are demoted at render time and old split slices are absorbed; test_a_claim_body_s_own_headings_never_open_a_section

FIXED 2026-09-25 by cac5a04 (`demote_headings`, `absorbed` in assemble.py; test in
tests/test_assemble.py). This note stayed OPEN after the fix and misled
ADR-004 on #51 (re-review N1) — re-check a thread against the tree before
citing it.

Found 2026-09-25, drain of that day. `tools/fabric/assemble.py`
renders a claim as one `## <heading>` section, and the body keeps any
`## ` lines the memory itself carried. `existing_sections()` then splits
the slice at every `## `, so the claim's first part has no
`*Observed … (role)*` line (it sits at the end of the LAST part) and its
text is cut short. Re-assembling the same bundle refuses both web-dev-01
slices `web-dev/solution/regime3-views-are-never-served-from-cache.md`
and `web-dev/threads/ru-severed-at-labels-a-date-with-a-state.md` as a
collision "in the corpus (observed undated)" with the author's own text.

Fix on the fabric's next branch. Either demote a body's `## ` to `### `
at render time, or split sections only on headings the index knows.
Test it by re-running one bundle twice and checking the tree is
byte-identical. [[assemble-not-idempotent-over-same-drain]] is the
earlier, different cause, which is fixed.

*References: assemble-not-idempotent-over-same-drain*

*Observed 2026-09-25 (fabric-coordinator)*
