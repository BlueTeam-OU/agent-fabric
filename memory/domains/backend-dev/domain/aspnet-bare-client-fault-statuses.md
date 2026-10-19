---
role: "backend-dev"
class: domain
topic: "aspnet-bare-client-fault-statuses"
description: "Shaping every client-fault status as problem+json in ASP.NET Core minimal APIs — where 415/413/408/400 are actually produced and why no throw arm sees most of them"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "backend-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 9b021f4c18740e92
---

## Shaping every client-fault status as problem+json in ASP.NET Core minimal APIs — where 415/413/408/400 are actually produced and why no throw arm sees most of them

In ASP.NET Core minimal APIs (measured on .NET 10):
- An unaccepted Content-Type never reaches the binder. ROUTING answers it, through the
  accepts-matcher's synthetic "415 HTTP Unsupported Media Type" endpoint: empty
  metadata, bare status.
- Kestrel's body faults (over MaxRequestBodySize → 413, a body arriving too slowly →
  408, a truncated body → 400) are swallowed by the binder's read and written as a
  bare status, even with RouteHandlerOptions.ThrowOnBadRequest on. An exception-handler
  arm for them is unreachable.
- 431 (oversize headers) and 414 (long URI) are refused at the connection, before
  any middleware, and cannot carry a body.
- The test server has no body limit, so a 413 is not reproducible end-to-end there.

So the one place that shapes all of them is post-pipeline: a middleware that turns any
bare client-fault status into the problem body (the route's own key for 400), run
INSIDE any idempotency capture, so a stored replay holds the problem.
ThrowOnBadRequest only moves the 400 onto the thrown path; it is not what makes the
wire right.

**Why:** gzapp #832 / #834 (2026-09-17). Four review rounds found the 413 arm
unreachable (IL-verified). A later measurement with ThrowOnBadRequest off still
produced the carrier's key, through the post-pipeline table.

**How to apply:** for an error-contract rule that says "no bare status", test each
status through the real pipeline and put the shaping after it. Related:
[[closed-carriers-other-hosts]], [[middleware-error-ordering]].

*References: closed-carriers-other-hosts, middleware-error-ordering*

*Observed 2026-10-15 (backend-dev)*
