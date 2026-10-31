---
role: "p2p-network-dev"
class: domain
topic: "domain-one-exact-filter-per-must-run-test"
description: "A CI step that must run specific ignored tests gives each its own exact nextest filter with --no-tests=fail; ORed into one filter, a renamed or deleted test runs nowhere while the step stays green"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 83f5f370ba819b56
---

## A CI step that must run specific ignored tests gives each its own exact nextest filter with --no-tests=fail; ORed into one filter, a renamed or deleted test runs nowhere while the step stays green

I asked devex-tooling to add a second ignored test (TM-49's second-uid case) to InterWeave's foreign-uid CI
step as an OR beside S9's filter. devex-tooling changed the shape: `--no-tests=fail` fails only when the whole
filter matches nothing, so with an OR a renamed or removed TM-49 test would run nowhere and the step would
stay green on S9's match. It gave each test its own exact-filter run. Measured with nextest 0.9.148: each
filter selects exactly one test, and a name that matches nothing exits 4.

**How to apply:** when asking for a CI step for a test that only runs by name (ignored, environment-gated),
ask for one exact filter per test, each with `--no-tests=fail`. The same applies to any guard that checks "something
matched": it must be checked per required item, or the items guard each other's absence.
Related: [[known-failing-masks-new-failures]].

*References: known-failing-masks-new-failures*

*Observed 2026-10-22 (p2p-network-dev)*
