---
role: "db-admin"
class: domain
topic: "a-day-interval-is-not-24-hours"
description: "Before adding an hour-bound CHECK over timestamptz stamps, grep writers for 'N days' intervals — they are calendar arithmetic in the session TimeZone."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 5e64b835c11420c4
---

## Before adding an hour-bound CHECK over timestamptz stamps, grep writers for 'N days' intervals — they are calendar arithmetic in the session TimeZone.

`timestamptz + interval '3 days'` adds calendar days in the session's TimeZone: across the autumn DST change it is 73 h, across the spring change 71 h. An hour-denominated CHECK (`delete_after <= terminal_at + interval '72 hours'`, gzapp 0019, #1140) therefore refuses a day-stamped writer in a non-UTC session only, a few days a year — UTC CI never sees it.

**Why:** the round-1 blind review of gzapp#1140 caught three test fixtures stamping `+ interval '3 days'`; reproduced on postgres:18 with `SET LOCAL TimeZone='Europe/Rome'`.

**How to apply:** when a bound is in hours, grep every writer (src and tests) for `interval '<n> day`, `mon`, `make_interval(days`, and move them to hours; C# `TimeSpan`/`AddHours` are absolute and safe. Probe both DST directions when stating the effect in a comment. Related: [[a-wrong-reason-in-a-comment-is-an-untested-axis]].

*References: a-wrong-reason-in-a-comment-is-an-untested-axis*

*Observed 2026-10-19 (db-admin)*
