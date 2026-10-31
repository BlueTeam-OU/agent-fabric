---
role: "p2p-network-dev"
class: workflow
topic: "re-run-recorded-measurements-at-the-final-head"
description: "A measurement recorded as a gate's proof counts only if it ran at code carrying every review fix: re-run at the final runtime head, commit the log naming that pin, and say which later commits touch only comments or tests"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0f34fa64b80d40b5
---

## A measurement recorded as a gate's proof counts only if it ran at code carrying every review fix: re-run at the final runtime head, commit the log naming that pin, and say which later commits touch only comments or tests

InterWeave #129 (2026-09-26): the interface-change and early-reservation rows
had been recorded at 680bbe10, before the review fixes; I listed that as
NOT-VERIFIED in the delivery, the architecture owner asked for a re-run, and
only the re-run at pin 36fd72a2 (the parent of log commit 3e3edb4d,
carrying every fix, replacing the earlier log) was taken as the row's proof.
The two commits after the pin were declared comment- and test-only, which is
what let the pin stand for the PR head.

**How to apply:** after the last review fix that touches runtime code,
re-run every recorded row the PR claims, commit the log with the pin it ran
at, and state in the delivery that nothing after the pin changes runtime
code — or re-run again. A row measured earlier is history, not evidence.
Related: [[a-behaviour-change-sweeps-the-prose-that-names-it]].

*References: a-behaviour-change-sweeps-the-prose-that-names-it*

*Observed 2026-10-18 (p2p-network-dev)*
