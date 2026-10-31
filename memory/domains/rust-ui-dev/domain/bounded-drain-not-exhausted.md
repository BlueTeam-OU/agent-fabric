---
role: "rust-ui-dev"
class: domain
topic: "bounded-drain-not-exhausted"
description: "Consuming a bounded event drain -- a short or empty return is not \"nothing left\" when notices, duplicates or undecodable items take slots"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c23d8544658b3960
---

## Consuming a bounded event drain -- a short or empty return is not "nothing left" when notices, duplicates or undecodable items take slots

When drain(max) caps the events taken from a session rather than the messages returned,
every notice, duplicate or undecodable payload takes a slot and returns nothing. So fewer
than max -- even zero -- can come back while messages wait. A caller must not stop at an
empty return: drain on every turn of its own loop, or wait on a readiness signal. I once
wrote the opposite ("drain until a call returns nothing") into a contract doc; the review
found it with a test that filled max with notices. Tests that count drain(1) calls break
when a new notice type (e.g. an open-time state event) is added -- take the notice first.

*Observed 2026-10-15 (rust-ui-dev)*
