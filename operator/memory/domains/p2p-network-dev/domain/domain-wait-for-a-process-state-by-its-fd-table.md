---
role: "p2p-network-dev"
class: domain
topic: "domain-wait-for-a-process-state-by-its-fd-table"
description: "A test that sleeps for a child process to reach a blocking point (a lock wait) flakes under load; wait on /proc/<pid>/fd holding the file instead"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 010336b2254c609f
---

## A test that sleeps for a child process to reach a blocking point (a lock wait) flakes under load; wait on /proc/<pid>/fd holding the file instead

A test that sleeps a fixed time for a spawned process to "be waiting on the lock"
fails under a loaded host: the process has not reached that point yet, and the
action meant for the wait (planting a file) is seen by an earlier read instead.
Wait on a real signal: the process holding the lock file open in
`/proc/<pid>/fd` (readlink each entry, compare to the canonicalized path), when
nothing before the wait opens that file. Poll short against the process's own
wait bound, since that bound runs from the open.

Proved by widening the real window: a 600 ms sleep before the daemon's load made
the old test fail with the exact flake message, the new one pass; removing the
under-lock read still fails the new one. InterWeave j92,
`tests/desktop-e2e/tests/daemon.rs` `holds_open`, commit 10cc8f9d7.
See [[domain-a-test-waits-for-the-state-it-presumes]].

*References: domain-a-test-waits-for-the-state-it-presumes*

*Observed 2026-11-05 (p2p-network-dev)*
