---
role: "backend-dev"
class: domain
topic: "one-read-test-needs-a-moving-clock"
description: "How to write a test that pins \"one clock read per operation\" so it can actually fail"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "backend-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 8c611583ef77aead
---

## How to write a test that pins "one clock read per operation" so it can actually fail

An assertion that two stamps of one operation are equal cannot fail under a clock that holds still. Pin it with a test IWallClock that advances (e.g. 7 ms) on every read, bound only to IWallClock, and switched on only around the operation under test (JourneyCallSignMintTests.AdvancingWallClock, #1124).
**Why:** the earlier SELECT-equality check passed with two reads.
**How to apply:** run the test against a mutation that reads the clock twice; it must go red.

*Observed 2026-10-18 (backend-dev)*
