---
role: "rust-services-dev"
class: domain
topic: "hyper-cancellation-and-head-deadline"
description: "What hyper 1.x itself does on body drop and idle connections, and how gateway tests separate it from the gateway's own guards"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - 02315f131565ce5f
---

## What hyper 1.x itself does on body drop and idle connections, and how gateway tests separate it from the gateway's own guards

Verified on hyper 1.12.0 with mutation tests in agent-fabric-gateway PR #5 (`tests/anthropic-passthrough`):
- **Body drop:** a `client::conn::http1` connection closes by itself when its response body is
  dropped unfinished. An abort-on-drop guard around the driver task is defence in depth, not what
  closes it. To prove cancellation, mutate the gateway (hold the body, detach the attempt into a
  spawned task) rather than removing the guard.
- **Head deadline:** the server's `header_read_timeout` (30 s default, effective only with
  `.timer(TokioTimer)`) starts when `poll_read_head` begins, before any byte arrives. It is
  re-armed for idle kept-alive connections, so a silent socket returns its slot.
- **Version floor for the head deadline:** before 1.4.0, `parse_headers` armed the timer only
  once bytes arrived (an empty buffer returned first), so a silent socket held its slot forever.
  From 1.4.0 a new connection is covered, but the deadline is not re-armed for an idle
  kept-alive connection until 1.6.0 (`notify_read`). The gateway requires `hyper = "1.6"`
  (agent-fabric-gateway PR #6). Shown by pinning hyper and hyper-util back in a local lockfile;
  hyper-util 0.1.21 needs a recent hyper, so pin hyper-util first (0.1.10 accepts ^1.4).
- **Test windows:** a cancellation test's close window must be well under every upstream timeout.
  At 5 s against a 5 s head timeout, a detached attempt passed by timing out.

*Observed 2026-10-08 (rust-services-dev)*
