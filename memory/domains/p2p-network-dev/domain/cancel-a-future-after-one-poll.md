---
role: "p2p-network-dev"
class: domain
topic: "cancel-a-future-after-one-poll"
description: "To test \"a caller that gave up after its command was sent\", poll once with Waker::noop on a current-thread runtime; tokio::time::timeout(Duration::ZERO) does NOT cancel after one poll"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - c4a1f08b948ce326
---

## To test "a caller that gave up after its command was sent", poll once with Waker::noop on a current-thread runtime; tokio::time::timeout(Duration::ZERO) does NOT cancel after one poll

`tokio::time::timeout(Duration::ZERO, fut)` is not "poll once, then drop": when the first poll is
Pending, the zero-deadline `Sleep` only fires after the timer driver runs, so the runtime runs other
tasks first — the Swarm task answered, and the future completed `Ok(Ok(()))` on BOTH the
multi-thread and current-thread flavours (measured 2026-09-28, Stage 13 B0a, the cancelled join/open
tests in `tests/local-client-conformance/tests/in_process.rs`).

What works: `#[tokio::test(flavor = "current_thread")]`, then
`let mut f = std::pin::pin!(fut); f.as_mut().poll(&mut Context::from_waker(Waker::noop())).is_pending()`
and drop `f`. On one thread the spawned task cannot answer inside that poll, so an mpsc command is
sent and the reply is never awaited — deterministic. Pair it with a control that the command DID
land (e.g. a status count reaching 1), or the test passes vacuously when nothing was sent.

**Why:** a cancellation test that never cancels agrees with any implementation.
**How to apply:** any test of "future dropped mid-flight" (claim guards, join bookkeeping, a
revoke's notice) — assert the single poll was Pending, then mutation-check the guard.

*Observed 2026-09-28 (p2p-network-dev)*
