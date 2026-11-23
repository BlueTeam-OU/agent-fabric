---
role: "db-admin"
class: domain
description: pg_advisory_xact_lock honors session lock_timeout and cancels with a normal error
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-09-05"
origin:
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - bb6160303e0dff55
  - ed6833942f5d6ec9
---

## pg_advisory_xact_lock honors session lock_timeout and cancels with a normal error

A session blocked waiting on pg_advisory_xact_lock respects `SET lock_timeout` the same way row/table locks do: a second session with `lock_timeout='1s'` waiting on a lock held by a long-running first session gets `ERROR: canceling statement due to lock timeout` rather than hanging indefinitely, confirmed live on Postgres 16. This makes advisory locks usable as a distributed mutex with deterministic, bounded wait behavior for orchestration-style coordination, without needing a separate polling/retry layer. This codebase's concurrency control otherwise leans on FOR UPDATE row locks; advisory locks are the tool to reach for when there is no row to lock against.
