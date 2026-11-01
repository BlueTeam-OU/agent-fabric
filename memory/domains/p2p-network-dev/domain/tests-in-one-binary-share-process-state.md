---
role: "p2p-network-dev"
class: domain
topic: "tests-in-one-binary-share-process-state"
description: "cargo test runs a binary's tests as parallel threads of ONE process, so a test asserting on process-global state (a captured log, a static gate, a per-process port registry) races its siblings; nextest runs one process per test, which…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1f13e47b22355722
---

## cargo test runs a binary's tests as parallel threads of ONE process, so a test asserting on process-global state (a captured log, a static gate, a per-process port registry) races its siblings; nextest runs one process per test, which breaks per-process uniqueness instead. Give such a test its own binary or a per-test seam, and reproduce flakes under the runner CI uses

Three InterWeave failures came from one fact about how the test harness
runs:

- **A shared log** (#261, endpoint_overlay.rs): a test counted "overlay is
  ahead" warnings in a log shared by the whole binary, and a sibling test
  emitted the same warning. It failed 8 of 8 on a 10-core host, passed
  alone and under `--test-threads=1`, and passed in CI by timing. #215's
  re-review had already fixed the same class for the trust overlay by
  giving the ahead test a binary of its own (trust_overlay_ahead.rs). #261
  repeated the bug because the fix was made per instance.
- **A static gate** (#236): a process-wide "one outstanding NSS read" flag
  made two tests refuse each other, failing 257 of 300 runs. Fixed by
  putting the flag behind the trait seam the fakes implement, so each fake
  has its own. See [[a-blocking-lookup-in-a-fail-closed-check-is-fail-stuck]].
- **The opposite direction** (#288, nextest): `free_port` kept its
  "handed out" set per process. Under nextest, which runs one process per
  test with binaries in parallel, two tests can get the same port and
  silently share it under SO_REUSEPORT. See the free-port slices.
- **Inherited descriptors** (#386, transportctl identity.rs): a sibling
  test's forked child shares a flock's open file description from fork to
  exec, so the lock outlived the parent's drop. See
  [[a-forked-sibling-holds-a-dropped-flock]].

**How to apply:** before a test asserts on anything global (log capture,
a static, an env var, a port, a file in a shared dir), decide which unit it
must be isolated in: a thread (pass it through a seam), a process (its own
`[[test]]` binary), or the host (a cross-process reservation). Reproduce a
suspected flake both ways: the whole binary in parallel, and the runner CI
uses. Running it alone proves nothing. When one instance is fixed, grep
for siblings of the same shape in the same PR.

*References: a-blocking-lookup-in-a-fail-closed-check-is-fail-stuck, a-forked-sibling-holds-a-dropped-flock, test*

*Observed 2026-10-25 (p2p-network-dev)*
