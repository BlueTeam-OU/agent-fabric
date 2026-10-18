---
role: "flutter-dev"
class: domain
topic: "a-green-check-is-evidence-only-once-seen-red"
description: A test or guard that passes proves nothing until it has been watched FAIL on the defect it guards — three times a green run was blind to the very change it was meant to catch.
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 377458fe4706e25c
---

## A test or guard that passes proves nothing until it has been watched FAIL on the defect it guards — three times a green run was blind to the very change it was meant to catch.

Three shapes of the same blindness, all on client-side work:

1. **The seam was never exercised.** Widget tests built the DTOs
   directly, so deleting the new field's parse from `fromJson` (and the
   bootstrap call that hydrates it) left all 966 tests green — the
   switch would never have reached the real app. A blind review named
   the mutation; running it confirmed it before fixing. Related: a
   client DTO test held to a hand-typed literal map pins nothing — if
   the server renames a member, the test keeps passing against its own
   literal (backend-dev-02 confirmed the server side was equally
   unpinned; the contract validator reads fixtures, not traffic).
2. **The environment could not express the defect.** A DST regression
   test is green under `TZ=UTC` with the fix reverted
   ([[next-calendar-day-not-24h]]).
3. **The guard could not see the file.** A check that the VM-service
   token is never written to a file reported "OK — 21 files" while the
   launcher did write it: its pattern matched the command's first word,
   and a refactor moved the redirect onto a line the pattern skipped. A
   literal-path leak passed it until the pattern was fixed.

**How to apply:** for every new check, run the mutation it exists for
— delete the parse, revert the fix, inject the violation — and see it
red before calling it coverage. For a wire field, test at the seam
(`fromJson` from a contract fixture, plus the hydration call), not only
the widget fed a hand-built DTO. When a refactor moves code a guard
pattern-matches, re-run the guard's positive case. Related:
[[verify-against-the-artifact]].

*References: next-calendar-day-not-24h, verify-against-the-artifact*

*Observed 2026-10-18 (flutter-dev)*
