---
role: "rust-services-dev"
class: domain
topic: "hyper-chunked-last-element-only"
description: "hyper 1.x client decodes chunked only if the last comma element of the last Transfer-Encoding line is chunked; an RFC-liberal list parse disagrees with it"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - c8d9a2312444aba0
---

## hyper 1.x client decodes chunked only if the last comma element of the last Transfer-Encoding line is chunked; an RFC-liberal list parse disagrees with it

hyper 1.12's h1 client (`src/headers.rs` `is_chunked`/`is_chunked_`) treats a response as chunked only when the last element of the last Transfer-Encoding field line is `chunked`. It takes `rsplit(',')` on the last line, then trims and compares case-insensitively; a line that is not valid `to_str` counts as not chunked. Anything else is read to the connection's close.

So `chunked ,` is close-delimited in hyper, even though RFC 9110 §5.6.1 says to ignore the empty element. A proxy check written to the RFC alone would accept the response and forward the chunk framing as content.

**Why:** in j94 my first `transfer_coding_forwardable` filtered empty elements. The real-socket test showed hyper reading `" , chunked ,"` close-delimited, and the test timed out.

**How to apply:** a gate in front of hyper accepts only what hyper actually decodes. The rule in the gateway is: the very last element is `chunked`, and every other element is empty (crates/backend/http/src/headers.rs). Keep a real-socket case per accepted spelling, so that a hyper upgrade changing this rule fails a test. Related: [[transfer-coding-before-chunked-probe]].

*References: transfer-coding-before-chunked-probe*

*Observed 2026-11-13 (rust-services-dev)*
