---
role: "python-dev"
class: solution
topic: "assemble-test-failure-must-reach-report"
description: "testing that a failed assemble.py drain does something (or nothing) after report(): which fixtures actually reach it"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1b0a33bba8f418f2
---

## testing that a failed assemble.py drain does something (or nothing) after report(): which fixtures actually reach it

A test of "a failed drain does X after the report" in tests/test_assemble.py needs a run that exits 1 from report() itself. An undecided collision, a domain-only refusal and similar exit earlier in main(), so a mutation moving the write past the exit check survives them. A body in Italian (three distinct ITALIAN_MARKERS words) is rejected by hygiene_check and reaches report(); a city name from the fixture's hygiene list is only redacted and exits 0. Seen on j49 (PR 305): the first failed-drain test passed with the mutation planted.

**Why:** a negative test with the wrong failure path is green whatever the code does.
**How to apply:** pair such a case with a positive control (the same drain minus the bad claim), and check the mutation fails it.

*Observed 2026-10-19 (python-dev)*
