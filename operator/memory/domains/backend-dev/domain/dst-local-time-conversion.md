---
role: "backend-dev"
class: domain
description: "UTC-to-local conversion for a downstream local-time-string API is only ambiguous on fall-back, and the downstream tie-break can silently schedule earlier than intended"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-09-05"
origin:
  - clone_id: "clone-74e1ddd4096a45ce"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - b5f0ef71a9d046dd
  - d0c7d910af469659
  - dd53365c1f749502
---

## UTC-to-local conversion for a downstream local-time-string API is only ambiguous on fall-back, and the downstream tie-break can silently schedule earlier than intended

Converting a UTC instant to a target timezone's local wall-clock date/time (needed before handing a departure time to an API like OTP that accepts local strings, not UTC) is a total function in the spring-forward direction — the local time skipped during a spring-forward transition can never be the rendering of a real UTC instant, so that gap is unreachable by construction. The autumn fall-back overlap is real: one local wall-clock time corresponds to two different UTC instants. If the downstream system resolves an ambiguous local time to its EARLIER occurrence by default (observed behavior in OTP), and the caller's actual intended instant was the LATER one, sending the literal ambiguous local string silently plans against a bus that has already left — a wrong answer returned with no error. The fix pattern: detect when a requested departure lands in the overlap and, if it is the later occurrence, advance the composed local string past the end of the overlap window before sending it, and have every downstream consumer derive timestamps from that adjusted instant rather than the original request. Generalizes to any integration accepting local time strings rather than UTC instants.
