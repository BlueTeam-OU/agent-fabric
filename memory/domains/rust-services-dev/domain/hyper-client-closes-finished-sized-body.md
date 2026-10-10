---
role: "rust-services-dev"
class: domain
topic: "hyper-client-closes-finished-sized-body"
description: "A test proving the gateway closed an upstream connection must leave that response's body unfinished — hyper's client closes a fully-received sized body itself"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - a9bff52f6260d098
---

## A test proving the gateway closed an upstream connection must leave that response's body unfinished — hyper's client closes a fully-received sized body itself

hyper 1's client connection (`client::conn::http1`) closes its socket on its
own once a response body with a known length has fully arrived and the
`SendRequest` handle is gone. So a test that asserts "the gateway closed the
upstream connection" passes even when the gateway leaks the response (e.g.
`std::mem::forget` on the body), if the fake upstream sent a small complete
sized body. Seen in gateway#21: `credential_retry`'s 429-connection test passed
under that mutation until the 429 was sent as an unfinished chunked body.

**How to apply:** to pin that a dropped response closes its connection, script
the upstream to leave the body open (chunked, no last chunk; `FakeUpstream`
then holds the connection until the peer closes), keep every other connection
in the test open too, and run the leak mutation before trusting the test.

*Observed 2026-10-09 (rust-services-dev)*
