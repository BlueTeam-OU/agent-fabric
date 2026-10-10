---
role: "backend-dev"
class: domain
topic: "npgsql-pooling"
description: "NpgsqlDataSource, not raw NpgsqlConnection, is what OTel query-span instrumentation hooks — correction qualifying the gzapp ADR citation"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "backend-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
  - clone_id: "clone-8a543ee5423d427c"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 33454e9bbd7cfc50
  - 92415433ac8fc179
  - b9efb6c3bebe4fae
  - c802541cd313b2b5
  - ce3b041d011223f9
---

## NpgsqlDataSource, not raw NpgsqlConnection, is what OTel query-span instrumentation hooks — correction qualifying the gzapp ADR citation

Wire Npgsql 9.x through a shared `NpgsqlDataSource` (built once per connection string with `NpgsqlDataSourceBuilder`, cached in a `ConcurrentDictionary<string, NpgsqlDataSource>`), not `new NpgsqlConnection(connectionString)` per call. The raw-connection form still works and still pools, but it silently opts out of `.AddNpgsql()`'s OTel query-span instrumentation, which hooks only the data source object. Key the cache by connection string rather than holding one global instance: under Testcontainers each test database then gets its own pool, instead of multiplying pools per factory instance or forcing every test database into one pool meant for a single production connection string.

*References: gzapp ADR-021 (OpenTelemetry observability policy)*

*Observed 2026-10-10 (backend-dev)*
