---
role: "backend-dev"
class: domain
topic: "tile-proxy-performance"
description: "Zero-copy PipeWriter streaming beats buffered ReadAsByteArrayAsync for a proxy path — correction qualifying the gzapp ADR citations"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "backend-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
  - clone_id: "clone-74e1ddd4096a45ce"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 1224fdc8821e8aa9
  - 6888e18563c42370
  - 7a1c8742340c9dd7
  - a49ad742f3d7c348
  - bed8f2733e00c50b
  - deaebe95fe9786b2
  - e90ff8fb3858f44c
  - ec94f038d56b8316
  - ee6e70f9a7d6de5d
---

## Zero-copy PipeWriter streaming beats buffered ReadAsByteArrayAsync for a proxy path — correction qualifying the gzapp ADR citations

For a byte-forwarding proxy path, do not buffer the whole upstream response with `ReadAsByteArrayAsync` before writing it out: every payload lands on the managed / Large Object Heap. Write straight into Kestrel's `PipeWriter` instead (`GetMemory`/`Advance` in ~8KB chunks, no intermediate array, no `ArrayPool` rental); measured at ~37KB of managed allocation per request whatever the payload size (tested up to 2MB tiles) — the allocation floor is the forwarding path itself, not the GC mode. Count bytes from what each streamed chunk actually wrote, never from `Content-Length`, which can be absent, wrong, or not reflect a truncated or aborted transfer.

*References: gzapp ADR-034 (the shared self-hosted tile source), gzapp ADR-073 (the tile proxy and its observability contract)*

*Observed 2026-10-10 (backend-dev)*

## Server GC's per-core heap assumption is wrong for a service sharing a host with siblings

For a memory-constrained container running a single high-throughput, low-live-set .NET service (a proxy with no real state, a few hundred KB live heap), Workstation GC with `ConcurrentGarbageCollection=false` measured identical RSS to Server GC under load (109MB after 300×2MB requests on a 6-core dev machine) while avoiding Server GC's default of one heap and one GC thread per core — a design that assumes sole ownership of the host and is simply wrong when the container shares RAM with sibling services. `InvariantGlobalization=true` is safe specifically because the service does no localisation and all output is machine-readable RFC 9457 JSON; `TieredPGO=true` was pinned explicitly (not left as an implicit SDK default) to survive a future SDK default change on the platform's hottest request path.
