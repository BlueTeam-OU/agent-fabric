---
role: "rust-services-dev"
class: domain
topic: "response-commitment-point"
description: Where a proxied response commits, and what a proxy may and may not do on each side of that point (retry, failover, its own error, an upstream failure)
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - af7e9109d21d0015
---

## Where a proxied response commits, and what a proxy may and may not do on each side of that point (retry, failover, its own error, an upstream failure)

Every proxied response has a commitment point. On a raw proxy it is the
first byte forwarded to the client, and the response head counts.
Decide where it is before writing retry, failover or error handling.

- **Before it**, the proxy may answer with its own error, or retry and
  fail over, under the retry rules (never replaying a side effect).
- **After it**, nothing is retried, re-routed or spliced. An upstream
  failure reaches the client as a cut: no terminal chunk, or a body
  shorter than its Content-Length. It is never a clean end, because a
  clean end tells the client that a truncated answer is whole.

Test both sides over a real socket. Assert the cut at the client, for
chunked and for sized bodies, and assert that a committed stream is
never retried.

Evidence, agent-fabric-gateway main: PRs #16 and #17;
tests/anthropic-passthrough/tests/cancellation.rs
`an_upstream_cut_{mid_chunk,inside_a_sized_body}_reaches_the_client_as_a_cut`,
credential_retry.rs `a_committed_stream_is_never_retried`, and
tests/openai-responses-passthrough/tests/streams.rs
`an_upstream_cut_mid_stream_reaches_the_client_as_a_cut`. Proposed for the
role's brief on 2026-10-17 (the REPLY above); not in the brief on
agent-fabric origin/main as of 2026-10-18.
Related: [[proxy-time-bounds-are-separate-clocks]].

*References: proxy-time-bounds-are-separate-clocks*

*Observed 2026-10-18 (rust-services-dev)*
