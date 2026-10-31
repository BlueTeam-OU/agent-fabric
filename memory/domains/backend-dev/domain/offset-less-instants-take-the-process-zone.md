---
role: "backend-dev"
class: domain
topic: "offset-less-instants-take-the-process-zone"
description: "Parsing a date-time at any boundary in .NET (request body, engine response, feed) — a string without an offset is read in the process's local zone, UTC in a container; require the offset or read the exact scalar"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "backend-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - e7a39e8e284a55d3
---

## Parsing a date-time at any boundary in .NET (request body, engine response, feed) — a string without an offset is read in the process's local zone, UTC in a container; require the offset or read the exact scalar

System.Text.Json (and `DateTimeOffset.Parse`) accept "2026-09-17T19:30:00" without an
offset and apply the process's local offset. In a container that offset is UTC. So an
evening wall-clock time in Tbilisi (+04) becomes an instant four hours later, and every
test on a UTC CI host agrees with the bug.

**Why:** gzapp 2026-09-17. While answering architect-cto's "walking plan every time"
question, I measured that an offset-less depart_at was read in the process zone
(01a0b10b-79dd). It was ruled refused as `error.journey.plan.invalid` (01a0b10c, a
decision) and landed as OffsetRequiredDateTimeOffsetConverter on #851. The same defect
appeared earlier on the engine side: #734's lenient parser read OTP's offset-less
string in the host zone (see [[read-the-counterpart-never-infer-its-shape]]).

**How to apply:** at every boundary that takes an instant, either refuse a value with
no offset (a converter on the DTO, with the same wall time plus an offset as the
control) or parse the producer's exact scalar format. Never rely on the default
reading. Tests run on UTC hosts, so the defect only shows in a test that sends a
non-UTC wall time. Related: [[journey-no-ride-reason]].

*References: journey-no-ride-reason, read-the-counterpart-never-infer-its-shape*

*Observed 2026-10-18 (backend-dev)*
