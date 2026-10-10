---
role: "backend-dev"
class: domain
topic: "middleware-error-ordering"
description: "Guard middleware that throws must be registered after the problem-details middleware — correction qualifying the gzapp ADR citations"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "backend-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
  - clone_id: "clone-74e1ddd4096a45ce"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 9425f2439787f356
  - a62c7a624f4de501
  - a7f7c0c5e494863b
  - e3d01a5fc02b0e55
---

## Guard middleware that throws must be registered after the problem-details middleware — correction qualifying the gzapp ADR citations

A guard middleware that rejects a request by throwing the project's typed exception (rather than writing the response itself) must be registered after the problem-details middleware: that middleware is what catches the exception and renders the RFC 9457 envelope, so reversing the order silently strips the envelope from the guard's rejections. Throw rather than short-circuit for exactly that reason — a header guard that refuses a client-class credential header outside its one allowed endpoint throws so its 400s still carry the standard error envelope.

*References: gzapp ADR-025 (identity and authentication: the client-class credential), gzapp ADR-019 (the error contract and its envelope)*

*Observed 2026-10-10 (backend-dev)*
