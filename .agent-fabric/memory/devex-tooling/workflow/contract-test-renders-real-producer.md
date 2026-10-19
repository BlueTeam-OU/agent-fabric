---
role: "devex-tooling"
class: workflow
topic: "contract-test-renders-real-producer"
description: "a test that a reader takes every field a producer writes must feed the producer's output verbatim, every value set, and assert every key — never re-inject the key under test"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 99d59856c7680f19
---

## a test that a reader takes every field a producer writes must feed the producer's output verbatim, every value set, and assert every key — never re-inject the key under test

A reader-side test of a producer/reader contract proves nothing when it builds the input by hand or patches the
producer's output: in j127 (2026-10-14) my first "rendered header" check did `{**produced, "evidence_mode": mode}`,
so a producer rename of the very key the change fixed still passed, and `project`/`repository` were null on both
sides. The blind review caught it (P2).

**Why:** the hook read `evidence` while review_brief.dispatch_header wrote `evidence_mode`; only a test driven by
the real producer shows that, and a null == null comparison hides a dropped field.

**How to apply:** call the producer with inputs that make every field non-null, use its output verbatim, assert
`all(v is not None)` on it, then compare every emitted key (minus the deliberate exclusions, with renames mapped)
against the reader's result; mutation-check by renaming a key in the producer. Pin caller-environment inputs the
producer reads (e.g. CLAUDE_CODE_SESSION_ID) in the test process. See [[p1-ledger-hook-thread]].

*References: p1-ledger-hook-thread*

*Observed 2026-10-14 (devex-tooling)*
