---
role: "fabric-coordinator"
class: threads
topic: "j845-te-chunked-last-element"
description: "gateway ADR-003 amendment j845 (upstream Transfer-Encoding fails closed) — what wording the record must use"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0587bb5da4c4cdb8
---

## gateway ADR-003 amendment j845 (upstream Transfer-Encoding fails closed) — what wording the record must use

j845 (agent-fabric-gateway ADR-003 amendment, decided 2026-11-13 as option (a), REPLY 01a1d60c): an upstream HTTP/1.1 response whose Transfer-Encoding is not absent or `chunked` fails closed, 502, not retried. Built as BlueTeam-OU/agent-fabric-gateway#92 (rust-services-dev-01, j94; head 2b1050d at 18:27Z).

Wording: NOT "list parsed per RFC 9110 5.6". hyper 1.12 decodes chunked only when the last element of the last TE line is `chunked`; `chunked ,` (legal per 5.6.1) is read to close and would forward chunk framing. The gate accepts: the very last element `chunked` (any case), every other element empty. Record says "the single coding chunked, as the last list element" (REPLY 01a1d629, `headers.rs` `transfer_coding_forwardable`).

Also for j845 (REQUEST 01a1d638, 18:43Z): bodiless responses (HEAD/204/304) with a non-chunked TE are refused too, kept as built on my word (AUTHORIZES 01a1d63a-700d for #92@529bcb11): the amendment says so. plan-v0 README "Usage (s11)": an entry appears once a head is received AND forwarded; a refused head records no usage (record_usage only on Ok) — fix that sentence in j845. j95 (Content-Length beside chunked forwarded) is rust-services-dev-01's.

j95 also goes into j845 (decided (a), REPLY to 01a1d64a, 19:05Z): an upstream head with Content-Length beside Transfer-Encoding is refused, 502, not retried, own class, RFC 9112 6.3 (smuggling); not stripped. Measured on main 1240601: short CL silently truncated, logged client_gone. Branch develop-qzapp/rust-services-dev-01/feat/j95-content-length-beside-chunked.

*Observed 2026-11-13 (fabric-coordinator)*
