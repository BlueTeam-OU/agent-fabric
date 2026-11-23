---
role: "backend-dev"
class: domain
description: "OTel's default histogram bucket ladder is millisecond-shaped and lies about seconds-valued metrics"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: "clone-74e1ddd4096a45ce"
    host: "develop-qzapp"
  - clone_id: "clone-8a543ee5423d427c"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 22d4513690f0a7ea
  - 27eca6946292ae22
  - a99c1e4eabb6f1b8
  - aeaf01b451931aa1
  - b48165d0fb95ff13
  - b5cbe824623352c9
---

## OTel's default histogram bucket ladder is millisecond-shaped and lies about seconds-valued metrics

OpenTelemetry SDK's default explicit-bucket-boundary histogram ladder (`0, 5, 10, 25, 50, 75, 100, 250, 500, 750, 1000, 2500, 5000, 7500, 10000`) is shaped for millisecond-valued instruments. Registering a *seconds*-valued histogram (a DB connection-pool wait-time metric where healthy values are microseconds) without an explicit `AddView(...)` bucket override collapses every real value into the single 0–5s bucket, and `histogram_quantile` then interpolates a p95/p99 around 4.75s/4.95s regardless of actual latency — indistinguishable from genuine pool exhaustion on every dashboard reading it. Always pass explicit `AddView` boundaries matched to an instrument's real unit/scale, and back it with a test that scrapes `/metrics` and asserts real values land below a sub-scale boundary, not merely that the metric exists.

*References: #408*

## OTel-to-Prometheus name translation is mechanical but not guessable from the C# declaration

`OpenTelemetry.Exporter.Prometheus.AspNetCore` translates instrument names non-obviously: dots become underscores, the declared unit is expanded and appended (`"By"` → `_bytes`, `"s"` → `_seconds`), and counters/histograms get `_total`/`_bucket` suffixes. `<app>.tiles.bytes_served` (unit `By`) exports as `<app>_tiles_bytes_served_bytes_total`, not the name a naive reading of the C# instrument declaration would suggest. Before writing a Prometheus alert rule or Grafana query against a new metric, run an empirical probe (a scratch project scraping its own `/metrics`) rather than guessing the exported name.
