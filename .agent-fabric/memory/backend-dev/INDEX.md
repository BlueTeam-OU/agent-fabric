---
role: "backend-dev"
class: index
description: "What backend-dev knows and where it lives."
tier: 1
distilled_at: "2026-10-10"
---

# backend-dev — knowledge index

A session is given the charter and brief (in the launch prompt),
and the project's remit with a pointer to this index (from the
session-start hook) — nothing below. Open a slice when its cue
matches what you are doing; a `workflow` slice says how a kind of
work is done here, so read the matching ones before that work.
Paths are relative to this working copy; `../agent-fabric/` is the
control plane checked out beside it.

## charter

- [`identities/roles/backend-dev/charter.md`](identities/roles/backend-dev/charter.md) — The backend that owns meaning: endpoints, services, data access, and the interpretation the clients are not allowed to do.

## brief

- [`identities/roles/backend-dev/brief.md`](identities/roles/backend-dev/brief.md) — How backend-dev works day to day, in any project: what the job is, the kind of thing it knows, the lines with the other roles, what it reads first.

## domain

- [`memory/domains/backend-dev/domain/advisory-lock-and-concurrency-control.md`](memory/domains/backend-dev/domain/advisory-lock-and-concurrency-control.md) — SET LOCAL lock_timeout has no retroactive effect on a pg_advisory_xact_lock call issued before it, and this backend never uses SERIALIZABLE
- [`memory/domains/backend-dev/domain/dotnet-test-gotchas.md`](memory/domains/backend-dev/domain/dotnet-test-gotchas.md) — Two nullable-reference-type gotchas in test doubles/assertions against framework interfaces
- [`memory/domains/backend-dev/domain/dst-local-time-conversion.md`](memory/domains/backend-dev/domain/dst-local-time-conversion.md) — UTC-to-local conversion for a downstream local-time-string API is only ambiguous on fall-back, and the downstream tie-break can silently schedule earlier than intended
- [`memory/domains/backend-dev/domain/middleware-error-ordering.md`](memory/domains/backend-dev/domain/middleware-error-ordering.md) — Guard middleware that throws must be registered after the problem-details middleware
- [`memory/domains/backend-dev/domain/npgsql-pooling.md`](memory/domains/backend-dev/domain/npgsql-pooling.md) — NpgsqlDataSource, not raw NpgsqlConnection, is what OTel query-span instrumentation hooks
- [`memory/domains/backend-dev/domain/otel-instrumentation.md`](memory/domains/backend-dev/domain/otel-instrumentation.md) — OTel's default histogram bucket ladder is millisecond-shaped and lies about seconds-valued metrics
- [`memory/domains/backend-dev/domain/tile-proxy-performance.md`](memory/domains/backend-dev/domain/tile-proxy-performance.md) — Zero-copy PipeWriter streaming beats buffered ReadAsByteArrayAsync for a proxy path
- [`memory/shared/domain-claude-code-attribution-reminder.md`](memory/shared/domain-claude-code-attribution-reminder.md) — The attribution key is written by runtime/claude-code/user-settings.py, run from tools/fabric/bootstrap.py (shared)

## recall

- [`identities/roles/backend-dev/recall.md`](identities/roles/backend-dev/recall.md) — Where backend-dev's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
