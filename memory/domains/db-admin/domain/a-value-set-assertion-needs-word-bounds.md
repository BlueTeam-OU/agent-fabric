---
role: "db-admin"
class: domain
topic: "a-value-set-assertion-needs-word-bounds"
description: "Assert.Contains is a substring test, so a closed-set assertion can be satisfied by another member of the set; and \\b is wrong for snake_case values."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - bd5c23ab78765f52
---

## Assert.Contains is a substring test, so a closed-set assertion can be satisfied by another member of the set; and \b is wrong for snake_case values.

When a test pins that a column comment (or any text) names every value of
a closed set, `Assert.Contains(value, text)` is a **substring** assertion,
so one member can satisfy the assertion for another. On
`driver_staff.status` the set is `active | inactive | severed |
pending_approval | rejected`, and the case for `active` could never fail
because `inactive` contains it — the blind review of #887 caught it, and
the loop had looked obviously correct to me when I wrote it.

`\b` is NOT the fix here: `_` is a word character, so `\bapproval\b`
matches inside `pending_approval`. Guard on the value characters instead:
`(?<![a-z_])<value>(?![a-z_])`.

The control that shows the fix is live: rewrite the value to something
else *everywhere it stands as a word* and re-run — under `Assert.Contains`
the case still passed, because the containing value was still in the text.
See [[verify-the-mutation-fired]]; the same "both print Passed!" trap.

`apps/backend_dotnet/tests/Gzapp.DriverApi.Tests/DriverStaffStatusConstraintTests.cs`,
commit c9bdf277 on #887.

*References: verify-the-mutation-fired*

*Observed 2026-09-18 (db-admin)*
