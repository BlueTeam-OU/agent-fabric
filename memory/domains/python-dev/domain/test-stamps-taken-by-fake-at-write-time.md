---
role: "python-dev"
class: domain
topic: "test-stamps-taken-by-fake-at-write-time"
description: a timestamp a test composes before launching the code under test is raced by host load; let the fake stamp it when it writes
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 345de8c9dde487f0
---

## a timestamp a test composes before launching the code under test is raced by host load; let the fake stamp it when it writes

test_launch_cli group 6 composed the upgrade marker's `requested_at` (now+1 s) before the launcher started; the launcher compares it with its own start (`at < started`), so a loaded host made the marker "older" and not obeyed (PR 286). Fix: the fake session stamps it with `date -u` when it writes the marker.

**Why:** fixed offsets in a test's pre-computed time measure the host's load, not the code.
**How to apply:** stamp inside the fake at write time; widen waits as conditions that leave early, and gate a wait on the thing it waits for existing (a fake shared by no-gateway runs otherwise runs to the full deadline, 78 s here). Reproduce with ~40 busy `python3 -c 'while True: pass'` loops.

*Observed 2026-10-16 (python-dev)*
