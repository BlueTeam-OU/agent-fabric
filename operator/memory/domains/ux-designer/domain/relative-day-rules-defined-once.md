---
role: "ux-designer"
class: domain
topic: "relative-day-rules-defined-once"
description: "A relative-date rule (Today, Yesterday, weekday) is defined once with its unit (calendar days, the device's time zone) and its future case; other sections refer to it, and every reference is true for every value"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 18217d72a0dfc7af
---

## A relative-date rule (Today, Yesterday, weekday) is defined once with its unit (calendar days, the device's time zone) and its future case; other sections refer to it, and every reference is true for every value

"Within the last seven days" and "two to six days old" read as 24-hour
periods or calendar days, and as one rule or two. A timestamp later
than now (a clock set back) falls in no bucket unless the rule says so.
Restating the rule in several sections let them drift, and references
like "in section 5.2's words" were false for one of the values.
**Why:** InterWeave android-look spec (#300, 2026-10-18): four review
and wording rounds each found one of these (F4, F5, F6, the future-time
P3); the build already used calendar days 0/1/2..6 in the phone's zone
and mapped the future to Today.
**How to apply:** define day buckets once: unit (calendar days in the
device's time zone), each bucket's range, and "a time later than now
counts as today". Elsewhere write "counted as in §N". Before writing
"as §N says", check the reference holds for every value it covers.
Related: [[thresholds-as-formulas]]

*References: thresholds-as-formulas*

*Observed 2026-10-22 (ux-designer)*
