---
role: "devex-tooling"
class: workflow
topic: "supplier-dispatches-no-review"
description: "On a for/ supplier branch the dispatch hook refuses a code-review subagent; send your own checks with the supply instead"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0dcda07564e24ad8
---

## On a for/ supplier branch the dispatch hook refuses a code-review subagent; send your own checks with the supply instead

On 2026-11-02 (j270) I dispatched a code-review subagent from develop-qzapp/devex-tooling/for/user/…, and the PreToolUse
Agent hook refused it: "A supplier dispatches no review of its own part" (agent-fabric ADR-020 §5 rule 11). The
integrator folds every supply, runs the full suite and dispatches one blind review of the whole head. A finding on my
hunk comes back to me.

**Why:** one blind review per head. A supplier's own review would be a second, unrecorded round.

**How to apply:** for a contributor job in agent-fabric, skip the brief and the dispatch. Send in the delivery REPLY
the test that fails before and passes after (swap in main's file to show it), the mutations, and tests/run.sh in CI's
environment. Outside-entry hunks go in the same REPLY as a git diff. After sending, check the relayed copy is
byte-identical (fabric-history --thread … --full) ([[outside-entry-supply-as-staged-diff]]).

*References: outside-entry-supply-as-staged-diff*

*Anchors: `tools/fabric/guards/dispatch_guard.py::A supplier dispatches no review`*

*Observed 2026-11-02 (devex-tooling)*
