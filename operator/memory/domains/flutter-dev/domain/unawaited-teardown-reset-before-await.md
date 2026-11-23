---
role: "flutter-dev"
class: domain
topic: "unawaited-teardown-reset-before-await"
description: "a stop()/teardown on a long-lived (non-autoDispose) notifier that callers fire unawaited must reset its state before its first await"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "flutter-dev-02"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - db398e44c77c9ab9
---

## a stop()/teardown on a long-lived (non-autoDispose) notifier that callers fire unawaited must reset its state before its first await

A Riverpod `Notifier` that is not autoDispose outlives the screen that starts
it, and screens call its teardown unawaited from `dispose` or listeners. If
the teardown does `await channel.stop(); state = initial;`, the next screen's
`start()` can run during the await, so the late reset wipes the new session's
state. If the await throws, the reset is skipped and the error surfaces as an
uncaught zone error. The rule: clear every session-scoped field *and* `state`
synchronously, then await the disconnect inside a try/catch that reports
silently and never rethrows. Test it with a fake whose `stop()` waits on a
held-open Completer while a second `start()` runs, plus a variant where
`stop()` throws.

Seen in gzapp driver `StopDirectiveFeed.stopFeed()` (fixed 57831aa82, #1183).
The race became reachable from one more path once `dispose` stopped throwing
on `ref.read` (see [[riverpod3-ref-in-dispose-throws]]).

*References: riverpod3-ref-in-dispose-throws*

*Observed 2026-10-26 (flutter-dev)*
