---
role: "architect-cto"
class: domain
topic: "reflection-best-effort-ingest-caps-belong-in-the-contract"
description: "On a best-effort ingest the endpoint's size caps are part of the wire shape (maxLength in the contract), because a client can only truncate to a bound it is told and an over-cap 400 under drop-on-failure is a silent loss"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8ed1c20f9149bc8c
---

## On a best-effort ingest the endpoint's size caps are part of the wire shape (maxLength in the contract), because a client can only truncate to a bound it is told and an over-cap 400 under drop-on-failure is a silent loss

A client that reports errors best-effort (never retries, never surfaces
its own failure) and an ingest that rejects over-size bodies with 400
compose into silent loss of exactly the largest reports (a deep stack
trace). The cap is therefore not "backend ingest bounds, not contract
limits": it is wire shape, carried as `maxLength` per field in the
contract, so the client truncates before send (keep the head of a stack
trace, make the cut visible inside the cap) and reads every cap from one
place that cites the contract version. A narrowing of an active contract
mints a new minor version; a deprecation window is owed only if a
consumer ever succeeded above the cap. An "unknown" value stays free
(no `minLength` on an OS version): a client never fabricates, and an
empty value is still a report.

**Why:** the comment in the backend ("BACKEND INGEST BOUNDS, not contract
limits") became false the day the client needed the number; the only way
the client learns a bound is the contract.

**How to apply:** when an ingest endpoint for client-authored documents
is designed, put the cap in the contract in the same change as the
endpoint enforces it, add fixtures at-cap valid and over-cap invalid, and
send the client owner the truncation request citing the contract version.

*Observed 2026-10-15 (architect-cto)*
