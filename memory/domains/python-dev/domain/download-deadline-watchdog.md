---
role: "python-dev"
class: domain
topic: "download-deadline-watchdog"
description: "Bounding a urllib download by wall-clock time (gateway-install, #176): read() and readline do not honour a deadline; use a watchdog that shuts down a duplicated socket"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ab3fdf58f4c4db12
---

## Bounding a urllib download by wall-clock time (gateway-install, #176): read() and readline do not honour a deadline; use a watchdog that shuts down a duplicated socket

A deadline checked between reads is not a bound against a hostile server: `HTTPResponse.read(n)` loops until n bytes and the socket timeout restarts with every byte; `read1` returns after one recv but http.client's chunk-size line and the status line are read with `readline`, which waits for a newline however slowly the bytes come; and a TLS handshake runs inside `connect()`. The bound that holds is a `threading.Timer` that calls `shutdown(SHUT_RDWR)` on the connection, set up from `connect()` by wrapping the instance's `_create_connection`. Track a `socket.fromfd` duplicate, not the socket object: `wrap_socket` detaches the original, so shutdown on it does nothing during the handshake. Close the duplicates in `finally`; settle the last-byte-versus-clock race with a `finish()` under the lock before the flush. urllib's default redirect handler forwards Authorization: subclass it to drop the header and refuse non-https. Python-source facts: tests for each phase need a real local server trickling bytes (chunked size line, status line, TLS record), and a mutation per phase.

**Why:** #176's review found each of these in turn (three rounds). **How to apply:** any bounded network read in the control plane.

*Observed 2026-10-10 (python-dev)*
