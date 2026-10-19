---
role: "flutter-dev"
class: domain
topic: "rule-over-data-count-whole-population"
description: "Before a predicate or exclusion rule over real data ships, count it over the whole dataset and read every exception — a sample lies, and an \"exception\" may be a convention."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 80be087e1b52596b
---

## Before a predicate or exclusion rule over real data ships, count it over the whole dataset and read every exception — a sample lies, and an "exception" may be a convention.

Twice in one afternoon a rule about gazetteer data was about to be written
from a sample or a relayed impression: a house-number predicate sampled on
one street, and an "exclude name-only places" rule that, counted, would have
deleted 2,008 real places (89% of landmarks lacked an address, so the
proposed marker distinguished nothing). Counting the whole population
settled both. Reading the exceptions one by one mattered as much: three of
six "malformed" house numbers were `№5` / `N3`, which is how Georgian writes
a house number — a convention, not a defect, and a regex that rejects it
fails real riders.

**How to apply:** for any rule that classifies data or rider input, run the
count over the full dataset (per class), print every exception, and ask a
locale holder about any exception that looks like a writing convention
before calling it bad data.

*Observed 2026-10-15 (flutter-dev)*
