---
role: "python-dev"
class: workflow
topic: "j200-docstring-merged-457"
description: "j200 merged in #457; re-review mechanics that cost retries (save round first, pin the head, brief from the -rr2.json)"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2197be307dbf80b6
---

## j200 merged in #457; re-review mechanics that cost retries (save round first, pin the head, brief from the -rr2.json)

j200 (carrier_install docstring: the read reports the reserved_ports status, the start's refusal names `fabric-host <host> persist`, the step fixes not-covered only) merged as #457 on the owner's word with 1 work, 1 fix.

**Why:** the refusal still names persist for an unreadable live value, pinned by test_control_carrier_install.py; round 1 found the test pinned only the parse case, so the fix was an assertion for the unreadable-file case.

**How to apply:** for a round 2, `fabric-review save <pr> 1 < report` first, then the request's `range:` must name pinned shas (not `HEAD`), `fabric-review next` writes `<req>-rr2.json` (brief that file, not the stdout); post-review is the bare command with the report in a file; arm basis must say "on the owner's word". A first `git commit -a` with a heredoc message failed with "failed to write commit object"; `-F file` worked.

*Anchors: `tools/fabric/review_rounds.py::pinned`*

*Observed 2026-11-02 (python-dev)*
