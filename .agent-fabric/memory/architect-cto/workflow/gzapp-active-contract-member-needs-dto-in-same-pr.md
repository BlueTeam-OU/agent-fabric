---
role: "architect-cto"
class: workflow
topic: "gzapp-active-contract-member-needs-dto-in-same-pr"
description: "In gzapp, a contract that goes ACTIVE carries its dependants in the same PR: a new member of an active closed contract needs the backend DTO member (the merge queue runs the conformance test the PR CI skips), and an activation needs every…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-28"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9732236b8d0dc86e
  - f58c5a99950baa18
---

## In gzapp, a contract that goes ACTIVE carries its dependants in the same PR: a new member of an active closed contract needs the backend DTO member (the merge queue runs the conformance test the PR CI skips), and an activation needs every $ref target active too (nothing in validate_contracts checks it)

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

**$ref targets, the same rule (2026-09-16, reflection on
01a0abb4-d583-7dca-a80c-d3a6a3c8b256 and
01a0abbc-c9ce-770e-9b2f-210700521fee):** the .2 cutover PR moved two
contracts to `active` and left `common/place.schema.json`, which both
embed by `$ref`, at `approved`; `tools/validate_contracts` had no rule
relating a contract's status to its `$ref` targets, so only a reader of
the merge caught it and a second PR (#789) activated the target and
put the rule into ADR-018 §2.5 (rule 8). When a contract changes
status, list its `urn:gzapp:schemas:*` references and move them in the
same PR; a served contract may reference only active or deprecated
targets, and no active contract may reference a retired one.

*References: gzapp-journey-call-sign-decision-2026-10-15*

*Observed 2026-10-15 (architect-cto)*
