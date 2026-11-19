---
role: "python-dev"
class: workflow
topic: "j240-refusal-screen-merged-591"
description: "Screen text before repr/cut in refusal messages; arm --dry-run shows the count rule before asking for words; short review brief by file path (j240, #591)"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 14f9861f4afa18ac
---

## Screen text before repr/cut in refusal messages; arm --dry-run shows the count rule before asking for words; short review brief by file path (j240, #591)

#591 merged 2026-11-14 (1 work, 2 fix, 1 merge): read_claims refusals print distiller text only through `shown()` = `repr(screened(text))`.

- Screen the RAW text, then repr, then cut: repr escapes quote/tab/backslash and a 60-char cut leaves a hit shorter than its pattern; both let a credential through (review F1, round 2).
- A role id the ROLE_ID regex admits can itself be a banned word; screen role/owner/class in every refusal, including rehome_unbound.
- `fabric-pr arm --dry-run --basis ...` prints the count rule first: here "1 work commits — 1 or more, arms at the review gate". I asked the coordinator for an AUTHORIZES that was not needed; read the dry run before asking.
- A review dispatch brief can be the dispatch header plus "read this brief file in full" (15 KB re-review brief); the review ran fine and post-review accepted its report.
- `fabric-review next` for round 3 takes the previous round's rr json (req-...-rr3.json), not the original request.

**Why:** saves a wrong ask and a missed-screen class.
**How to apply:** any new stderr/log message built from untrusted fields: screen, quote, then truncate.

*Anchors: `tools/fabric/assembler/intake.py::def shown`*

*Observed 2026-11-14 (python-dev)*
