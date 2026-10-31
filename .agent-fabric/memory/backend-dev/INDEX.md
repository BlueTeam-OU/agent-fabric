---
role: "backend-dev"
class: index
description: "What backend-dev knows and where it lives."
tier: 1
distilled_at: "2026-10-31"
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

- [`memory/domains/backend-dev/domain/a-write-states-its-intent.md`](memory/domains/backend-dev/domain/a-write-states-its-intent.md) — When the meaning of a write depends on current state (first decision vs correction, create vs replace), the request must say which it means; inferring intent from state turns a stale page into a silent overwrite of someone else's write.
- [`memory/domains/backend-dev/domain/actions-rerun-keeps-old-workflow.md`](memory/domains/backend-dev/domain/actions-rerun-keeps-old-workflow.md) — A PR check fails on CI configuration that main has since fixed — a re-run will not pick up the fix; update the branch from main
- [`memory/domains/backend-dev/domain/advisory-lock-and-concurrency-control.md`](memory/domains/backend-dev/domain/advisory-lock-and-concurrency-control.md) — SET LOCAL lock_timeout has no retroactive effect on a pg_advisory_xact_lock call issued before it, and this backend never uses SERIALIZABLE
- [`memory/domains/backend-dev/domain/aspnet-bare-client-fault-statuses.md`](memory/domains/backend-dev/domain/aspnet-bare-client-fault-statuses.md) — Shaping every client-fault status as problem+json in ASP.NET Core minimal APIs — where 415/413/408/400 are actually produced and why no throw arm sees most of them
- [`memory/domains/backend-dev/domain/constraint-test-asserts-constraint-name.md`](memory/domains/backend-dev/domain/constraint-test-asserts-constraint-name.md) — Writing or editing a test that expects a Postgres constraint violation — assert the constraint's name, not only the SQLSTATE, and make the bad row violate only that one constraint
- [`memory/domains/backend-dev/domain/derived-data-stamp-covers-the-code.md`](memory/domains/backend-dev/domain/derived-data-stamp-covers-the-code.md) — Data computed at import and read later (folded names, normalised keys, precomputed spans) — stamp it with the version of EVERY input that decides it, code included, and make the reader refuse a mismatch observably
- [`memory/domains/backend-dev/domain/dotnet-test-gotchas.md`](memory/domains/backend-dev/domain/dotnet-test-gotchas.md) — Two nullable-reference-type gotchas in test doubles/assertions against framework interfaces
- [`memory/domains/backend-dev/domain/dst-local-time-conversion.md`](memory/domains/backend-dev/domain/dst-local-time-conversion.md) — UTC-to-local conversion for a downstream local-time-string API is only ambiguous on fall-back, and the downstream tie-break can silently schedule earlier than intended
- [`memory/domains/backend-dev/domain/importer-counts-what-it-tolerates.md`](memory/domains/backend-dev/domain/importer-counts-what-it-tolerates.md) — An importer reading a producer's file (export, feed) — store your own reading of derived values, count every disagreement/clamp/skip in the report with a warning, refuse the file only for what the producer cannot have written
- [`memory/domains/backend-dev/domain/insert-guard-does-not-bound-commit.md`](memory/domains/backend-dev/domain/insert-guard-does-not-bound-commit.md) — A reader that serves closed time windows needs the writer bounded from stamp to COMMIT on the reader's clock; a WHERE clock_timestamp() guard only bounds statement start
- [`memory/domains/backend-dev/domain/k-suppression-holds-across-responses.md`](memory/domains/backend-dev/domain/k-suppression-holds-across-responses.md) — Designing an aggregate read with small-cell (k) suppression — the property must hold across every response a caller can combine, not per response; serve fixed disjoint closed tiles, stable against writers and sweeps
- [`memory/domains/backend-dev/domain/keycloak-step-up-traps.md`](memory/domains/backend-dev/domain/keycloak-step-up-traps.md) — Keycloak step-up (LoA 2) traps that pass silently: a skipped credential step grants the level, custom client scopes drop acr/auth_time, a required action blocks password grants
- [`memory/domains/backend-dev/domain/media-urls-meet-the-browser-element.md`](memory/domains/backend-dev/domain/media-urls-meet-the-browser-element.md) — Before shaping a media read, check how the client's element will load the URL: an <img>/<video> src sends no Authorization header, so a 302 from a bearer-only route never reaches it; and an HLS manifest plays natively only in Safari.
- [`memory/domains/backend-dev/domain/middleware-error-ordering.md`](memory/domains/backend-dev/domain/middleware-error-ordering.md) — Guard middleware that throws must be registered after the problem-details middleware — correction qualifying the gzapp ADR citations
- [`memory/domains/backend-dev/domain/name-the-failing-half-not-a-quantifier.md`](memory/domains/backend-dev/domain/name-the-failing-half-not-a-quantifier.md) — Writing or reviewing prose, a log line or an error message about a guard over two or more conditions — name which condition failed; a quantified sentence ("both", "and", "no X and Y") inverts under negation
- [`memory/domains/backend-dev/domain/npgsql-pooling.md`](memory/domains/backend-dev/domain/npgsql-pooling.md) — NpgsqlDataSource, not raw NpgsqlConnection, is what OTel query-span instrumentation hooks — correction qualifying the gzapp ADR citation
- [`memory/domains/backend-dev/domain/offset-less-instants-take-the-process-zone.md`](memory/domains/backend-dev/domain/offset-less-instants-take-the-process-zone.md) — Parsing a date-time at any boundary in .NET (request body, engine response, feed) — a string without an offset is read in the process's local zone, UTC in a container; require the offset or read the exact scalar
- [`memory/domains/backend-dev/domain/one-read-test-needs-a-moving-clock.md`](memory/domains/backend-dev/domain/one-read-test-needs-a-moving-clock.md) — How to write a test that pins "one clock read per operation" so it can actually fail
- [`memory/domains/backend-dev/domain/otel-instrumentation.md`](memory/domains/backend-dev/domain/otel-instrumentation.md) — OTel's default histogram bucket ladder is millisecond-shaped and lies about seconds-valued metrics
- [`memory/domains/backend-dev/domain/tile-proxy-performance.md`](memory/domains/backend-dev/domain/tile-proxy-performance.md) — Zero-copy PipeWriter streaming beats buffered ReadAsByteArrayAsync for a proxy path — correction qualifying the gzapp ADR citations
- [`memory/domains/backend-dev/domain/uuidv7-same-millisecond-order-is-random.md`](memory/domains/backend-dev/domain/uuidv7-same-millisecond-order-is-random.md) — Guid.CreateVersion7 has no counter inside a millisecond, so two ids minted in one ms sort by random bits; a test that ORDER BYs minted ids and asserts positions is a coin flip
- [`memory/shared/domain-claude-code-attribution-reminder.md`](memory/shared/domain-claude-code-attribution-reminder.md) — The attribution key is written by runtime/claude-code/user-settings.py, run from tools/fabric/bootstrap.py (shared)

## workflow

- [`.agent-fabric/memory/backend-dev/workflow/fabric-review-rereview-card-base.md`](.agent-fabric/memory/backend-dev/workflow/fabric-review-rereview-card-base.md) — A re-review request whose base is not on main needs card_base; finding-adjudication is its own mode
- [`.agent-fabric/memory/backend-dev/workflow/pgrep-wait-loop-self-match.md`](.agent-fabric/memory/backend-dev/workflow/pgrep-wait-loop-self-match.md) — A background "wait until no dotnet build runs" loop using pgrep -f deadlocks on its own command line

## recall

- [`identities/roles/backend-dev/recall.md`](identities/roles/backend-dev/recall.md) — Where backend-dev's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
