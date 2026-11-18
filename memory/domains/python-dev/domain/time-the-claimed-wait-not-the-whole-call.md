---
role: "python-dev"
class: domain
topic: "time-the-claimed-wait-not-the-whole-call"
description: "j116 #580 — a timing bound on a cleanup case must wrap only the waits it claims; wrap the module's wait function, record (bound, elapsed)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 61406425c43cfec7
---

## j116 #580 — a timing bound on a cleanup case must wrap only the waits it claims; wrap the module's wait function, record (bound, elapsed)

A test that bounded all of `cleanup()` by grace + KILL wait + 2 flaked on CI (8.4 s vs 8 s) because git removals after the waits counted too. Wrap the module-level wait function (`tw.wait_ended`) for one call, record `(requested bound, elapsed)`, assert the list of bounds and bound only the summed elapsed.

**Why:** a member that dies at once cannot show how long the KILL wait is, so pin the argument (patch both constants to distinct values, e.g. 1.0 and 2.5, so a literal at the call site fails) and the elapsed upper bound. A production constant's value stays out of the test's reach once the test overrides it; say so when deferring.

**How to apply:** mutate removal, doubling, a literal, and a lengthened grace; read each run's FAIL line for the new check, not only rc. Second open PR of mine was allowed as the CI-blocking-fix exception, said in its body; arm minimum was 1 (dry-run).

*Observed 2026-11-13 (python-dev)*
