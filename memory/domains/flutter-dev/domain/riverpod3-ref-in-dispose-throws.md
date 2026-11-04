---
role: "flutter-dev"
class: domain
topic: "riverpod3-ref-in-dispose-throws"
description: Riverpod 3 ConsumerState — any ref.read/watch in State.dispose throws a StateError in release too, silently skipping the rest of dispose
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "flutter-dev-02"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - d75a51b3a8904d32
---

## Riverpod 3 ConsumerState — any ref.read/watch in State.dispose throws a StateError in release too, silently skipping the rest of dispose

flutter_riverpod 3.x (`ConsumerStatefulElement._assertNotDisposed`, 3.4.3) throws
`StateError('Using "ref" when a widget is about to or has been unmounted is unsafe')`
from `ref.read`/`watch`/`exists` once the element is deactivated. It is a plain
`throw`, not an `assert` — it fires in release builds. In `State.dispose` the first
`ref` call throws and every line after it (including `super.dispose()`) is skipped.

Fix shape: capture the notifiers in `initState` (`late final _x = ref.read(p.notifier)`)
and use the fields in dispose. A widget test that unmounts the screen
(`tester.pumpWidget(const SizedBox())`) reproduces it at once.

Found in gzapp driver_flutter `active_shift_screen.dart` (fix commit 3f767abb0, PR #1183):
the traversal poll outlived the shift and the next shift inherited answered offers.
A screen nobody had ever mounted in a test hid it — see [[flutter-coverage-floor-tooling]].

*References: flutter-coverage-floor-tooling*

*Observed 2026-10-26 (flutter-dev)*
