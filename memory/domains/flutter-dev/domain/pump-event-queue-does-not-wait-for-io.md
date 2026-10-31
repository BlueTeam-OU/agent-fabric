---
role: "flutter-dev"
class: domain
topic: "pump-event-queue-does-not-wait-for-io"
description: "A Dart test that pumps the event queue to \"let the code reach\" a stream listen races real file I/O; synchronise on the controller's onListen instead"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 405ffc2f1995126f
---

## A Dart test that pumps the event queue to "let the code reach" a stream listen races real file I/O; synchronise on the controller's onListen instead

`pumpEventQueue()` turns zero-delay timers only; real `dart:io` work (temp-dir
stores, `File.exists`, `Directory.create`) completes on I/O callbacks it does
not wait for. A test that starts code doing such I/O, pumps, then feeds a
`StreamController` and acts (cancel, error) races it: on a slow CI runner the
listen comes late, events sit buffered, and the action lands before the first
event — gzapp's offline-pack cancel test wrote 3 bytes, not 5, once in the
merge queue (j39, commits 80ae04b46 + 0fe9d6c7a).

**Why:** green locally, flaky only under load, so it reaches the merge queue.
**How to apply:** give the controller `onListen: completer.complete` and await
that; guard the wait with `Future.any([listened, running.then(fail unless
listened)])` so an early return fails with its outcome, not the 30 s timeout.
Reproduce first by delaying one fake's answer ~50 ms — that turns the flake
deterministic. The sync test's `started()` poll is the same class.

*Observed 2026-10-25 (flutter-dev)*
