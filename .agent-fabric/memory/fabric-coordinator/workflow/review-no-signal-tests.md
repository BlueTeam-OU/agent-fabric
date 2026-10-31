---
role: "fabric-coordinator"
class: workflow
topic: "review-no-signal-tests"
description: "A review brief never invites signal tests: the reviewer's kill of a $var pid prompts the owner each time; the owner said stop (2026-10-17)"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 007fbaf106e52de4
---

## A review brief never invites signal tests: the reviewer's kill of a $var pid prompts the owner each time; the owner said stop (2026-10-17)

On InterWeave #294 the blind reviewer tested phone-run's exit paths with `kill -KILL $w` and similar; the self-kill guard asked the owner to confirm each one, repeatedly. The owner: "you must stop to do this", "again stop". I stopped the review and restarted it with an out-of-scope line: run no command that signals a pid held in a variable or a substitution; the author's live runs (named in the commit) are the evidence; review by reading.

**Why:** a reviewer's tool prompt lands on the owner, who is not the review's operator.
**How to apply:** when a range has signal or process-lifecycle behaviour, run those tests myself before the review, cite them in the commit, and put the no-signal line in the brief's out_of_scope. The guard false positive itself is job j264. See [[review-dispatch-no-cd]].

*References: review-dispatch-no-cd*

*Observed 2026-10-17 (fabric-coordinator)*
