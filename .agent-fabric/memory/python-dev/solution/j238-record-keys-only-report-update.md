---
role: "python-dev"
class: solution
topic: "j238-record-keys-only-report-update"
description: "re-home pass writing agent-fabric's drain report — merge_reports' other-stamp/none paths leak stamp+telemetry; write record keys only, refuse unreadable up front (j227 F6/F7)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1e024ff7c0aaaf14
---

## re-home pass writing agent-fabric's drain report — merge_reports' other-stamp/none paths leak stamp+telemetry; write record keys only, refuse unreadable up front (j227 F6/F7)

`record_rehomed` (tools/fabric/assembler/report.py) must not take merge_reports' whole result for a report the pass does not own: other-stamp keeps only watermarks+record, an absent report gets the drained project's stamp and roles' telemetry. Write REHOME_RECORD_KEYS (+`project` when absent) only; decisions merge by key and retitles append (merge_reports' other-stamp branch replaces both); unreadable/non-object report = refuse in `rehome()` BEFORE the pass writes, not treated as absent.

**Why:** reviewer rounds 2 and 3 of #589 found the same class twice (a fix for one path left two).
**How to apply:** when a merge helper has stamp-dependent branches, enumerate every branch (same stamp, other stamp, none, unreadable) in tests. Round 3 patch was left at the j239 scratchpad (j239.diff) because the job guard blocked the commit in the j238 session — see [[job-guard-literal-path-and-review-post-order]].

*References: job-guard-literal-path-and-review-post-order*

*Observed 2026-11-13 (python-dev)*
