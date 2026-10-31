---
role: "web-dev"
class: domain
topic: "count-polls-on-the-network-log"
description: "to count how often a page polls a URL, read Playwright's network log; performance resource entries cap at 250 and a Vite dev page fills them, so they read as zero"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 6176b4def3ee133b
---

## to count how often a page polls a URL, read Playwright's network log; performance resource entries cap at 250 and a Vite dev page fills them, so they read as zero

`performance.getEntriesByType("resource")` holds at most 250 entries by
default (the resource timing buffer). A Vite dev page loads one module
per file and fills that before the app polls anything, so new requests
are never recorded and a poller looks silent. Count requests with
Playwright's network events (`page.on("request")`), and filter by URL.

Seen in gzapp while checking that `useUrlReachability` (web-shared) runs
one poller per URL and interval across every watcher (gzapp#1074,
2026-10-10).

*Observed 2026-10-12 (web-dev)*
