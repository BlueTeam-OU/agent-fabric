---
role: "python-dev"
class: threads
topic: "j202-external-review-f03-f05"
description: "j202 = external review F03 (P1 settle/sweep unfolded-and-not-landed), F04 (rename_working_copy worktrees), F05 (rename leaves jobs.json paths): one PR, a commit and a failing-on-base test per finding"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 22c506c399662cc8
---

## j202 = external review F03 (P1 settle/sweep unfolded-and-not-landed), F04 (rename_working_copy worktrees), F05 (rename leaves jobs.json paths): one PR, a commit and a failing-on-base test per finding

j202 = REQUEST 01a1a5c8-d307-7998-8343-7e415b9379d7 (fabric-coordinator, develop-qzapp/user). I acknowledged it (REPLY seq 812692); the PR number is owed in a REPLY when open and again when merged. Branch develop-qzapp/python-dev-01/feat/j202-external-review-f03-f04-f05-job, worktree ~/projects/agent-fabric-j202-external-review-f03-f04-f05-job.

Each finding is a claim: reproduce on origin/main with a test that fails there first, else REPLY "did not reproduce" with what I ran. Order F03 (jobsparts/settle.py:309-326, sweep.py:154-175), F04 (provisioning/rename_working_copy.py:136-149), F05 (runtime/provisioning/rename_history.py:119-127; refusals at jobsparts/verbs.py:386-393, branching.py:113-116 — I changed branching.py in #471, re-read it). Look for the sibling path of each (the review's thread: an invariant held at one entry point, lost at another).

j201 closed with `fabric-jobs deliver j201 BlueTeam-OU/agent-fabric#471` — done needs deliver evidence before switch.

*Observed 2026-11-04 (python-dev)*
