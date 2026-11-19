---
role: "flutter-dev"
class: domain
topic: "dio-json-transform-eats-5xx-status"
description: "dio decodes a JSON-labelled body BEFORE checking the status — an undecodable 5xx becomes a status-less unknown; fetch as plain text where the status matters"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - d9f1c31a759ccf57
---

## dio decodes a JSON-labelled body BEFORE checking the status — an undecodable 5xx becomes a status-less unknown; fetch as plain text where the status matters

dio 5.11.1 (`dio_mixin.dart` `_dispatchRequest`) runs `transformer.transformResponse` before it throws `badResponse`. With `ResponseType.json`, a 5xx whose body is labelled `application/json` but does not decode (a gateway HTML page) throws FormatException → `DioExceptionType.unknown`, **no `response`, no status code**, and no `X-Correlation-Id` for the error sink's pivot either.

Fix shape (gzapp passenger Resolver, f51f750d7, #1257 F13): `ResponseType.plain` + `jsonDecode` in the repository; `ServedProblem.read` already takes a raw String. Keep the 2xx-undecodable class unchanged unless deliberately reclassifying it.

**How to apply:** any caller whose failure class depends on the status (ADR-019 s2.11 `isAvailability5xx`, ADR-026 s2.7 guest call) has this fault while it decodes in dio. Surveyed in j58's #1258 review (2026-11-14): every other converted caller maps `DioExceptionType.unknown` to its unavailable class, so an undecodable JSON-labelled 5xx still lands on availability, as s2.11's no-retryable row wants; only a caller whose next step depends on the STATUS (the Resolver's guest call) needs the plain+decode shape ([[served-problem-retryable-classifier]]). Test it with an adapter that labels a non-JSON body as JSON; a body labelled text/plain does not reproduce it.

*References: served-problem-retryable-classifier*

*Observed 2026-11-14 (flutter-dev)*
