---
role: "python-dev"
class: domain
topic: "j193-zero-padded-length-cap"
description: "a digit-string length cap before int() must count the digits after leading zeros; one helper for every env var with the cap"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - da382e416b4f2723
---

## a digit-string length cap before int() must count the digits after leading zeros; one helper for every env var with the cap

A `len(have) >= 10` guard that keeps int() off a huge digit string misreads zero-padded values (0000000002 is 2, not "above any budget"). Strip leading zeros first, then cap; one helper (`_number_below` in tools/fabric/lease.py, j193 branch develop-qzapp/python-dev-01/for/user/j193-zero-padded-test-jobs) so every var with the cap (TEST_JOBS, CARGO_BUILD_JOBS, DOTNET_PROCESSOR_COUNT) agrees.

**Why:** #429 round-2 F6; the F3 fix had added the cap and broke the documented "0 is kept".
**How to apply:** when adding a length cap, test padded-below, padded-above and 5000-digit values; grep the file for the same cap spelled twice. Related: [[j192-cpu-child-env-f3]].

*References: j192-cpu-child-env-f3*

*Observed 2026-10-30 (python-dev)*
