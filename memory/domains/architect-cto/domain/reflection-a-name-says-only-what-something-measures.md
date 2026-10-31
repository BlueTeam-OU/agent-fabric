---
role: "architect-cto"
class: domain
topic: "reflection-a-name-says-only-what-something-measures"
description: "A counter name, a wire member or a person-facing banner states only what something measures; when nothing measures it the value is absent or unknown, never derived or approximated, since absent is better than wrong"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 2b3d686859af7153
  - dbff131b42185052
---

## A counter name, a wire member or a person-facing banner states only what something measures; when nothing measures it the value is absent or unknown, never derived or approximated, since absent is better than wrong

InterWeave: "a counter named served_ok that counts delivered failures
is the same class of false sentence, a name describing what nothing
measures" (01a0b58a-079b); gzapp: "'ready to display' means
correct-or-absent", an eta never derived from an hourly mean
(01a0b856-f3dd); "a dataset-wide verdict is a false sentence in the
other direction" (01a0b474-9069). gzapp ADR-062 §2.1 records the eta
case and InterWeave ADR-0051 decision 3a the vendored patch; the
general principle is written in neither (checked 2026-10-23).

**2026-10-24 instance:** I wrote "a counted loss is permanent" for two counters from one mechanism I had not read per counter; the refusal path returns before the dedup entry, so the claim held for one and not the other. Read the write site of EACH counter before stating a guarantee for both.

*Observed 2026-10-24 (architect-cto)*
