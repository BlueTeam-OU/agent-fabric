---
role: "python-dev"
class: workflow
topic: "roots-seam-stage2-and-intake"
description: "j6/j7/j11 (roots-seam tests on fixtures, bare command hints, REQUEST intake) — MERGED as #136; what it left and how it was run"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 58b8e2538c3859bc
---

## j6/j7/j11 (roots-seam tests on fixtures, bare command hints, REQUEST intake) — MERGED as #136; what it left and how it was run

#136 merged 2026-10-09 as d3edc887 (4 work, 5 fix, 2 merge), armed by me on the owner's word relayed
by fabric-coordinator (arm.sh 136 --basis "..."): under 8 work commits needs that word.
Carried and named in its reviews: watch (--follow) call site of the intake has no case of its own;
step-5 recovery-copy/store-backup lines of new_agent.py unasserted; test_lint/test_adr copy the live
docs/adr on purpose (stripped_run.py fails them; python-dev-01/coordinator own the skip list).

**Lessons (workflow):**
- A run of the whole suite needs a SHORT TMPDIR: path-length checks (recovery-copy < 250 chars)
  fail under the scratchpad's long path. Run suites with TMPDIR=/var/tmp/<short>.
- "Next work is another commit on the open PR": cherry-pick the finished branch onto it, delete the
  side branch; a posted review covers only the head it was posted on, so each fix commit and each
  merge of main needs its own re-review before the owner arms.
- tests/stripped_run.py <tree> <files> is the counterfactual for "test reads fixtures"; the in-tree
  suite cannot tell. Use it, or a copy of the tree with instance files moved aside.
- NEVER `git checkout <file>` with uncommitted edits (did it once, redid the edits).
- An assertion on a bare name ("fabric-role bind" in out) also matches "bin/fabric-role bind": pair it
  with the negative.

*Observed 2026-10-09 (python-dev)*
