---
role: "language-culture"
class: workflow
topic: "safeguard-stop-on-worker-blocks-job"
description: "the model's safeguard stopped the worker: do not resend the text reworded, block the job"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 81c6bf8c468ae276
---

## the model's safeguard stopped the worker: do not resend the text reworded, block the job

During the cold read of the charter's notes paragraph (locale/ge/charter.md, lines 133–155), the model's safeguards stopped the locale-worker twice, tagged reasoning_extraction (2026-10-18 and 2026-10-19, j99). The paragraph describes how the harness stores thinking blocks.

**Why:** rewording the text to get it past the safeguard would be circumventing the safeguard. And I cannot stand in for the cold read of my own fix.
**How to apply:** after a safeguard stop, block the job. Give fabric-coordinator the job, file, lines, tag and request id, without quoting the text. They and the owner decide how it goes on.

*References: locale-worker-missing-after-upgrade*

*Observed 2026-11-09 (language-culture)*
