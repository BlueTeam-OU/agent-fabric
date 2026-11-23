---
role: "flutter-dev"
class: domain
description: Riverpod 3.x FamilyNotifier test migration breaks silently, not loudly
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 1c45bbfc5a091d19
  - 49537f54d78606e2
  - 4c11db6dfa4430ed
  - fc156744c4bdad2e
---

## Riverpod 3.x FamilyNotifier test migration breaks silently, not loudly

Migrating FamilyNotifier-style test doubles from Riverpod 2.x to 3.x has two traps beyond the mechanical `build()` signature change. First: `build()` no longer takes the family argument — it must be injected via the Notifier's own constructor (`super(arg)`), and call sites move from `.overrideWith(() => Notifier())` to `.overrideWith2((arg) => Notifier(arg))`. A test subclass that hardcodes a fixed value in its super-constructor instead of forwarding the constructor's actual argument keeps compiling and keeps passing, but for the wrong reason — it silently ignores whatever family value the code under test actually supplies, so the test stops testing what it claims to. Second: Riverpod 3.x now throws at runtime if the same provider is overridden twice within one `ProviderContainer` (previously allowed silently) — a test pattern of layering a second override to switch behaviour mid-test is no longer possible; the container has to be rebuilt instead.
