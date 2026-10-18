---
role: "devex-tooling"
class: solution
topic: "ots-signing-flaky-retry"
description: "git commit fails \"ots: need at least 2 attestations\" — the OpenTimestamps calendars are slow, retry the commit"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a6cce8dba9ca5269
---

## git commit fails "ots: need at least 2 attestations" — the OpenTimestamps calendars are slow, retry the commit

On develop-qzapp, commit signing adds an OpenTimestamps stamp; `git commit` fails with
"ots: Failed to create timestamp: need at least 2 attestations but received 0|1 within timeout" /
"fatal: failed to write commit object" when the calendars answer slowly. The calendars were
reachable (curl HTTP 200) and the second retry succeeded (2026-10-13, 7d6583d9).

**How to apply:** keep the message in a scratchpad file and retry `git commit -F` a few times before
diagnosing the network or the sandbox.

*Observed 2026-10-13 (devex-tooling)*
