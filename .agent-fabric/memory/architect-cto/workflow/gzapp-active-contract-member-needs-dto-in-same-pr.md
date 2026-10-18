---
role: "architect-cto"
class: workflow
topic: "gzapp-active-contract-member-needs-dto-in-same-pr"
description: "In gzapp, adding a member to an ACTIVE closed contract fails the merge queue unless the backend DTO gains the member in the same PR — the PR's own CI skips the backend surface and hides it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f58c5a99950baa18
---

## In gzapp, adding a member to an ACTIVE closed contract fails the merge queue unless the backend DTO gains the member in the same PR — the PR's own CI skips the backend surface and hides it

gzapp's `ResponseContractConformanceTests` / `RequestContractConformanceTests`
(`apps/backend_dotnet/tests/Gzapp.IntegrationTests.Common/RequestContractConformance.cs`)
hold each mapped DTO's wire members equal to its closed contract's
property set, both directions. So "contracts before code" for an
ACTIVE contract (ADR-077 A 2026-10-01's reading) still needs the DTO
member in the same PR, served null and omitted (`WhenWritingNull`), as
#1006 did for `push_registration`. A contracts-only PR is green on its
own CI (the detector skips the backend surface) and is evicted by the
merge queue, whose merge_group run builds every surface: #1120,
run 38782839170, "missing in DTO [call_sign]".

**Why:** the wire shape and the record that serves it are checked as one
thing; the PR's own checks cannot show it.

**How to apply:** when a contract edit touches an `active` contract with
a conformance row, request the DTO member from backend-dev as a one-commit
supply onto the contracts branch before arming (`AWAITING-SUPPLY` in the
body), and widen the review brief's file-scope invariant to admit that
file. A new `approved` contract needs nothing. See
[[gzapp-journey-call-sign-decision-2026-10-15]].

*References: gzapp-journey-call-sign-decision-2026-10-15*

*Observed 2026-10-15 (architect-cto)*
