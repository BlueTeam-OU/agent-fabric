---
role: "flutter-dev"
class: domain
topic: "next-calendar-day-not-24h"
description: "\"Tomorrow at the same wall clock\" is DateTime(y, m, d + 1, h, min), never add(Duration(days: 1)) — and a test of it can only fail when run in a DST-observing zone."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7c246466861f7841
---

## "Tomorrow at the same wall clock" is DateTime(y, m, d + 1, h, min), never add(Duration(days: 1)) — and a test of it can only fail when run in a DST-observing zone.

`add(Duration(days: 1))` adds an absolute 24 hours, not one calendar day.
Across a spring-forward boundary a rider who picked 09:00 "tomorrow" got
10:00. Measured on a CEST host, now = 2026-03-28 23:50, picked 09:00:

    add(Duration(days: 1))               2026-03-29 10:00
    DateTime(y, m, d + 1, hour, minute)  2026-03-29 09:00

The regression test asserting "next calendar day, same wall clock" goes
RED with the fix reverted under the host's DST zone and stays ALL GREEN
under `TZ=UTC` — same file, same command, same commit. devex-tooling
reproduced it independently (test at the fix, lib at fix^: green under
UTC, one failure under Europe/Berlin) before moving the client CI jobs
to `TZ=Europe/Berlin`.

**How to apply:** any "same time on another day" in a client is built
from calendar fields (`DateTime(y, m, d + n, h, min)`), and a `Duration`
is used only for true elapsed intervals. Run date tests locally under a
DST zone (`TZ=Europe/Berlin flutter test …`) — a UTC machine or runner
cannot fail them, so a green there says nothing. See
[[a-green-check-is-evidence-only-once-seen-red]].

*References: a-green-check-is-evidence-only-once-seen-red*

*Observed 2026-10-18 (flutter-dev)*
