---
role: "python-dev"
class: solution
topic: "j118-oversized-by-origin-merged"
description: "j118 PR 493 merged (36976b2e) — assembler oversized_by_origin; drop_held dict traps, post-review header cut, re-review brief has no previous_findings"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 452ecbbcf4ce1990
---

## j118 PR 493 merged (36976b2e) — assembler oversized_by_origin; drop_held dict traps, post-review header cut, re-review brief has no previous_findings

PR 493 merged 2026-11-05: assembler report gains `oversized_claim_details` (in REPORT_LISTS, merged per stamp) and derived `oversized_by_origin` (computed after drop_held).

**Why/traps:** drop_held's regexes need a trailing char after the slice key, so a dict record must match its "slice" exactly; derived keys must be computed after drop_held. Remaining: source_file is `<frontmatter name>.md` (F2 P3 deferred); write_shared never checks oversized claims.
**How to apply:** a posted-review file needs the first 20 lines of the brief (dispatch header through closing fence); a PR re-review request must omit previous_findings; fabric-pr arm --defer "<head8>:F<n>" lifts an open P3 chain finding; commit alone (hook refuses commit chained with $HOME commands).

*Observed 2026-11-05 (python-dev)*
