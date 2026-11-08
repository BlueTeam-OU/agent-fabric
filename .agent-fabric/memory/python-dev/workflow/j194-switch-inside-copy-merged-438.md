---
role: "python-dev"
class: workflow
topic: "j194-switch-inside-copy-merged-438"
description: "j194 #438 merged; post-review refuses a re-review after main is merged in; arm --defer syntax; worktree-as-working-copy consequence"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 35e8b2a83c1ed755
---

## j194 #438 merged; post-review refuses a re-review after main is merged in; arm --defer syntax; worktree-as-working-copy consequence

#438 (switch takes a job in place only from inside its copy) merged 2026-11-01 on bc6c31a4, armed on the owner's word.

- After the coordinator merged origin/main into the branch, `fabric-pr post-review` refused a re-review whose base was the old head ("neither the merge-base nor a checkpoint head"). Fix: a full primary review of merge-base..head (`fabric-review brief` with `range: <merge-base>..<head>`), report posted verbatim; the coverage block may list only paths in that range.
- Open P3s in a review chain refuse arm; lift each with `--defer "<review-head8>:F<n>" "<why>"` (head8 is the head the review was raised on).
- Since #432 the switch records the job's worktree as working_copy, so a session in the project's main checkout is outside the copy and gets a fresh verdict.
- Never chain `cd <scratch> && fabric-pr post-review`: the job guard reads the first cd; run it bare from the project cwd.
- Carried: F1 test for the "or under" clause of inside (verbs.py outside_copy startswith) in my next PR; DIGEST bullet and ADR-022 amendment are the coordinator's.

**Why:** these cost several refused commands. **How to apply:** next PR after a coordinator merge-in.

*Observed 2026-11-01 (python-dev)*
