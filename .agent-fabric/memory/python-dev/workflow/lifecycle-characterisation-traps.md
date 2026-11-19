---
role: "python-dev"
class: workflow
topic: "lifecycle-characterisation-traps"
description: "Pinning a state machine's code against a table: derive findings from the verb x state matrix; two guards hide a mutation; the table moves under you"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b59c7b46077a4c06
---

## Pinning a state machine's code against a table: derive findings from the verb x state matrix; two guards hide a mutation; the table moves under you

j100 (PR 512, tests/test_work_lifecycle*.py): characterising fabric-jobs against ADR-037 rule 14.

- The coordinator's reading of the code was wrong in one place (start from done/dropped is refused by records.transition) and the table itself was corrected mid-job (eee64007 added rows that withdrew two findings). Probe each claim with the real command before filing it, and re-read the table ref before the PR body.
- A verb x state matrix (seed the state by editing jobs.json, run each verb, record exit 0) gives the cells outside the table directly; pin the set so a fix flips the test.
- Several behaviours are guarded twice (sweep's selector and its re-check under the lock; blockers' cleared-is-sticky in refresh and in the merge). A single mutation survives; plant both sites together. A sticky-cleared test also has to age checked_at past the ten-minute TTL or the TTL hides the mutation.
- An expectedFailure must fail on the behaviour it names: a switch-made branch has no commits and counts as landed to settle, so commit first or the case can never see its fix.
- Re-review brief: paste the rendered file exactly (I once shortened it); extract the posted report by requiring "# Re-review of" and no "## Previous findings", or the longest match is the prompt.
- tests/run.sh may wait 20+ minutes on the host lock held by another agent; arm with a `fabric-pr arm --authorization` is not read when the dry-run's minimum is already met.

**Why:** each cost a round. **How to apply:** before a characterisation PR, probe claims, pin the matrix, mutate every guard site.

*Anchors: `tests/test_work_lifecycle.py::VerbMatrix`, `tools/fabric/jobsparts/records.py::transition`*

*Observed 2026-11-08 (python-dev)*
