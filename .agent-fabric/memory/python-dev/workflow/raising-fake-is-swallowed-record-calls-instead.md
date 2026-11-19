---
role: "python-dev"
class: workflow
topic: "raising-fake-is-swallowed-record-calls-instead"
description: "j130 — a \"never called\" fake that raises AssertionError stays green when the code under test catches Exception; record the calls and assert none"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 604c5d2fe92850a5
---

## j130 — a "never called" fake that raises AssertionError stays green when the code under test catches Exception; record the calls and assert none

j130 (#623, control/presence.py carrier-only): my first tests passed a relay fake that raised `AssertionError` if called. Two mutations (post made anyway; relay polled anyway) survived, because `ask_presence` wraps the relay calls in `except Exception` (a failed relay is the second carrier's to make up for) and swallowed the assertion.

**Why:** the negative test ("the relay is never asked") has no positive control when the code under test is built to absorb relay failures.

**How to apply:** make the fake record `(method, path)` and fail like a down relay; assert `calls == []` afterwards. Run the mutations before trusting the test, and keep the backup outside a `$TMPDIR` that a failed `cp` could leave empty (check `cmp` after restoring). Also: a module-default argument binds at def time, so a suite that must own a state-reading default needs a late-bound `None` default plus a module patch. Related: [[mutation-backup-path-check-before-restore]].

*References: mutation-backup-path-check-before-restore*

*Anchors: `tools/fabric/control/presence.py::carrier_only`, `tests/test_control_w12_dual.py::class Relay`*

*Observed 2026-11-15 (python-dev)*
