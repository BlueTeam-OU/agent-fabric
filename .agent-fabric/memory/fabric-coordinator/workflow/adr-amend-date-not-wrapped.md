---
role: "fabric-coordinator"
class: workflow
topic: "adr-amend-date-not-wrapped"
description: "an \"(A YYYY-MM-DD)\" mark in an agent-fabric ADR's §5 fails \"§5 dates something\" when \"(A\" and the date wrap, or when the A follows other text in the parenthesis, or two dates share one"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f469ceebd9d34cbb
---

## an "(A YYYY-MM-DD)" mark in an agent-fabric ADR's §5 fails "§5 dates something" when "(A" and the date wrap, or when the A follows other text in the parenthesis, or two dates share one

In agent-fabric's ADR §1–§8, the amendment mark `(A 2026-11-10)` passes `tests/test_adr.py` (case_the_real_records_are_clean) only when
"(A" and the date are on the same line. Wrapped as "(A\n 2026-11-10)", the date reads as a bare one and is refused with "§5 dates
something — a record reads current". Seen on PR #545 (ADR-037, j710). After the body edit, `python3 tools/fabric/adr.py index --write`
regenerates index.json and the README table; then run `tests/test_adr.py` with AGENT_FABRIC_ROOT=$PWD. Related: [[adr-range-check-before-push]].

The mark must open its parenthesis: `(rule 14, A 2026-11-11)` was refused the same way on #556 (j769); `... by rule 14 (A 2026-11-11)` passed. `python3 tools/fabric/adr.py --root . check` names it in a second, before the test.

One date per parenthesis: `(A 2026-11-13, A 2026-11-14)` was refused for both dates on #595 (j853). A clause added by a later amendment either takes its own `(A …)` where it stands or stays under the earlier mark.

*References: adr-range-check-before-push*

*Anchors: `tools/fabric/adr.py::dates something`*

*Observed 2026-11-14 (fabric-coordinator)*
